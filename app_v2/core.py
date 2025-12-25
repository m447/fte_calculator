"""
app_v2/core.py - Single Source of Truth for Business Logic

This module centralizes all business logic, constants, and calculations
to ensure consistency between the API server and AI agent.

All FTE calculations, conversion factors, and formulas should be imported
from this module - NEVER duplicated elsewhere.
"""

import pickle
import json
import pandas as pd
from pathlib import Path

# ============================================================
# CONSTANTS - Single Source of Truth
# ============================================================

# Segment proportions for FTE breakdown (F/L/ZF roles)
# Calculated from training data - used for NET to GROSS FTE conversion
SEGMENT_PROPORTIONS = {
    'A - shopping premium': {'prop_F': 0.4149, 'prop_L': 0.5350, 'prop_ZF': 0.1037},
    'B - shopping': {'prop_F': 0.3759, 'prop_L': 0.4470, 'prop_ZF': 0.1547},
    'C - street +': {'prop_F': 0.3488, 'prop_L': 0.3563, 'prop_ZF': 0.2699},
    'D - street': {'prop_F': 0.2942, 'prop_L': 0.3659, 'prop_ZF': 0.2990},
    'E - poliklinika': {'prop_F': 0.4715, 'prop_L': 0.3734, 'prop_ZF': 0.2243},
}

# Type-based GROSS conversion factors (NET to GROSS)
# Used when pharmacy-specific factors are not available
GROSS_CONVERSION = {
    'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
    'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
    'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
    'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
    'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
}
GROSS_CONVERSION_DEFAULT = {'F': 1.21, 'L': 1.22, 'ZF': 1.20}

# Segment productivity means (weighted averages from training data)
# Used for calculating productivity percentage above/below average
SEGMENT_PROD_MEANS = {
    'A - shopping premium': 7.25,
    'B - shopping': 9.14,
    'C - street +': 6.85,
    'D - street': 6.44,
    'E - poliklinika': 6.11
}

# FTE gap thresholds - defines what counts as "notable" vs "significant" gaps
FTE_GAP_NOTABLE = 0.5     # Threshold for counting as understaffed/overstaffed
FTE_GAP_URGENT = 0.5      # Threshold for urgent priority (with productivity check)
FTE_GAP_OPTIMIZE = 0.7    # Threshold for optimize priority (overstaffed)
FTE_GAP_OUTLIER = 1.0     # Threshold for significant outliers

# ============================================================
# MODEL & DATA LOADING
# ============================================================

# Module-level state for loaded model and factors
_model_pkg = None
_pharmacy_gross_factors = None
_network_median_factors = None


def load_model(project_root: Path):
    """
    Load ML model and pharmacy-specific gross factors.

    Must be called once at application startup before using any
    calculation functions.

    Args:
        project_root: Path to project root directory

    Returns:
        dict: The loaded model package
    """
    global _model_pkg, _pharmacy_gross_factors, _network_median_factors

    # Load ML model
    model_path = project_root / 'models' / 'fte_model_v5.pkl'
    with open(model_path, 'rb') as f:
        _model_pkg = pickle.load(f)

    # Load pharmacy-specific gross factors
    gross_factors_path = project_root / 'data' / 'gross_factors.json'
    with open(gross_factors_path, 'r') as f:
        data = json.load(f)
    _pharmacy_gross_factors = {int(k): v for k, v in data['factors'].items()}
    _network_median_factors = data.get('network_medians', GROSS_CONVERSION_DEFAULT)

    return _model_pkg


def get_model():
    """Get the loaded model package."""
    if _model_pkg is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")
    return _model_pkg


def get_rx_time_factor():
    """Get the RX time factor from the model."""
    return get_model().get('rx_time_factor', 0.41)


def get_feature_cols():
    """Get the feature columns used by the model."""
    return get_model()['feature_cols']


# ============================================================
# SHARED HELPER FUNCTIONS
# ============================================================

def get_gross_factors(pharmacy_id, typ):
    """
    Get GROSS conversion factors for a pharmacy.

    Uses pharmacy-specific factors if available (from payroll data),
    otherwise falls back to type-based averages.

    Args:
        pharmacy_id: Pharmacy ID (int or None)
        typ: Pharmacy type (e.g., 'B - shopping')

    Returns:
        dict: {'F': factor, 'L': factor, 'ZF': factor}
    """
    if pharmacy_id is not None and int(pharmacy_id) in _pharmacy_gross_factors:
        return _pharmacy_gross_factors[int(pharmacy_id)]
    return GROSS_CONVERSION.get(typ, GROSS_CONVERSION_DEFAULT)


def is_above_avg_productivity(row):
    """
    Check if pharmacy has above-average productivity.

    Args:
        row: DataFrame row or dict with 'prod_residual' key

    Returns:
        bool: True if productivity is above segment average
    """
    return float(row.get('prod_residual', 0)) > 0


def calculate_prod_pct(row):
    """
    Calculate productivity percentage above/below segment average.

    Args:
        row: DataFrame row or dict with 'prod_residual' and 'typ' keys

    Returns:
        float: Productivity as percentage (e.g., 15 means 15% above average)
    """
    prod_residual = float(row.get('prod_residual', 0))
    typ = row.get('typ', 'D - street')
    segment_mean = SEGMENT_PROD_MEANS.get(typ, 8.0)
    return round(prod_residual / segment_mean * 100, 0)


def calculate_revenue_at_risk(predicted_fte, actual_fte, trzby, is_above_avg):
    """
    Calculate potential revenue at risk due to understaffing.

    Only applies to productive pharmacies (above average) that are understaffed.
    Formula: (Overload_ratio - 1) × 50% × Annual_Revenue

    Args:
        predicted_fte: Model-predicted FTE (GROSS)
        actual_fte: Current actual FTE (GROSS)
        trzby: Annual revenue
        is_above_avg: Whether pharmacy has above-average productivity

    Returns:
        int: Estimated annual revenue at risk (EUR)
    """
    if not actual_fte or predicted_fte <= actual_fte or trzby <= 0 or not is_above_avg:
        return 0

    # Use rounded values for consistency with display
    actual_rounded = round(actual_fte, 1)
    predicted_rounded = round(predicted_fte, 1)

    if predicted_rounded <= actual_rounded:
        return 0

    overload_ratio = predicted_rounded / actual_rounded if actual_rounded > 0 else 1
    return int((overload_ratio - 1) * 0.5 * trzby)


def calculate_pharmacy_fte(row):
    """
    Single source of truth for pharmacy FTE calculation.

    Calculates both predicted and actual GROSS FTE for a single pharmacy,
    applying pharmacy-specific or type-based conversion factors.

    Args:
        row: DataFrame row or dict with pharmacy data

    Returns:
        dict: {
            'predicted_fte': float,
            'predicted_fte_net': float,
            'predicted_fte_F': float,
            'predicted_fte_L': float,
            'predicted_fte_ZF': float,
            'actual_fte': float,
            'actual_fte_F': float,
            'actual_fte_L': float,
            'actual_fte_ZF': float,
            'fte_diff': float,
            'gross_factors': dict,
        }
    """
    pharmacy_id = int(row['id'])
    typ = row['typ']

    # Get conversion factors (pharmacy-specific or type-based)
    conv = get_gross_factors(pharmacy_id, typ)
    props = SEGMENT_PROPORTIONS.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})

    # Build features for prediction
    rx_time_factor = get_rx_time_factor()
    effective_bloky = row['bloky'] * (1 + rx_time_factor * row['podiel_rx'])

    features = {col: row.get(col, 0) for col in get_feature_cols()}
    features['effective_bloky'] = effective_bloky
    # CRITICAL: Clip prod_residual to 0 (v5 asymmetric model)
    features['prod_residual'] = max(0, features.get('prod_residual', 0))

    # Predict NET FTE
    X = pd.DataFrame([features])
    predicted_fte_net = get_model()['models']['fte'].predict(X)[0]

    # Convert predicted NET to GROSS by role
    fte_F_pred = predicted_fte_net * props['prop_F'] * conv['F']
    fte_L_pred = predicted_fte_net * props['prop_L'] * conv['L']
    fte_ZF_pred = predicted_fte_net * props['prop_ZF'] * conv['ZF']
    predicted_fte = fte_F_pred + fte_L_pred + fte_ZF_pred

    # Calculate actual GROSS FTE from role breakdown
    fte_F_actual = float(row['fte_F']) * conv['F']
    fte_L_actual = float(row['fte_L']) * conv['L']
    fte_ZF_actual = float(row['fte_ZF']) * conv['ZF']
    actual_fte = fte_F_actual + fte_L_actual + fte_ZF_actual

    # Calculate difference
    fte_diff = predicted_fte - actual_fte

    return {
        'predicted_fte': predicted_fte,
        'predicted_fte_net': predicted_fte_net,
        'predicted_fte_F': fte_F_pred,
        'predicted_fte_L': fte_L_pred,
        'predicted_fte_ZF': fte_ZF_pred,
        'actual_fte': actual_fte,
        'actual_fte_F': fte_F_actual,
        'actual_fte_L': fte_L_actual,
        'actual_fte_ZF': fte_ZF_actual,
        'fte_diff': fte_diff,
        'gross_factors': conv,
    }


def prepare_fte_dataframe(df, include_revenue_at_risk=True):
    """
    Batch FTE calculation for DataFrames.

    Single source of truth for preparing a DataFrame with all FTE-related
    calculated columns. Used by API endpoints and agent tools.

    Args:
        df: DataFrame with pharmacy data
        include_revenue_at_risk: Whether to calculate revenue_at_risk column

    Returns:
        DataFrame: Copy of input with added columns:
            - effective_bloky
            - predicted_fte_net
            - predicted_fte (GROSS)
            - actual_fte (GROSS)
            - fte_gap
            - prod_pct
            - is_above_avg
            - revenue_at_risk (if include_revenue_at_risk=True)
    """
    df_calc = df.copy()
    rx_time_factor = get_rx_time_factor()

    # 1. Calculate effective_bloky
    df_calc['effective_bloky'] = df_calc['bloky'] * (1 + rx_time_factor * df_calc['podiel_rx'])

    # 2. Clip prod_residual (v5 asymmetric model)
    df_calc['prod_residual'] = df_calc['prod_residual'].clip(lower=0)

    # 3. Build feature matrix and predict
    feature_cols = get_feature_cols()
    X = df_calc[feature_cols].copy()
    X['effective_bloky'] = df_calc['effective_bloky']
    X['prod_residual'] = df_calc['prod_residual']
    df_calc['predicted_fte_net'] = get_model()['models']['fte'].predict(X)

    # 4. Convert NET to GROSS (predicted)
    def calc_predicted_gross(row):
        props = SEGMENT_PROPORTIONS.get(row['typ'], {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})
        conv = get_gross_factors(row['id'], row['typ'])
        return row['predicted_fte_net'] * (
            props['prop_F'] * conv['F'] +
            props['prop_L'] * conv['L'] +
            props['prop_ZF'] * conv['ZF']
        )

    # 5. Calculate actual GROSS
    def calc_actual_gross(row):
        conv = get_gross_factors(row['id'], row['typ'])
        return (
            row['fte_F'] * conv['F'] +
            row['fte_L'] * conv['L'] +
            row['fte_ZF'] * conv['ZF']
        )

    df_calc['predicted_fte'] = df_calc.apply(calc_predicted_gross, axis=1)
    df_calc['actual_fte'] = df_calc.apply(calc_actual_gross, axis=1)

    # 6. Calculate derived fields
    df_calc['fte_gap'] = df_calc['predicted_fte'] - df_calc['actual_fte']
    df_calc['prod_pct'] = df_calc.apply(calculate_prod_pct, axis=1)
    df_calc['is_above_avg'] = df_calc.apply(is_above_avg_productivity, axis=1)

    # 7. Revenue at risk (optional)
    if include_revenue_at_risk:
        df_calc['revenue_at_risk'] = df_calc.apply(
            lambda r: calculate_revenue_at_risk(
                r['predicted_fte'], r['actual_fte'], r['trzby'], r['is_above_avg']
            ),
            axis=1
        )

    return df_calc
