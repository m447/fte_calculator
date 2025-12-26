#!/usr/bin/env python3
"""
Pre-compute all derived fields for the agent.
Run this script once to add computed columns to ml_ready_v3.csv.

This eliminates the need for runtime calculations, making agent queries instant.
"""

import pandas as pd
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Segment productivity averages (from core.py)
SEGMENT_PROD_MEANS = {
    'A - poliklinika': 8.5,
    'B - shopping': 7.8,
    'C - street velka': 7.2,
    'D - street': 6.8,
    'E - street mala': 6.0
}


def precompute_fields(input_path: Path, output_path: Path = None):
    """Add pre-computed fields to CSV."""

    print(f"Loading data from {input_path}...")
    df = pd.read_csv(input_path)
    print(f"Loaded {len(df)} pharmacies")

    # === PRODUCTIVITY INDEX ===
    # 100 = segment average, based on produktivita field
    print("Computing productivity_index...")
    df['productivity_index'] = df.apply(
        lambda row: int(round(
            (row['produktivita'] / SEGMENT_PROD_MEANS.get(row['typ'], 7.0)) * 100
        )), axis=1
    )
    # Clamp to 50-150 range
    df['productivity_index'] = df['productivity_index'].clip(50, 150)

    # === PRODUCTIVITY PERCENTILE ===
    # Percentile within segment (0-100)
    print("Computing productivity_percentile...")
    df['productivity_percentile'] = df.groupby('typ')['produktivita'].transform(
        lambda x: (x.rank(pct=True) * 100).round().astype(int)
    )

    # === PRODUCTIVITY VS SEGMENT ===
    # Text description
    print("Computing productivity_vs_segment...")
    df['productivity_vs_segment'] = df['productivity_index'].apply(
        lambda x: 'nadpriemerná' if x > 105 else ('podpriemerná' if x < 95 else 'priemerná')
    )

    # === PEER RANK STRING ===
    # "X/Y" format - rank within segment by productivity
    print("Computing peer_rank_str...")
    df['peer_rank'] = df.groupby('typ')['produktivita'].transform(
        lambda x: x.rank(ascending=False, method='min').astype(int)
    )
    df['segment_count'] = df.groupby('typ')['id'].transform('count')
    df['peer_rank_str'] = df['peer_rank'].astype(str) + '/' + df['segment_count'].astype(str)

    # === BLOKY INDEX ===
    # 100 = segment average
    print("Computing bloky_index...")
    segment_bloky_avg = df.groupby('typ')['bloky'].transform('mean')
    df['bloky_index'] = ((df['bloky'] / segment_bloky_avg) * 100).round().astype(int)

    # === TRZBY INDEX ===
    # 100 = segment average
    print("Computing trzby_index...")
    segment_trzby_avg = df.groupby('typ')['trzby'].transform('mean')
    df['trzby_index'] = ((df['trzby'] / segment_trzby_avg) * 100).round().astype(int)

    # === RENAME COLUMNS FOR AGENT ===
    # These columns already exist, just rename for clarity
    print("Renaming columns...")
    if 'actual_fte_gross' in df.columns:
        df['fte_actual'] = df['actual_fte_gross'].round(1)
    if 'predicted_fte' in df.columns:
        df['fte_recommended'] = df['predicted_fte'].round(1)
    if 'fte_diff' in df.columns:
        df['fte_gap'] = df['fte_diff'].round(1)
    if 'revenue_at_risk' in df.columns:
        df['revenue_at_risk_eur'] = df['revenue_at_risk'].astype(int)

    # Drop temporary columns
    df = df.drop(columns=['peer_rank', 'segment_count'], errors='ignore')

    # Save
    output_path = output_path or input_path
    print(f"Saving to {output_path}...")
    df.to_csv(output_path, index=False)

    # Print summary
    print("\n=== SUMMARY ===")
    print(f"Total pharmacies: {len(df)}")
    print(f"\nNew columns added:")
    new_cols = ['productivity_index', 'productivity_percentile', 'productivity_vs_segment',
                'peer_rank_str', 'bloky_index', 'trzby_index',
                'fte_actual', 'fte_recommended', 'fte_gap', 'revenue_at_risk_eur']
    for col in new_cols:
        if col in df.columns:
            print(f"  - {col}: {df[col].dtype}")

    print("\n=== SAMPLE DATA ===")
    print(df[['id', 'mesto', 'typ', 'productivity_index', 'peer_rank_str', 'fte_gap']].head(5))

    return df


if __name__ == '__main__':
    data_path = PROJECT_ROOT / 'data' / 'ml_ready_v3.csv'
    precompute_fields(data_path)
    print("\nDone! CSV updated with pre-computed fields.")
