"""
Update CSV to use GROSS FTE instead of NET FTE.
Uses the simpler formula: GROSS FTE = fte + fte_n (neprítomnosť)

This script updates:
- fte_n: absence FTE (from all.csv)
- actual_fte_gross: GROSS actual FTE (fte + fte_n)
- fte_diff: recalculated using GROSS values
- revenue_at_risk: recalculated using GROSS values
- hospital_supply: flag for E pharmacies serving hospital supply chain
"""

import pandas as pd
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "ml_ready_v3.csv"
ALL_CSV_PATH = PROJECT_ROOT / "data" / "raw" / "all.csv"

# Segment productivity means (for revenue at risk calculation)
SEGMENT_PROD_MEANS = {
    'A - shopping premium': 7.25,
    'B - shopping': 9.14,
    'C - street +': 6.85,
    'D - street': 6.44,
    'E - poliklinika': 6.11
}


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


# Load main data
df = pd.read_csv(DATA_PATH)

# Load all.csv to get fte_n (neprítomnosť)
all_df = pd.read_csv(ALL_CSV_PATH)
fte_n_map = dict(zip(all_df['id'], all_df['fte_n']))

print(f"Processing {len(df)} pharmacies using GROSS FTE (fte + fte_n)...")

# Add fte_n and calculate gross FTE
df['fte_n'] = df['id'].map(fte_n_map).fillna(0)
df['actual_fte_gross'] = (df['fte'] + df['fte_n']).round(1)

# NOTE: hospital_supply flag is set separately based on server's FTE calculation
# (uses gross factors method, not fte + fte_n) - see below after fte_diff calculation
# Flag is set for E pharmacies appearing in PREBYTOK list with surplus > 0.5 FTE

# Recalculate fte_diff and revenue_at_risk
results = []
for idx, row in df.iterrows():
    actual_gross = row['actual_fte_gross']
    predicted = row['predicted_fte']
    fte_diff = round(actual_gross - predicted, 1)
    rev_at_risk = calculate_revenue_at_risk(
        predicted, actual_gross, row['trzby'], row['produktivita'], row['typ']
    )
    results.append({
        'fte_diff': fte_diff,
        'revenue_at_risk': rev_at_risk
    })

df['fte_diff'] = [r['fte_diff'] for r in results]
df['revenue_at_risk'] = [r['revenue_at_risk'] for r in results]

# Also update fte_actual to match actual_fte_gross
df['fte_actual'] = df['actual_fte_gross']
df['fte_gap'] = df['fte_recommended'] - df['fte_actual']
df['revenue_at_risk_eur'] = df['revenue_at_risk']

# Save
df.to_csv(DATA_PATH, index=False)
print(f"Updated {DATA_PATH}")

# Summary
understaffed = df[df['fte_diff'] < -0.5]
e_pharmacies = df[df['hospital_supply']]
print(f"\nSummary:")
print(f"  Total pharmacies: {len(df)}")
print(f"  Understaffed (diff < -0.5): {len(understaffed)}")
print(f"  E pharmacies (hospital supply): {len(e_pharmacies)}")
print(f"  Total revenue at risk: €{df['revenue_at_risk'].sum():,.0f}")

# Verify a few examples
print(f"\nExample calculations (fte + fte_n = gross):")
for id in [67, 300, 3]:
    if id in df['id'].values:
        row = df[df['id'] == id].iloc[0]
        print(f"  ID {id}: {row['fte']:.2f} + {row['fte_n']:.2f} = {row['actual_fte_gross']:.1f} (hospital: {row['hospital_supply']})")
