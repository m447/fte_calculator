"""
Update CSV to use GROSS FTE instead of NET FTE.
This script updates:
- actual_fte_gross: GROSS actual FTE (using pharmacy-specific factors)
- fte_diff: recalculated using GROSS values
- revenue_at_risk: recalculated using GROSS values
"""

import pandas as pd
import json
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "ml_ready_v3.csv"
GROSS_FACTORS_PATH = PROJECT_ROOT / "data" / "gross_factors.json"

# Load data
df = pd.read_csv(DATA_PATH)

# Load gross factors
with open(GROSS_FACTORS_PATH, 'r') as f:
    gross_factors_data = json.load(f)
PHARMACY_GROSS_FACTORS = {int(k): v for k, v in gross_factors_data['factors'].items()}

# Type-based gross conversion factors (fallback)
GROSS_CONVERSION = {
    'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
    'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
    'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
    'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
    'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
}

# Segment productivity means (for revenue at risk calculation)
SEGMENT_PROD_MEANS = {
    'A - shopping premium': 7.25,
    'B - shopping': 9.14,
    'C - street +': 6.85,
    'D - street': 6.44,
    'E - poliklinika': 6.11
}


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


def calculate_revenue_at_risk(predicted_fte, actual_fte, trzby, produktivita, typ):
    """Calculate revenue at risk from understaffing."""
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


# Process all pharmacies
print(f"Processing {len(df)} pharmacies using GROSS FTE...")

results = []
for idx, row in df.iterrows():
    actual_gross = calculate_gross_actual_fte(row)
    predicted = row['predicted_fte']  # Keep existing predicted FTE
    fte_diff = round(actual_gross - predicted, 1)
    rev_at_risk = calculate_revenue_at_risk(
        predicted, actual_gross, row['trzby'], row['produktivita'], row['typ']
    )
    results.append({
        'actual_fte_gross': actual_gross,
        'fte_diff': fte_diff,
        'revenue_at_risk': rev_at_risk
    })

# Update dataframe
df['actual_fte_gross'] = [r['actual_fte_gross'] for r in results]
df['fte_diff'] = [r['fte_diff'] for r in results]
df['revenue_at_risk'] = [r['revenue_at_risk'] for r in results]

# Save
df.to_csv(DATA_PATH, index=False)
print(f"Updated {DATA_PATH}")

# Summary
understaffed = df[df['fte_diff'] < -0.5]
print(f"\nSummary:")
print(f"  Total pharmacies: {len(df)}")
print(f"  Understaffed (diff < -0.5): {len(understaffed)}")
print(f"  Total revenue at risk: €{df['revenue_at_risk'].sum():,.0f}")

# Verify ID 300
row300 = df[df['id'] == 300].iloc[0]
print(f"\nID 300 verification:")
print(f"  actual_fte_gross: {row300['actual_fte_gross']}")
print(f"  predicted_fte: {row300['predicted_fte']}")
print(f"  fte_diff: {row300['fte_diff']}")
print(f"  revenue_at_risk: €{row300['revenue_at_risk']:,}")
