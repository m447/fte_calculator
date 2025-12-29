"""
Data Sanitizer for Agent SDK
Loads pre-computed data from CSV - no runtime calculations needed.

All derived fields (productivity_index, peer_rank, etc.) are pre-computed
by scripts/precompute_agent_fields.py and stored in the CSV.
"""

import pandas as pd
from pathlib import Path

from app_v2.config import DATA_DIR, logger


# ============================================================
# MAIN DATA LOADING FUNCTION
# ============================================================

def generate_sanitized_data(data_path: Path = None, output_path: Path = None) -> pd.DataFrame:
    """
    Load pre-computed sanitized data from CSV.

    All derived fields are pre-computed and stored in ml_ready_v3.csv:
    - productivity_index (100 = segment avg)
    - productivity_percentile (0-100)
    - productivity_vs_segment ("nadpriemerná"/"podpriemerná"/"priemerná")
    - peer_rank_str ("X/Y" format)
    - bloky_index, trzby_index (100 = segment avg)
    - fte_actual, fte_recommended, fte_gap, revenue_at_risk_eur

    NO ML model needed - just reads CSV.
    """
    if data_path is None:
        data_path = DATA_DIR

    # Load pre-computed data
    csv_path = data_path / 'ml_ready_v3.csv'
    logger.info(f"Loading pre-computed data from {csv_path}")
    df = pd.read_csv(csv_path)

    # Select only columns needed by agent
    safe_columns = [
        'id', 'mesto', 'region_code', 'typ',
        'fte_actual', 'fte_F', 'fte_L', 'fte_ZF',
        'trzby', 'bloky', 'podiel_rx',
        'bloky_trend',
        # Pre-computed indexed values
        'productivity_index',
        'productivity_percentile',
        'productivity_vs_segment',
        'peer_rank_str',
        'bloky_index',
        'trzby_index',
        # Pre-computed predictions
        'fte_recommended',
        'fte_gap',
        'revenue_at_risk_eur',
        # Zastup (borrowed staff)
        'zastup',
        'zastup_pct',
        # Above-average productivity flag (GROSS-based, matches app)
        'is_above_avg_gross'
    ]

    # Only select columns that exist (for backwards compatibility)
    available_columns = [col for col in safe_columns if col in df.columns]
    sanitized = df[available_columns].copy()

    # Rename peer_rank_str to peer_rank for backwards compatibility
    if 'peer_rank_str' in sanitized.columns:
        sanitized = sanitized.rename(columns={'peer_rank_str': 'peer_rank'})

    logger.info(f"Loaded {len(sanitized)} pharmacies with {len(sanitized.columns)} columns")

    if output_path:
        sanitized.to_csv(output_path, index=False)
        print(f"Sanitized data saved to {output_path}")

    return sanitized


# ============================================================
# HELPER FUNCTIONS FOR AGENT QUERIES
# ============================================================

def get_sanitized_pharmacy(pharmacy_id: int, data_path: Path = None) -> dict:
    """Get sanitized data for a single pharmacy."""
    df = generate_sanitized_data(data_path)
    pharmacy = df[df['id'] == pharmacy_id]

    if pharmacy.empty:
        return None

    return pharmacy.iloc[0].to_dict()


def get_understaffed_pharmacies(
    data_path: Path = None,
    predictions_df: pd.DataFrame = None,
    region: str = None,
    min_gap: float = -0.5
) -> list:
    """
    Get understaffed pharmacies with sanitized data.

    Args:
        data_path: Path to data directory (optional, defaults to DATA_DIR)
        predictions_df: Optional pre-computed predictions DataFrame
        region: Optional region filter (e.g., 'RR15')
        min_gap: Minimum FTE gap to consider understaffed (default -0.5)

    Returns:
        List of sanitized pharmacy dicts with staffing gaps
    """
    sanitized = generate_sanitized_data(data_path)

    # If predictions_df is provided, merge it (for backward compatibility)
    if predictions_df is not None:
        merged = sanitized.merge(
            predictions_df[['id', 'predicted_fte', 'diff', 'revenue_at_risk']],
            on='id',
            how='left',
            suffixes=('', '_old')
        )
        # Use old column names if they exist
        if 'diff' in merged.columns:
            merged['fte_gap'] = merged['diff']
    else:
        merged = sanitized

    # Filter understaffed
    understaffed = merged[merged['fte_gap'] < min_gap].copy()

    # Filter by region if specified
    if region:
        understaffed = understaffed[understaffed['region_code'] == region]

    # Sort by gap (most understaffed first)
    understaffed = understaffed.sort_values('fte_gap')

    # Round numeric values
    if 'fte_recommended' in understaffed.columns:
        understaffed['fte_recommended'] = understaffed['fte_recommended'].round(1)
    if 'fte_gap' in understaffed.columns:
        understaffed['fte_gap'] = understaffed['fte_gap'].round(1)
    if 'revenue_at_risk_eur' in understaffed.columns:
        understaffed['revenue_at_risk_eur'] = understaffed['revenue_at_risk_eur'].round(0)

    return understaffed.to_dict('records')


def compare_to_peers(
    pharmacy_id: int,
    data_path: Path = None,
    predictions_df: pd.DataFrame = None,
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

    # If predictions_df is provided, merge it (for backward compatibility)
    if predictions_df is not None:
        merged = sanitized.merge(
            predictions_df[['id', 'predicted_fte', 'diff', 'revenue_at_risk']],
            on='id',
            how='left',
            suffixes=('', '_old')
        )
    else:
        merged = sanitized

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


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    # Test the sanitizer
    output_path = DATA_DIR / 'agent_safe.csv'

    df = generate_sanitized_data(output_path=output_path)
    print(f"\nSanitized {len(df)} pharmacies")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nSample row:\n{df.iloc[0].to_dict()}")
