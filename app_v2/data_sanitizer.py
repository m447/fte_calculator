"""
Data Sanitizer for Agent SDK
Creates indexed/relative values to protect proprietary productivity formulas.

Refactored to use shared business logic from app_v2.core for consistency.
"""

import pandas as pd
import warnings
from pathlib import Path

# Import from shared core module (single source of truth)
from app_v2.core import (
    SEGMENT_PROPORTIONS,
    GROSS_CONVERSION,
    SEGMENT_PROD_MEANS,
    get_gross_factors,
    prepare_fte_dataframe,
    load_model,
    get_model,
    validate_pharmacy_dataframe,
    DataValidationError,
)
from app_v2.config import PROJECT_ROOT, DATA_DIR, logger


# ============================================================
# DATA LOADING
# ============================================================

def load_raw_data(data_path: Path = None) -> pd.DataFrame:
    """Load and validate raw pharmacy data."""
    if data_path is None:
        data_path = DATA_DIR

    df = pd.read_csv(data_path / 'ml_ready_v3.csv')

    # Validate the loaded data
    try:
        validate_pharmacy_dataframe(df)
    except DataValidationError as e:
        logger.warning(f"Data validation warning in load_raw_data: {e}")
        # Don't fail - just warn (data_sanitizer may work with partial data)

    return df


# ============================================================
# SANITIZATION LOGIC (Indexing/Relative Values)
# ============================================================

def calculate_productivity_index(row: pd.Series) -> int:
    """
    Convert raw productivity to index where 100 = segment average.
    Example: productivity 8.2 in segment with avg 7.5 → index 109
    """
    segment_avg = SEGMENT_PROD_MEANS.get(row['typ'], 7.0)
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

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
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

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        df = df.groupby('typ', group_keys=False).apply(percentile_in_segment)
    return df


# ============================================================
# MAIN SANITIZATION FUNCTION
# ============================================================

def generate_sanitized_data(data_path: Path = None, output_path: Path = None) -> pd.DataFrame:
    """
    Generate sanitized dataset with indexed values.

    Uses shared business logic from app_v2.core to ensure consistency
    with the main API server.

    Protected (removed/indexed):
    - produktivita → productivity_index (100 = segment avg)
    - prod_residual → removed (but used internally for revenue_at_risk)
    - naklady → removed
    - All coefficients → never included

    Exposed (safe):
    - id, mesto, region_code, typ
    - fte values (actual staffing)
    - trzby, bloky (volume metrics)
    - podiel_rx, bloky_trend
    - Calculated: fte_recommended, fte_gap, revenue_at_risk (fresh from model)
    """
    if data_path is None:
        data_path = DATA_DIR

    # Load raw data
    df = load_raw_data(data_path)

    # Load model if not already loaded
    try:
        get_model()
    except RuntimeError:
        load_model(PROJECT_ROOT)

    # Use shared FTE calculation logic from core.py
    df = prepare_fte_dataframe(df, include_revenue_at_risk=True)

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

    # Select only safe columns (using fresh calculations from core.py)
    safe_columns = [
        'id', 'mesto', 'region_code', 'typ',
        'actual_fte', 'fte_F', 'fte_L', 'fte_ZF',  # GROSS FTE (calculated)
        'trzby', 'bloky', 'podiel_rx',
        'bloky_trend',
        # Indexed/relative values (safe)
        'productivity_index',
        'productivity_percentile',
        'productivity_vs_segment',
        'peer_rank_str',
        'bloky_index',
        'trzby_index',
        # Fresh predictions (from model via core.py)
        'predicted_fte',
        'fte_gap',
        'revenue_at_risk'
    ]

    sanitized = df[safe_columns].copy()

    # Rename for clarity - use explicit names to avoid AI confusion
    sanitized = sanitized.rename(columns={
        'peer_rank_str': 'peer_rank',
        'actual_fte': 'fte_actual',          # Rename to match expected column name
        'predicted_fte': 'fte_recommended',  # Clear: this is FTE recommendation
        'fte_gap': 'fte_gap',                # Positive = understaffed (from core.py)
        'revenue_at_risk': 'revenue_at_risk_eur'  # Clear: in EUR
    })

    # Round FTE values for output (same as server.py)
    sanitized['fte_actual'] = sanitized['fte_actual'].round(1)
    sanitized['fte_recommended'] = sanitized['fte_recommended'].round(1)
    sanitized['fte_gap'] = sanitized['fte_gap'].round(1)

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
