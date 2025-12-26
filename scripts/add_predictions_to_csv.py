"""
Add FTE predictions to the CSV file permanently.
Run once to enrich ml_ready_v3.csv with:
- predicted_fte: ML model recommendation
- fte_diff: actual - predicted (negative = understaffed)
- revenue_at_risk: potential lost revenue from understaffing
"""

import pickle
import pandas as pd
import json
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "fte_model_v5.pkl"
DATA_PATH = PROJECT_ROOT / "data" / "ml_ready_v3.csv"
GROSS_FACTORS_PATH = PROJECT_ROOT / "data" / "gross_factors.json"

# Load model
with open(MODEL_PATH, 'rb') as f:
    model_pkg = pickle.load(f)

# Load data
df = pd.read_csv(DATA_PATH)
defaults = df.median(numeric_only=True).to_dict()

# Load gross factors
with open(GROSS_FACTORS_PATH, 'r') as f:
    gross_factors_data = json.load(f)
PHARMACY_GROSS_FACTORS = {int(k): v for k, v in gross_factors_data['factors'].items()}

# Segment productivity means
SEGMENT_PROD_MEANS = model_pkg.get('segment_prod_means', {
    'A - shopping premium': 7.25,
    'B - shopping': 9.14,
    'C - street +': 6.85,
    'D - street': 6.44,
    'E - poliklinika': 6.11
})

# Gross conversion factors by type
GROSS_CONVERSION = {
    'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
    'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
    'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
    'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
    'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
}

rx_time_factor = model_pkg.get('rx_time_factor', 0.41)


def calculate_gross_actual_fte(row):
    """Calculate GROSS actual FTE using pharmacy-specific or type-based factors."""
    pharmacy_id = int(row['id'])
    typ = row['typ']

    if pharmacy_id in PHARMACY_GROSS_FACTORS:
        pf = PHARMACY_GROSS_FACTORS[pharmacy_id]
        gross = row['fte_F'] * pf['F'] + row['fte_L'] * pf['L'] + row['fte_ZF'] * pf['ZF']
    else:
        conv = GROSS_CONVERSION.get(typ, {'F': 1.22, 'L': 1.22, 'ZF': 1.20})
        gross = row['fte_F'] * conv['F'] + row['fte_L'] * conv['L'] + row['fte_ZF'] * conv['ZF']

    return round(gross, 1)


def predict_fte_for_row(row):
    """Calculate predicted FTE for a single pharmacy."""
    typ = row['typ']
    bloky = row['bloky']
    trzby = row['trzby']
    podiel_rx = row['podiel_rx']
    pharmacy_id = int(row['id'])

    # Build features using EXACT same logic as /api/pharmacy/{id} endpoint
    # Copy all features from row, then override calculated ones
    features = {col: row.get(col, 0) for col in model_pkg['feature_cols']}
    features['effective_bloky'] = bloky * (1 + rx_time_factor * podiel_rx)

    # Create feature vector
    X = pd.DataFrame([{col: features.get(col, 0) for col in model_pkg['feature_cols']}])

    # Predict NET FTE
    fte_net = model_pkg['models']['fte'].predict(X)[0]
    fte_net = max(0.5, fte_net)

    # Get role proportions
    props = model_pkg['proportions'].get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})

    # Calculate NET role breakdown
    fte_F_net = fte_net * props['prop_F']
    fte_L_net = fte_net * props['prop_L']
    fte_ZF_net = fte_net * props['prop_ZF']

    # Convert to GROSS using pharmacy-specific or type-based factors
    if pharmacy_id in PHARMACY_GROSS_FACTORS:
        pf = PHARMACY_GROSS_FACTORS[pharmacy_id]
        fte_F_gross = fte_F_net * pf['F']
        fte_L_gross = fte_L_net * pf['L']
        fte_ZF_gross = fte_ZF_net * pf['ZF']
    else:
        conv = GROSS_CONVERSION.get(typ, {'F': 1.22, 'L': 1.22, 'ZF': 1.20})
        fte_F_gross = fte_F_net * conv['F']
        fte_L_gross = fte_L_net * conv['L']
        fte_ZF_gross = fte_ZF_net * conv['ZF']

    # Total GROSS FTE (rounded)
    predicted_fte = round(fte_F_gross + fte_L_gross + fte_ZF_gross, 1)

    return predicted_fte


def calculate_revenue_at_risk(predicted_fte, actual_fte, trzby, produktivita, typ):
    """Calculate revenue at risk from understaffing."""
    # Check if above average productivity
    segment_avg = SEGMENT_PROD_MEANS.get(typ, 7.0)
    is_above_avg = produktivita > segment_avg

    if not is_above_avg or predicted_fte <= actual_fte or trzby <= 0:
        return 0

    actual_rounded = round(actual_fte, 1)
    predicted_rounded = round(predicted_fte, 1)

    if predicted_rounded <= actual_rounded:
        return 0

    overload_ratio = predicted_rounded / actual_rounded if actual_rounded > 0 else 1
    revenue_at_risk = int((overload_ratio - 1) * 0.5 * trzby)
    return revenue_at_risk


# Calculate predictions for all pharmacies using GROSS FTE
print(f"Processing {len(df)} pharmacies using GROSS FTE...")

predictions = []
for idx, row in df.iterrows():
    predicted_fte = predict_fte_for_row(row)
    actual_fte_gross = calculate_gross_actual_fte(row)  # GROSS, not NET
    fte_diff = round(actual_fte_gross - predicted_fte, 1)
    revenue_at_risk = calculate_revenue_at_risk(
        predicted_fte, actual_fte_gross, row['trzby'], row['produktivita'], row['typ']
    )
    predictions.append({
        'predicted_fte': predicted_fte,
        'actual_fte_gross': actual_fte_gross,
        'fte_diff': fte_diff,
        'revenue_at_risk': revenue_at_risk
    })

# Add columns to dataframe
df['predicted_fte'] = [p['predicted_fte'] for p in predictions]
df['actual_fte_gross'] = [p['actual_fte_gross'] for p in predictions]  # New column
df['fte_diff'] = [p['fte_diff'] for p in predictions]
df['revenue_at_risk'] = [p['revenue_at_risk'] for p in predictions]

# Save
df.to_csv(DATA_PATH, index=False)
print(f"Updated {DATA_PATH}")

# Summary
understaffed = df[df['fte_diff'] < -0.5]
print(f"\nSummary:")
print(f"  Total pharmacies: {len(df)}")
print(f"  Understaffed (diff < -0.5): {len(understaffed)}")
print(f"  Total revenue at risk: €{df['revenue_at_risk'].sum():,.0f}")
print(f"\nNew columns added: predicted_fte, fte_diff, revenue_at_risk")
