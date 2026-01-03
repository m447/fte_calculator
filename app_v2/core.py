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

# Default values (fallback if not in model pickle)
# These will be overwritten by load_model() if the model contains the values
_DEFAULT_SEGMENT_PROPORTIONS = {
    'A - shopping premium': {'prop_F': 0.4149, 'prop_L': 0.5350, 'prop_ZF': 0.1037},
    'B - shopping': {'prop_F': 0.3759, 'prop_L': 0.4470, 'prop_ZF': 0.1547},
    'C - street +': {'prop_F': 0.3488, 'prop_L': 0.3563, 'prop_ZF': 0.2699},
    'D - street': {'prop_F': 0.2942, 'prop_L': 0.3659, 'prop_ZF': 0.2990},
    'E - poliklinika': {'prop_F': 0.4715, 'prop_L': 0.3734, 'prop_ZF': 0.2243},
}

_DEFAULT_SEGMENT_PROD_MEANS = {
    'A - shopping premium': 7.25,
    'B - shopping': 9.14,
    'C - street +': 6.85,
    'D - street': 6.44,
    'E - poliklinika': 6.11
}

# Mutable module-level state (updated by load_model)
SEGMENT_PROPORTIONS = _DEFAULT_SEGMENT_PROPORTIONS.copy()
SEGMENT_PROD_MEANS = _DEFAULT_SEGMENT_PROD_MEANS.copy()

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

# FTE gap thresholds - defines what counts as "notable" vs "significant" gaps
FTE_GAP_NOTABLE = 0.05    # Threshold for counting as understaffed/overstaffed (~1.5 hrs/week)
FTE_GAP_URGENT = 0.05     # Threshold for urgent priority (with productivity check)
FTE_GAP_OPTIMIZE = 0.2    # Threshold for optimize priority (overstaffed)
FTE_GAP_OUTLIER = 1.0     # Threshold for significant outliers

# Small pharmacy threshold - pharmacies below this may have false positive revenue at risk
# Small pharmacies (especially without laborants) can legitimately operate leaner
SMALL_PHARMACY_FTE = 2.5  # NET FTE threshold for "small pharmacy" flag

# Revenue at Risk v2 - Research-backed factors
# Based on: Mani et al. (2015) "Estimating the Impact of Understaffing on Sales"
# Rx revenue is less sensitive (patients need medication, will wait)
# Non-Rx revenue is more sensitive (discretionary, impulse purchases)
RAR_RX_FACTOR = 0.05       # 5% for Rx revenue (sticky demand)
RAR_NON_RX_FACTOR = 0.20   # 20% for non-Rx revenue (discretionary)

# Competition factor by segment - high productivity in competitive markets
# means higher revenue at risk (customers can easily switch to competitor)
# Based on: Shopping locations have multiple pharmacy options,
# high-volume poliklinika locations attract competition,
# street pharmacies have strongest neighborhood loyalty
RAR_COMPETITION_FACTOR = {
    'A - shopping premium': 1.3,  # Mall competition, impulse buyers
    'B - shopping': 1.2,          # Shopping center alternatives
    'C - street +': 1.1,          # Urban competition
    'D - street': 1.0,            # Baseline (neighborhood loyalty)
    'E - poliklinika': 1.2,       # Hospital complex competition, high volume
}

# Revenue at Risk v3 - Peak Hour Amplification
# Based on pharmacy 25 POS data analysis:
# - Peak hours have 27% higher pressure than average
# - Using 2.5x multiplier as conservative estimate for demand concentration
# - Original 14x was incorrect (compared pressure diff to FTE gap - wrong units)
RAR_PEAK_PROFILE = {
    # (peak_revenue_share, peak_overload_ratio)
    'A - shopping premium': (0.60, 2.5),
    'B - shopping': (0.57, 2.5),
    'C - street +': (0.52, 2.5),
    'D - street': (0.50, 2.5),
    'E - poliklinika': (0.55, 2.5),
}

# Maximum revenue at risk cap (sanity check)
RAR_MAX_PERCENTAGE = 0.15  # 15% cap

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

    Also updates SEGMENT_PROPORTIONS and SEGMENT_PROD_MEANS from the model
    if they are present (ensuring model-code alignment).

    Args:
        project_root: Path to project root directory

    Returns:
        dict: The loaded model package
    """
    global _model_pkg, _pharmacy_gross_factors, _network_median_factors
    global SEGMENT_PROPORTIONS, SEGMENT_PROD_MEANS

    # Load ML model
    model_path = project_root / 'models' / 'fte_model_v5.pkl'
    with open(model_path, 'rb') as f:
        _model_pkg = pickle.load(f)

    # Update SEGMENT_PROPORTIONS from model if available (model-code alignment)
    if 'proportions' in _model_pkg:
        model_proportions = _model_pkg['proportions']
        for segment, values in model_proportions.items():
            if segment in SEGMENT_PROPORTIONS:
                # Only update prop_F, prop_L, prop_ZF (not avg_fte, std_fte, count)
                SEGMENT_PROPORTIONS[segment] = {
                    'prop_F': values.get('prop_F', SEGMENT_PROPORTIONS[segment]['prop_F']),
                    'prop_L': values.get('prop_L', SEGMENT_PROPORTIONS[segment]['prop_L']),
                    'prop_ZF': values.get('prop_ZF', SEGMENT_PROPORTIONS[segment]['prop_ZF']),
                }

    # Update SEGMENT_PROD_MEANS from model if available
    if 'segment_prod_means' in _model_pkg:
        SEGMENT_PROD_MEANS.update(_model_pkg['segment_prod_means'])

    # Load pharmacy-specific gross factors
    gross_factors_path = project_root / 'data' / 'gross_factors.json'
    with open(gross_factors_path, 'r') as f:
        data = json.load(f)
    _pharmacy_gross_factors = {int(k): v for k, v in data['factors'].items()}
    _network_median_factors = data.get('network_medians', GROSS_CONVERSION_DEFAULT)

    return _model_pkg


def ensure_model_loaded(project_root: Path = None):
    """
    Ensure model is loaded (lazy initialization).

    Call this before any function that requires the model.
    Safe to call multiple times - only loads once.

    Args:
        project_root: Path to project root. If None, uses parent of this file's directory.

    Returns:
        dict: The loaded model package
    """
    global _model_pkg
    if _model_pkg is None:
        if project_root is None:
            project_root = Path(__file__).parent.parent
        return load_model(project_root)
    return _model_pkg


def get_model():
    """Get the loaded model package."""
    if _model_pkg is None:
        raise RuntimeError("Model not loaded. Call load_model() or ensure_model_loaded() first.")
    return _model_pkg


def get_rx_time_factor():
    """Get the RX time factor from the model."""
    return get_model().get('rx_time_factor', 0.41)


def get_feature_cols():
    """Get the feature columns used by the model."""
    return get_model()['feature_cols']


# ============================================================
# DATA VALIDATION
# ============================================================

# Required columns for the main pharmacy DataFrame
REQUIRED_COLUMNS = [
    'id', 'mesto', 'typ', 'bloky', 'trzby', 'podiel_rx',
    'fte_F', 'fte_L', 'fte_ZF', 'prod_residual'
]

# Additional columns that should be present for full functionality
OPTIONAL_COLUMNS = [
    'bloky_trend', 'region', 'var_residual'
]


class DataValidationError(Exception):
    """Raised when DataFrame validation fails."""
    pass


def validate_pharmacy_dataframe(df: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
    """
    Validate that a DataFrame has all required columns for FTE calculations.

    Args:
        df: Pharmacy DataFrame to validate
        strict: If True, raise error for missing optional columns too

    Returns:
        The validated DataFrame (for method chaining)

    Raises:
        DataValidationError: If required columns are missing
    """
    # Check required columns
    missing_required = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_required:
        raise DataValidationError(
            f"Missing required columns: {missing_required}. "
            f"Expected columns: {REQUIRED_COLUMNS}"
        )

    # Check optional columns (warn but don't fail unless strict)
    missing_optional = [col for col in OPTIONAL_COLUMNS if col not in df.columns]
    if missing_optional:
        import logging
        logger = logging.getLogger('app_v2')
        if strict:
            raise DataValidationError(
                f"Missing optional columns (strict mode): {missing_optional}"
            )
        else:
            logger.warning(f"Missing optional columns: {missing_optional}")

    # Validate data types and ranges
    validations = [
        ('id', lambda x: x.notna().all(), "id cannot have null values"),
        ('bloky', lambda x: (x >= 0).all(), "bloky must be non-negative"),
        ('trzby', lambda x: (x >= 0).all(), "trzby must be non-negative"),
        ('podiel_rx', lambda x: ((x >= 0) & (x <= 1)).all(), "podiel_rx must be between 0 and 1"),
        ('fte_F', lambda x: (x >= 0).all(), "fte_F must be non-negative"),
        ('fte_L', lambda x: (x >= 0).all(), "fte_L must be non-negative"),
        ('fte_ZF', lambda x: (x >= 0).all(), "fte_ZF must be non-negative"),
    ]

    for col, check, message in validations:
        if col in df.columns:
            try:
                if not check(df[col]):
                    raise DataValidationError(f"Data validation failed: {message}")
            except TypeError:
                # Column might have unexpected type
                raise DataValidationError(f"Column '{col}' has unexpected data type")

    # Validate segment values
    valid_segments = set(SEGMENT_PROPORTIONS.keys())
    if 'typ' in df.columns:
        invalid_segments = set(df['typ'].unique()) - valid_segments
        if invalid_segments:
            raise DataValidationError(
                f"Invalid segment values: {invalid_segments}. "
                f"Valid segments: {valid_segments}"
            )

    return df


def load_and_validate_csv(path: Path) -> pd.DataFrame:
    """
    Load a CSV file and validate it has required columns.

    Args:
        path: Path to CSV file

    Returns:
        Validated DataFrame

    Raises:
        FileNotFoundError: If file doesn't exist
        DataValidationError: If validation fails
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    df = pd.read_csv(path)
    return validate_pharmacy_dataframe(df)


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

    Uses GROSS-based productivity for classification (consistent with FTE staffing).
    Falls back to NET-based (prod_residual) if GROSS column not available.

    Args:
        row: DataFrame row or dict with 'is_above_avg_gross' or 'prod_residual' key

    Returns:
        bool: True if productivity is above segment average
    """
    # Prefer GROSS-based classification (consistent with staffing metrics)
    if 'is_above_avg_gross' in row:
        return bool(row.get('is_above_avg_gross', False))
    # Fallback to NET-based (legacy)
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


def calculate_revenue_at_risk_v1(predicted_fte, actual_fte, trzby, is_above_avg):
    """
    DEPRECATED: Original revenue at risk calculation (v1).

    Uses arbitrary 50% factor. Kept for backward compatibility and comparison.
    Use calculate_revenue_at_risk() for the research-backed v2 calculation.

    Args:
        predicted_fte: Model-predicted FTE (GROSS)
        actual_fte: Current actual FTE (GROSS)
        trzby: Annual revenue
        is_above_avg: Whether pharmacy has above-average productivity

    Returns:
        int: Estimated annual revenue at risk (EUR)
    """
    if not actual_fte or actual_fte <= 0 or predicted_fte <= actual_fte or trzby <= 0 or not is_above_avg:
        return 0

    overload_ratio = predicted_fte / actual_fte
    return int((overload_ratio - 1) * 0.5 * trzby)


def calculate_revenue_at_risk(
    predicted_fte,
    actual_fte,
    trzby,
    rx_ratio,
    pharmacy_productivity,
    segment_mean,
    segment_type=None
):
    """
    Calculate potential revenue at risk due to understaffing (v3).

    Research-backed model with peak hour calibration:
    1. Rx vs Non-Rx revenue sensitivity (5% vs 20%)
    2. Peak hour amplification (overload concentrated in peak hours)
    3. Productivity magnitude (scales with outperformance)
    4. Competition factor by segment

    Based on:
    - Mani et al. (2015) "Estimating the Impact of Understaffing"
    - Calibrated against real hourly POS data (pharmacy 25)

    Key insight: Model FTE gap represents AVERAGE understaffing, but actual
    overload is CONCENTRATED in peak hours (typically 50-60% of revenue
    happening in 40-50% of hours with 4-14x higher transaction pressure).

    Args:
        predicted_fte: Model-predicted FTE (GROSS)
        actual_fte: Current actual FTE (GROSS)
        trzby: Annual revenue
        rx_ratio: Prescription revenue share (0-1), from podiel_rx
        pharmacy_productivity: Pharmacy's GROSS productivity
        segment_mean: Segment average productivity
        segment_type: Pharmacy segment (A-E) for peak profile

    Returns:
        int: Estimated annual revenue at risk (EUR)
    """
    # Gate 1: Must be understaffed
    if not actual_fte or actual_fte <= 0 or predicted_fte <= actual_fte:
        return 0

    # Gate 2: Valid revenue
    if trzby <= 0:
        return 0

    # Gate 3: Must be above average productivity
    if not segment_mean or segment_mean <= 0:
        return 0
    productivity_ratio = pharmacy_productivity / segment_mean
    if productivity_ratio <= 1.0:
        return 0

    # Step 1: Get peak hour profile for segment
    peak_revenue_share, peak_overload_ratio = RAR_PEAK_PROFILE.get(
        segment_type, (0.50, 4.0)
    )

    # Step 2: Calculate base overload and peak overload
    base_overload = (predicted_fte / actual_fte) - 1
    peak_overload = base_overload * peak_overload_ratio

    # Step 3: Calculate peak hour revenue
    peak_revenue = trzby * peak_revenue_share

    # Step 4: Calculate blended factor from Rx ratio
    rx_ratio = max(0, min(1, rx_ratio))  # Clamp to 0-1
    blended_factor = rx_ratio * RAR_RX_FACTOR + (1 - rx_ratio) * RAR_NON_RX_FACTOR

    # Step 5: Base revenue at risk (peak hours only)
    base_at_risk = peak_overload * blended_factor * peak_revenue

    # Step 6: Scale by productivity magnitude
    productivity_multiplier = productivity_ratio - 1
    productivity_scaled = base_at_risk * (1 + productivity_multiplier)

    # Step 7: Apply competition factor
    competition_factor = RAR_COMPETITION_FACTOR.get(segment_type, 1.0)
    final_at_risk = productivity_scaled * competition_factor

    # Step 8: Apply cap (sanity check)
    max_at_risk = trzby * RAR_MAX_PERCENTAGE
    final_at_risk = min(final_at_risk, max_at_risk)

    return int(final_at_risk)


def calculate_pharmacy_fte(row):
    """
    Single source of truth for pharmacy FTE calculation.

    GROSS FTE conversion (single source of truth):
        actual_gross = fte + fte_n (NET working staff + absence FTE)
        predicted_gross = predicted_net + fte_n (same formula)

    This ensures consistency: both actual and predicted use the same
    NET + fte_n formula for GROSS conversion.

    Args:
        row: DataFrame row or dict with pharmacy data

    Returns:
        dict: {
            'predicted_fte': float (GROSS),
            'predicted_fte_net': float (NET),
            'predicted_fte_F': float (informational),
            'predicted_fte_L': float (informational),
            'predicted_fte_ZF': float (informational),
            'actual_fte': float (GROSS),
            'actual_fte_net': float (NET),
            'actual_fte_F': float (informational),
            'actual_fte_L': float (informational),
            'actual_fte_ZF': float (informational),
            'fte_n': float (absence FTE),
            'fte_diff': float,
            'gross_factors': dict (informational, not used for conversion),
        }
    """
    pharmacy_id = int(row['id'])
    typ = row['typ']
    props = SEGMENT_PROPORTIONS.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})

    # Get gross factors (for informational/backward compatibility only)
    gross_factors = get_gross_factors(pharmacy_id, typ)

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
    predicted_fte_net = max(0.5, predicted_fte_net)  # Minimum 0.5 FTE

    # Get fte_n (absence FTE) - same value used for both actual and predicted
    fte_n = float(row.get('fte_n', 0))

    # GROSS = NET + fte_n (single source of truth for both actual and predicted)
    predicted_fte = predicted_fte_net + fte_n

    # Actual NET and GROSS
    actual_fte_net = float(row.get('fte', 0))
    actual_fte = actual_fte_net + fte_n  # Same formula as predicted

    # Role breakdown for display (informational only, uses proportions)
    # Predicted roles (based on segment proportions)
    fte_F_pred = predicted_fte_net * props['prop_F']
    fte_L_pred = predicted_fte_net * props['prop_L']
    fte_ZF_pred = predicted_fte_net * props['prop_ZF']

    # Actual roles (from CSV data)
    fte_F_actual = float(row.get('fte_F', 0))
    fte_L_actual = float(row.get('fte_L', 0))
    fte_ZF_actual = float(row.get('fte_ZF', 0))

    # Calculate difference (positive = understaffed, negative = overstaffed)
    # Note: fte_diff = (pred_net + fte_n) - (actual_net + fte_n) = pred_net - actual_net
    fte_diff = predicted_fte - actual_fte

    return {
        'predicted_fte': predicted_fte,
        'predicted_fte_net': predicted_fte_net,
        'predicted_fte_F': fte_F_pred,
        'predicted_fte_L': fte_L_pred,
        'predicted_fte_ZF': fte_ZF_pred,
        'actual_fte': actual_fte,
        'actual_fte_net': actual_fte_net,
        'actual_fte_F': fte_F_actual,
        'actual_fte_L': fte_L_actual,
        'actual_fte_ZF': fte_ZF_actual,
        'fte_n': fte_n,
        'fte_diff': fte_diff,
        'gross_factors': gross_factors,  # For informational/backward compatibility
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
    df_calc['predicted_fte_net'] = df_calc['predicted_fte_net'].clip(lower=0.5)  # Minimum 0.5 FTE

    # 4. Convert NET to GROSS: GROSS = NET + fte_n (single source of truth)
    # Same formula for both actual and predicted
    df_calc['predicted_fte'] = df_calc['predicted_fte_net'] + df_calc['fte_n']
    df_calc['actual_fte'] = df_calc['fte'] + df_calc['fte_n']

    # 5. Calculate derived fields
    df_calc['fte_gap'] = df_calc['predicted_fte'] - df_calc['actual_fte']
    df_calc['prod_pct'] = df_calc.apply(calculate_prod_pct, axis=1)
    df_calc['is_above_avg'] = df_calc.apply(is_above_avg_productivity, axis=1)

    # 6. Revenue at risk (optional) - v2 research-backed calculation
    if include_revenue_at_risk:
        # Get productivity column (prefer GROSS, fallback to NET-derived)
        if 'produktivita_gross' in df_calc.columns:
            prod_col = 'produktivita_gross'
        else:
            # Fallback: calculate from prod_residual + segment mean
            prod_col = None

        # Calculate ACTUAL segment means from data (not model-stored means)
        # This ensures RAR gate uses real data averages
        if prod_col:
            actual_segment_means = df_calc.groupby('typ')[prod_col].mean().to_dict()
        else:
            actual_segment_means = SEGMENT_PROD_MEANS.copy()

        def calc_rar(r):
            # Get pharmacy productivity
            if prod_col:
                pharmacy_prod = float(r.get(prod_col, 0))
            else:
                # Derive from prod_residual: prod = residual + mean
                segment_mean = actual_segment_means.get(r['typ'], 7.0)
                pharmacy_prod = float(r.get('prod_residual', 0)) + segment_mean

            # Get segment mean for this pharmacy's type (from actual data)
            segment_mean = actual_segment_means.get(r['typ'], 7.0)

            return calculate_revenue_at_risk(
                predicted_fte=r['predicted_fte'],
                actual_fte=r['actual_fte'],
                trzby=r['trzby'],
                rx_ratio=r['podiel_rx'],
                pharmacy_productivity=pharmacy_prod,
                segment_mean=segment_mean,
                segment_type=r['typ']
            )

        df_calc['revenue_at_risk'] = df_calc.apply(calc_rar, axis=1)

        # Also calculate v1 for comparison (optional, can be removed later)
        df_calc['revenue_at_risk_v1'] = df_calc.apply(
            lambda r: calculate_revenue_at_risk_v1(
                r['predicted_fte'], r['actual_fte'], r['trzby'], r['is_above_avg']
            ),
            axis=1
        )

    # 7. Small pharmacy flag - potential false positive for revenue at risk
    # Small pharmacies without laborants can legitimately operate leaner
    df_calc['is_small_pharmacy'] = (df_calc['fte'] <= SMALL_PHARMACY_FTE) & (df_calc['fte_L'] == 0)

    return df_calc


# ============================================================
# USER INPUT PREDICTION (for /api/predict endpoint)
# ============================================================

# GROSS conversion with coefficient of variation (for uncertainty bands)
# CV values capped at 0.30 for practical ranges (street types have high variability)
GROSS_CONVERSION_WITH_CV = {
    'A - shopping premium': {
        'F': {'factor': 1.17, 'cv': 0.12},
        'L': {'factor': 1.22, 'cv': 0.04},
        'ZF': {'factor': 1.23, 'cv': 0.30},
    },
    'B - shopping': {
        'F': {'factor': 1.22, 'cv': 0.16},
        'L': {'factor': 1.22, 'cv': 0.08},
        'ZF': {'factor': 1.18, 'cv': 0.30},
    },
    'C - street +': {
        'F': {'factor': 1.23, 'cv': 0.30},
        'L': {'factor': 1.22, 'cv': 0.21},
        'ZF': {'factor': 1.20, 'cv': 0.25},
    },
    'D - street': {
        'F': {'factor': 1.29, 'cv': 0.30},
        'L': {'factor': 1.22, 'cv': 0.30},
        'ZF': {'factor': 1.25, 'cv': 0.18},
    },
    'E - poliklinika': {
        'F': {'factor': 1.27, 'cv': 0.30},
        'L': {'factor': 1.24, 'cv': 0.29},
        'ZF': {'factor': 1.23, 'cv': 0.30},
    },
}
GROSS_CONVERSION_WITH_CV_DEFAULT = {
    'F': {'factor': 1.22, 'cv': 0.20},
    'L': {'factor': 1.22, 'cv': 0.15},
    'ZF': {'factor': 1.20, 'cv': 0.30},
}


def calculate_fte_from_inputs(
    bloky: float,
    trzby: float,
    typ: str,
    podiel_rx: float = 0.5,
    productivity_z: float = 0,
    variability_z: float = 0,
    pharmacy_id: int = None,
    defaults: dict = None
) -> dict:
    """
    Calculate FTE from user inputs (for manual prediction).

    Single source of truth for the /api/predict endpoint logic.

    Args:
        bloky: Annual transactions
        trzby: Annual revenue in EUR
        typ: Pharmacy type (A-E)
        podiel_rx: Rx share (0-1)
        productivity_z: Productivity z-score (-1 to 1)
        variability_z: Variability z-score (0 to 1)
        pharmacy_id: Optional pharmacy ID for specific factors
        defaults: Default feature values from model

    Returns:
        dict with predicted FTE values and metadata
    """
    if defaults is None:
        defaults = get_model().get('defaults', {})

    rx_time_factor = get_rx_time_factor()
    conv = GROSS_CONVERSION_WITH_CV.get(typ, GROSS_CONVERSION_WITH_CV_DEFAULT)

    # Check if pharmacy-specific factors should be used
    use_pharmacy_factors = False
    if pharmacy_id is not None:
        pharmacy_id = int(pharmacy_id)
        test_conv = get_gross_factors(pharmacy_id, typ)
        type_conv = GROSS_CONVERSION.get(typ, GROSS_CONVERSION_DEFAULT)
        use_pharmacy_factors = test_conv != type_conv

    # Build features for model v5
    features = defaults.copy()
    features['bloky'] = bloky
    features['trzby'] = trzby
    features['typ'] = typ
    features['effective_bloky'] = bloky * (1 + rx_time_factor * podiel_rx)
    features['revenue_per_transaction'] = trzby / bloky if bloky > 0 else 20
    features['bloky_range'] = bloky * 0.028 * (1 + variability_z)
    features['podiel_rx'] = podiel_rx
    # prod_residual: ASYMMETRIC - only positive values count (v5)
    prod_residual_raw = productivity_z * 1.5
    features['prod_residual'] = max(0, prod_residual_raw)

    # Create DataFrame and predict
    X = pd.DataFrame([{col: features.get(col, 0) for col in get_feature_cols()}])
    fte_net = get_model()['models']['fte'].predict(X)[0]
    fte_net = max(0.5, fte_net)

    # Get role proportions
    props = SEGMENT_PROPORTIONS.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})

    # Calculate NET role breakdown
    fte_F_net = fte_net * props['prop_F']
    fte_L_net = fte_net * props['prop_L']
    fte_ZF_net = fte_net * props['prop_ZF']

    # Convert to GROSS
    if use_pharmacy_factors:
        pf = get_gross_factors(pharmacy_id, typ)
        fte_F_gross = fte_F_net * pf['F']
        fte_L_gross = fte_L_net * pf['L']
        fte_ZF_gross = fte_ZF_net * pf['ZF']
        gross_factors_used = pf
    else:
        fte_F_gross = fte_F_net * conv['F']['factor']
        fte_L_gross = fte_L_net * conv['L']['factor']
        fte_ZF_gross = fte_ZF_net * conv['ZF']['factor']
        gross_factors_used = {
            'F': conv['F']['factor'],
            'L': conv['L']['factor'],
            'ZF': conv['ZF']['factor']
        }

    # Round for display
    fte_F = round(fte_F_gross, 1)
    fte_L = round(fte_L_gross, 1)
    fte_ZF = round(fte_ZF_gross, 1)
    fte_total = fte_F + fte_L + fte_ZF

    # Tolerance based on model accuracy
    fte_std = get_model()['metrics']['fte']['std']
    avg_conv = sum(gross_factors_used.values()) / 3
    tolerance = fte_std * avg_conv

    return {
        'fte_total': fte_total,
        'fte_net': round(fte_net, 2),
        'fte_F': fte_F,
        'fte_L': fte_L,
        'fte_ZF': fte_ZF,
        'tolerance': round(tolerance, 2),
        'gross_factors': gross_factors_used,
        'use_pharmacy_factors': use_pharmacy_factors,
        'effective_bloky': features['effective_bloky'],
        'conv_with_cv': conv,
    }


def calculate_sensitivity(
    bloky: float,
    trzby: float,
    podiel_rx: float,
    typ: str,
    defaults: dict = None
) -> dict:
    """
    Calculate FTE sensitivity to input changes.

    Shows how FTE recommendation changes with ±10% input variations.

    Args:
        bloky: Annual transactions
        trzby: Annual revenue
        podiel_rx: Rx share (0-1)
        typ: Pharmacy type
        defaults: Default feature values

    Returns:
        dict with sensitivity values for each input
    """
    if defaults is None:
        defaults = get_model().get('defaults', {})

    def predict_fte(b, t, rx):
        result = calculate_fte_from_inputs(
            bloky=b, trzby=t, typ=typ, podiel_rx=rx,
            productivity_z=0, variability_z=0, defaults=defaults
        )
        return result['fte_total']

    # Calculate base FTE
    base_fte = predict_fte(bloky, trzby, podiel_rx)

    # Calculate sensitivity for each variable
    bloky_plus10 = predict_fte(bloky * 1.1, trzby, podiel_rx)
    trzby_plus10 = predict_fte(bloky, trzby * 1.1, podiel_rx)
    rx_plus10pp = predict_fte(bloky, trzby, min(1.0, podiel_rx + 0.1))

    return {
        'base_fte': base_fte,
        'bloky_10pct': round(bloky_plus10 - base_fte, 2),
        'trzby_10pct': round(trzby_plus10 - base_fte, 2),
        'rx_10pp': round(rx_plus10pp - base_fte, 2)
    }
