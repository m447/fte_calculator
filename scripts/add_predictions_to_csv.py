"""
Add FTE predictions to the CSV file permanently.

SINGLE SOURCE OF TRUTH for GROSS FTE conversion:
    actual_gross = fte + fte_n (NET working staff + absence FTE)
    predicted_gross = predicted_net + fte_n (same formula)

Run once to enrich ml_ready_v3.csv with:
- predicted_fte: ML model recommendation (GROSS)
- predicted_fte_net: ML model recommendation (NET)
- actual_fte_gross: actual GROSS FTE (fte + fte_n)
- fte_diff: actual - predicted (negative = understaffed)
- revenue_at_risk: potential lost revenue from understaffing
"""

import pickle
import pandas as pd
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "fte_model_v5.pkl"
DATA_PATH = PROJECT_ROOT / "data" / "ml_ready_v3.csv"

# Load model
with open(MODEL_PATH, 'rb') as f:
    model_pkg = pickle.load(f)

# Load data
df = pd.read_csv(DATA_PATH)

# Segment productivity means (for GROSS-based productivity classification)
SEGMENT_PROD_MEANS_GROSS = {
    'A - shopping premium': 6.27,
    'B - shopping': 7.96,
    'C - street +': 5.68,
    'D - street': 5.55,
    'E - poliklinika': 5.23
}

rx_time_factor = model_pkg.get('rx_time_factor', 0.41)
feature_cols = model_pkg['feature_cols']


def predict_fte_net(row):
    """
    Calculate predicted NET FTE for a single pharmacy.

    CRITICAL: Clips prod_residual to 0 (v5 asymmetric model).
    """
    bloky = row['bloky']
    podiel_rx = row['podiel_rx']

    # Build features
    features = {col: row.get(col, 0) for col in feature_cols}
    features['effective_bloky'] = bloky * (1 + rx_time_factor * podiel_rx)

    # CRITICAL: Clip prod_residual to 0 (v5 asymmetric model)
    # Negative productivity should NOT reduce FTE recommendation
    features['prod_residual'] = max(0, features.get('prod_residual', 0))

    # Create feature vector and predict
    X = pd.DataFrame([{col: features.get(col, 0) for col in feature_cols}])
    fte_net = model_pkg['models']['fte'].predict(X)[0]

    return max(0.5, fte_net)  # Minimum 0.5 FTE


def calculate_revenue_at_risk(predicted_fte, actual_fte, trzby, is_above_avg):
    """
    Calculate revenue at risk from understaffing.

    Uses UNROUNDED values for accurate calculation.
    Only applies to above-average productivity pharmacies that are understaffed.
    """
    if not is_above_avg or predicted_fte <= actual_fte or trzby <= 0 or actual_fte <= 0:
        return 0

    # Use actual values, not rounded (more accurate)
    overload_ratio = predicted_fte / actual_fte
    return int((overload_ratio - 1) * 0.5 * trzby)


# Calculate predictions for all pharmacies
print(f"Processing {len(df)} pharmacies...")
print(f"Using SINGLE SOURCE OF TRUTH: GROSS = NET + fte_n")

results = []
for idx, row in df.iterrows():
    # 1. Predict NET FTE (with prod_residual clipping)
    predicted_net = predict_fte_net(row)

    # 2. Get fte_n (absence FTE)
    fte_n = row.get('fte_n', 0)

    # 3. GROSS = NET + fte_n (single source of truth)
    predicted_gross = predicted_net + fte_n
    actual_gross = row['fte'] + fte_n

    # 4. Calculate gap (positive = understaffed) - UNROUNDED for accurate filtering
    fte_gap_unrounded = predicted_gross - actual_gross
    fte_diff = round(actual_gross - predicted_gross, 1)  # Legacy (rounded, opposite sign)

    # 5. GROSS-based productivity classification
    produktivita_gross = row.get('produktivita_gross', row.get('produktivita', 0))
    segment_avg = SEGMENT_PROD_MEANS_GROSS.get(row['typ'], 6.0)
    is_above_avg = produktivita_gross > segment_avg

    # 6. Revenue at risk
    rev_at_risk = calculate_revenue_at_risk(
        predicted_gross, actual_gross, row['trzby'], is_above_avg
    )

    results.append({
        'predicted_fte_net': round(predicted_net, 2),
        'predicted_fte': round(predicted_gross, 1),
        'actual_fte_gross': round(actual_gross, 1),
        'fte_diff': fte_diff,
        'fte_gap_raw': fte_gap_unrounded,  # Unrounded for accurate filtering
        'revenue_at_risk': rev_at_risk,
        'is_above_avg_gross': is_above_avg
    })

# Update dataframe
df['predicted_fte_net'] = [r['predicted_fte_net'] for r in results]
df['predicted_fte'] = [r['predicted_fte'] for r in results]
df['actual_fte_gross'] = [r['actual_fte_gross'] for r in results]
df['fte_diff'] = [r['fte_diff'] for r in results]
df['revenue_at_risk'] = [r['revenue_at_risk'] for r in results]
df['is_above_avg_gross'] = [r['is_above_avg_gross'] for r in results]

# Also update legacy columns for compatibility
df['fte_actual'] = df['actual_fte_gross']
df['fte_recommended'] = df['predicted_fte']
# Use UNROUNDED fte_gap for accurate urgent pharmacy identification
df['fte_gap'] = [r['fte_gap_raw'] for r in results]
df['revenue_at_risk_eur'] = df['revenue_at_risk']

# Save
df.to_csv(DATA_PATH, index=False)
print(f"Updated {DATA_PATH}")

# Summary
understaffed = df[df['fte_diff'] < -0.5]
overstaffed = df[df['fte_diff'] > 0.5]
print(f"\nSummary:")
print(f"  Total pharmacies: {len(df)}")
print(f"  Understaffed (gap > 0.5): {len(understaffed)}")
print(f"  Overstaffed (gap < -0.5): {len(overstaffed)}")
print(f"  Total revenue at risk: EUR {df['revenue_at_risk'].sum():,.0f}")

# Verification
print(f"\nVerification (first 5 pharmacies):")
print(f"{'ID':>5} | {'fte':>6} | {'fte_n':>6} | {'actual':>7} | {'pred_net':>8} | {'predicted':>9} | {'gap':>6}")
print("-" * 65)
for idx, row in df.head(5).iterrows():
    print(f"{row['id']:>5} | {row['fte']:>6.2f} | {row['fte_n']:>6.2f} | {row['actual_fte_gross']:>7.1f} | {row['predicted_fte_net']:>8.2f} | {row['predicted_fte']:>9.1f} | {row['fte_gap']:>+6.1f}")
