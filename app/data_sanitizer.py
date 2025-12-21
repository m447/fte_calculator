"""
Data Sanitizer for Agent SDK
Creates indexed/relative values to protect proprietary productivity formulas.
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Segment productivity averages (used for indexing, not exposed)
SEGMENT_PRODUCTIVITY_AVG = {
    'A - shopping premium': 7.53,
    'B - shopping': 9.14,
    'C - street +': 7.12,
    'D - street': 6.83,
    'E - poliklinika': 6.51
}


def load_raw_data(data_path: Path) -> pd.DataFrame:
    """Load raw pharmacy data."""
    return pd.read_csv(data_path / 'ml_ready_v3.csv')


def calculate_productivity_index(row: pd.Series) -> int:
    """
    Convert raw productivity to index where 100 = segment average.
    Example: productivity 8.2 in segment with avg 7.5 → index 109
    """
    segment_avg = SEGMENT_PRODUCTIVITY_AVG.get(row['typ'], 7.0)
    if segment_avg == 0:
        return 100
    index = int(round((row['produktivita'] / segment_avg) * 100))
    return max(50, min(150, index))  # Clamp to 50-150 range


def calculate_peer_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate percentile rank within segment."""
    df = df.copy()

    def rank_in_segment(group):
        # Rank by productivity (higher = better rank)
        group['peer_rank'] = group['produktivita'].rank(ascending=False, method='min').astype(int)
        group['segment_count'] = len(group)
        return group

    df = df.groupby('typ', group_keys=False).apply(rank_in_segment)
    df['peer_rank_str'] = df['peer_rank'].astype(str) + '/' + df['segment_count'].astype(str)

    return df


def calculate_percentile(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate percentile within segment."""
    df = df.copy()

    def percentile_in_segment(group):
        group['productivity_percentile'] = (
            group['produktivita'].rank(pct=True) * 100
        ).round().astype(int)
        return group

    df = df.groupby('typ', group_keys=False).apply(percentile_in_segment)
    return df


def generate_sanitized_data(data_path: Path, output_path: Path = None) -> pd.DataFrame:
    """
    Generate sanitized dataset with indexed values.

    Protected (removed/indexed):
    - produktivita → productivity_index (100 = segment avg)
    - prod_residual → removed
    - naklady → removed
    - All coefficients → never included

    Exposed (safe):
    - id, mesto, region_code, typ
    - fte values (actual staffing)
    - trzby, bloky (volume metrics)
    - podiel_rx, bloky_trend
    - Calculated: fte_recommended, fte_diff, revenue_at_risk
    """
    df = load_raw_data(data_path)

    # Calculate productivity index
    df['productivity_index'] = df.apply(calculate_productivity_index, axis=1)

    # Calculate peer rankings
    df = calculate_peer_rank(df)
    df = calculate_percentile(df)

    # Calculate bloky index (100 = segment avg)
    segment_bloky_avg = df.groupby('typ')['bloky'].transform('mean')
    df['bloky_index'] = ((df['bloky'] / segment_bloky_avg) * 100).round().astype(int)

    # Calculate trzby index
    segment_trzby_avg = df.groupby('typ')['trzby'].transform('mean')
    df['trzby_index'] = ((df['trzby'] / segment_trzby_avg) * 100).round().astype(int)

    # Productivity comparison text
    df['productivity_vs_segment'] = df['productivity_index'].apply(
        lambda x: 'nadpriemerná' if x > 105 else ('podpriemerná' if x < 95 else 'priemerná')
    )

    # Select only safe columns
    safe_columns = [
        'id', 'mesto', 'region_code', 'typ',
        'fte', 'fte_F', 'fte_L', 'fte_ZF',
        'trzby', 'bloky', 'podiel_rx',
        'bloky_trend',
        # Indexed/relative values (safe)
        'productivity_index',
        'productivity_percentile',
        'productivity_vs_segment',
        'peer_rank_str',
        'bloky_index',
        'trzby_index'
    ]

    sanitized = df[safe_columns].copy()

    # Rename for clarity
    sanitized = sanitized.rename(columns={
        'fte': 'fte_actual',
        'peer_rank_str': 'peer_rank'
    })

    if output_path:
        sanitized.to_csv(output_path, index=False)
        print(f"Sanitized data saved to {output_path}")

    return sanitized


def get_sanitized_pharmacy(pharmacy_id: int, data_path: Path) -> dict:
    """Get sanitized data for a single pharmacy."""
    df = generate_sanitized_data(data_path)
    pharmacy = df[df['id'] == pharmacy_id]

    if pharmacy.empty:
        return None

    return pharmacy.iloc[0].to_dict()


def get_understaffed_pharmacies(
    data_path: Path,
    predictions_df: pd.DataFrame,
    region: str = None,
    min_gap: float = -0.5
) -> list:
    """
    Get understaffed pharmacies with sanitized data.

    Args:
        data_path: Path to data directory
        predictions_df: DataFrame with fte_actual, predicted_fte, diff columns
        region: Optional region filter (e.g., 'RR15')
        min_gap: Minimum FTE gap to consider understaffed (default -0.5)

    Returns:
        List of sanitized pharmacy dicts with staffing gaps
    """
    sanitized = generate_sanitized_data(data_path)

    # Merge with predictions
    merged = sanitized.merge(
        predictions_df[['id', 'predicted_fte', 'diff', 'revenue_at_risk']],
        on='id',
        how='left'
    )

    # Filter understaffed
    understaffed = merged[merged['diff'] < min_gap].copy()

    # Filter by region if specified
    if region:
        understaffed = understaffed[understaffed['region_code'] == region]

    # Sort by gap (most understaffed first)
    understaffed = understaffed.sort_values('diff')

    # Round numeric values
    understaffed['predicted_fte'] = understaffed['predicted_fte'].round(1)
    understaffed['diff'] = understaffed['diff'].round(1)
    understaffed['revenue_at_risk'] = understaffed['revenue_at_risk'].round(0)

    return understaffed.to_dict('records')


def compare_to_peers(
    pharmacy_id: int,
    data_path: Path,
    predictions_df: pd.DataFrame,
    n_peers: int = 5
) -> dict:
    """
    Compare pharmacy to similar peers using indexed values.

    Returns comparison with:
    - Target pharmacy (sanitized)
    - N most similar peers by bloky volume
    - All using indexed productivity (no raw values)
    """
    sanitized = generate_sanitized_data(data_path)

    # Merge with predictions
    merged = sanitized.merge(
        predictions_df[['id', 'predicted_fte', 'diff', 'revenue_at_risk']],
        on='id',
        how='left'
    )

    # Get target pharmacy
    target = merged[merged['id'] == pharmacy_id]
    if target.empty:
        return None

    target = target.iloc[0]

    # Find peers in same segment
    same_segment = merged[merged['typ'] == target['typ']]

    # Find similar by bloky (within 20%)
    bloky_range = target['bloky'] * 0.2
    peers = same_segment[
        (same_segment['bloky'] >= target['bloky'] - bloky_range) &
        (same_segment['bloky'] <= target['bloky'] + bloky_range) &
        (same_segment['id'] != pharmacy_id)
    ]

    # Sort by bloky similarity
    peers['bloky_diff'] = abs(peers['bloky'] - target['bloky'])
    peers = peers.sort_values('bloky_diff').head(n_peers)

    return {
        'target': target.to_dict(),
        'peers': peers.drop(columns=['bloky_diff']).to_dict('records'),
        'segment': target['typ'],
        'comparison_note': f"Porovnanie s {len(peers)} lekárňami s podobným objemom ({int(target['bloky']/1000)}k ± 20% blokov)"
    }


if __name__ == '__main__':
    # Test the sanitizer
    data_path = Path(__file__).parent.parent / 'data'
    output_path = data_path / 'agent_safe.csv'

    df = generate_sanitized_data(data_path, output_path)
    print(f"\nSanitized {len(df)} pharmacies")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nSample row:\n{df.iloc[0].to_dict()}")
