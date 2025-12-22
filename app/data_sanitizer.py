"""
Data Sanitizer for Agent SDK
Creates indexed/relative values to protect proprietary productivity formulas.

Now uses the same ML model and pharmacy-specific gross factors as server.py
to ensure consistent FTE predictions and revenue_at_risk calculations.
"""

import pandas as pd
import numpy as np
import pickle
import json
from pathlib import Path

# Segment productivity averages (used for indexing, not exposed)
SEGMENT_PRODUCTIVITY_AVG = {
    'A - shopping premium': 7.53,
    'B - shopping': 9.14,
    'C - street +': 7.12,
    'D - street': 6.83,
    'E - poliklinika': 6.51
}

# Type-based gross conversion factors (fallback if no pharmacy-specific factors)
TYPE_GROSS_CONVERSION = {
    'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
    'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
    'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
    'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
    'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23}
}

# Segment proportions for FTE breakdown (must match server.py lines 160-166)
SEGMENT_PROPORTIONS = {
    'A - shopping premium': {'prop_F': 0.4149, 'prop_L': 0.5350, 'prop_ZF': 0.1037},
    'B - shopping': {'prop_F': 0.3759, 'prop_L': 0.4470, 'prop_ZF': 0.1547},
    'C - street +': {'prop_F': 0.3488, 'prop_L': 0.3563, 'prop_ZF': 0.2699},
    'D - street': {'prop_F': 0.2942, 'prop_L': 0.3659, 'prop_ZF': 0.2990},
    'E - poliklinika': {'prop_F': 0.4715, 'prop_L': 0.3734, 'prop_ZF': 0.2243},
}


def load_raw_data(data_path: Path) -> pd.DataFrame:
    """Load raw pharmacy data."""
    return pd.read_csv(data_path / 'ml_ready_v3.csv')


def load_model_and_factors(data_path: Path) -> tuple:
    """
    Load ML model and pharmacy-specific gross factors.

    Returns:
        tuple: (model_pkg, pharmacy_gross_factors)
    """
    # Get project root (parent of data directory)
    project_root = data_path.parent

    # Load ML model
    model_path = project_root / 'models' / 'fte_model_v5.pkl'
    with open(model_path, 'rb') as f:
        model_pkg = pickle.load(f)

    # Load pharmacy-specific gross factors
    gross_factors_path = data_path / 'gross_factors.json'
    with open(gross_factors_path, 'r') as f:
        gross_factors_data = json.load(f)

    pharmacy_gross_factors = {int(k): v for k, v in gross_factors_data['factors'].items()}

    return model_pkg, pharmacy_gross_factors


def calculate_fte_predictions(df: pd.DataFrame, model_pkg: dict, pharmacy_gross_factors: dict) -> pd.DataFrame:
    """
    Calculate FTE predictions using the same logic as server.py.

    This ensures consistency between the agent and the main app.
    """
    df = df.copy()

    # Get model parameters
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)
    feature_cols = model_pkg['feature_cols']

    # Get proportions from model (same as server.py line 160)
    # This ensures we use the same source of truth as the app
    segment_proportions = model_pkg.get('proportions', SEGMENT_PROPORTIONS)

    # Calculate effective_bloky (same as server.py)
    df['effective_bloky'] = df['bloky'] * (1 + rx_time_factor * df['podiel_rx'])

    # Apply asymmetric prod_residual (v5: only positive values count, negative clipped to 0)
    # This matches how the model was trained (server.py line 600-601)
    df['prod_residual'] = df['prod_residual'].clip(lower=0)

    # Build feature matrix
    X = pd.DataFrame([{col: row.get(col, 0) for col in feature_cols}
                      for _, row in df.iterrows()])

    # Predict NET FTE
    df['predicted_fte_net'] = model_pkg['models']['fte'].predict(X)

    def calc_gross_fte_predicted(row):
        """Calculate predicted GROSS FTE using pharmacy-specific factors."""
        pharmacy_id = int(row['id'])
        typ = row['typ']
        fte_net = row['predicted_fte_net']

        # Get segment proportions (from model or fallback)
        props = segment_proportions.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})

        # Get conversion factors (pharmacy-specific or type-based)
        if pharmacy_id in pharmacy_gross_factors:
            conv = pharmacy_gross_factors[pharmacy_id]
        else:
            conv = TYPE_GROSS_CONVERSION.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})

        # Calculate gross FTE by role (no rounding here - same as server.py)
        fte_F = fte_net * props['prop_F'] * conv['F']
        fte_L = fte_net * props['prop_L'] * conv['L']
        fte_ZF = fte_net * props['prop_ZF'] * conv['ZF']

        return fte_F + fte_L + fte_ZF  # No rounding - diff calculated from unrounded values

    def calc_gross_fte_actual(row):
        """Calculate actual GROSS FTE using pharmacy-specific factors."""
        pharmacy_id = int(row['id'])
        typ = row['typ']

        # Get conversion factors (pharmacy-specific or type-based)
        if pharmacy_id in pharmacy_gross_factors:
            conv = pharmacy_gross_factors[pharmacy_id]
        else:
            conv = TYPE_GROSS_CONVERSION.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})

        # Calculate using actual role breakdown (no rounding - same as server.py)
        fte_F = row['fte_F'] * conv['F']
        fte_L = row['fte_L'] * conv['L']
        fte_ZF = row['fte_ZF'] * conv['ZF']

        return fte_F + fte_L + fte_ZF  # No rounding - diff calculated from unrounded values

    # Calculate gross FTE values
    df['predicted_fte_gross'] = df.apply(calc_gross_fte_predicted, axis=1)
    df['actual_fte_gross_calc'] = df.apply(calc_gross_fte_actual, axis=1)

    # Calculate FTE diff (positive = understaffed, same as server.py)
    df['fte_diff_calc'] = df['predicted_fte_gross'] - df['actual_fte_gross_calc']

    # Calculate revenue at risk (same logic as server.py)
    def calc_revenue_at_risk(row):
        """Calculate revenue at risk for understaffed + productive pharmacies."""
        predicted = row['predicted_fte_gross']
        actual = row['actual_fte_gross_calc']
        trzby = row['trzby']
        is_above_avg = row['prod_residual'] > 0  # Same condition as server.py

        # Only calculate for understaffed + productive pharmacies
        if predicted <= actual or trzby <= 0 or not is_above_avg:
            return 0

        # Use rounded values (same as server.py line 713-717)
        predicted_rounded = round(predicted, 1)
        actual_rounded = round(actual, 1)

        if predicted_rounded <= actual_rounded:
            return 0

        overload_ratio = predicted_rounded / actual_rounded if actual_rounded > 0 else 1
        revenue_at_risk = int((overload_ratio - 1) * 0.5 * trzby)

        return revenue_at_risk

    df['revenue_at_risk_calc'] = df.apply(calc_revenue_at_risk, axis=1)

    return df


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

    import warnings
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

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        df = df.groupby('typ', group_keys=False).apply(percentile_in_segment)
    return df


def generate_sanitized_data(data_path: Path, output_path: Path = None) -> pd.DataFrame:
    """
    Generate sanitized dataset with indexed values.

    Now uses the same ML model and pharmacy-specific gross factors as server.py
    to ensure consistent FTE predictions and revenue_at_risk calculations.

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
    df = load_raw_data(data_path)

    # Load model and pharmacy-specific factors
    model_pkg, pharmacy_gross_factors = load_model_and_factors(data_path)

    # Calculate FTE predictions using same logic as server.py
    df = calculate_fte_predictions(df, model_pkg, pharmacy_gross_factors)

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

    # Select only safe columns (now using fresh calculations, not CSV values)
    safe_columns = [
        'id', 'mesto', 'region_code', 'typ',
        'actual_fte_gross_calc', 'fte_F', 'fte_L', 'fte_ZF',  # GROSS FTE (calculated)
        'trzby', 'bloky', 'podiel_rx',
        'bloky_trend',
        # Indexed/relative values (safe)
        'productivity_index',
        'productivity_percentile',
        'productivity_vs_segment',
        'peer_rank_str',
        'bloky_index',
        'trzby_index',
        # Fresh predictions (from model, not CSV)
        'predicted_fte_gross',
        'fte_diff_calc',
        'revenue_at_risk_calc'
    ]

    sanitized = df[safe_columns].copy()

    # Rename for clarity - use explicit names to avoid AI confusion
    sanitized = sanitized.rename(columns={
        'actual_fte_gross_calc': 'fte_actual',    # GROSS FTE (same as main UI)
        'peer_rank_str': 'peer_rank',
        'predicted_fte_gross': 'fte_recommended',  # Clear: this is FTE recommendation
        'fte_diff_calc': 'fte_gap',               # Clear: positive = understaffed (same as server.py)
        'revenue_at_risk_calc': 'revenue_at_risk_eur'  # Clear: in EUR
    })

    # Round FTE values for output (same as server.py line 693-695)
    sanitized['fte_actual'] = sanitized['fte_actual'].round(1)
    sanitized['fte_recommended'] = sanitized['fte_recommended'].round(1)
    sanitized['fte_gap'] = sanitized['fte_gap'].round(1)

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
