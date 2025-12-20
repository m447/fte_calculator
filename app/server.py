"""
FTE Kalkulačka v5.1
Dr.Max Pharmacy Staffing Tool

Run: python app/server.py
Access: http://localhost:8080
"""

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from functools import wraps
import pickle
import pandas as pd
import numpy as np
import os
import subprocess
import requests
from pathlib import Path

app = Flask(__name__, static_folder='static')
CORS(app)

# Basic Auth Configuration
APP_USERNAME = os.environ.get('APP_USERNAME', 'drmax')
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'FteCalc2024!Rx#Secure')

# API Key for direct API access (separate from web UI auth)
API_KEY = os.environ.get('API_KEY', 'fte-api-2024-xK9mP2vL8nQ4wR7y')


def check_auth(username, password):
    """Check if username/password combination is valid."""
    return username == APP_USERNAME and password == APP_PASSWORD


def check_api_key():
    """Check if valid API key is provided in header."""
    provided_key = request.headers.get('X-API-Key')
    return provided_key == API_KEY


def is_browser_request():
    """Check if request is from browser (has Referer from our app)."""
    referer = request.headers.get('Referer', '')
    return 'fte-calculator' in referer or 'localhost' in referer


def authenticate():
    """Send 401 response that enables basic auth."""
    return Response(
        'Prístup zamietnutý. Zadajte správne prihlasovacie údaje.',
        401,
        {'WWW-Authenticate': 'Basic realm="FTE Calculator"'}
    )


def api_key_required():
    """Send 403 response for missing API key."""
    return Response(
        json.dumps({'error': 'API key required. Use X-API-Key header.'}),
        403,
        {'Content-Type': 'application/json'}
    )


def requires_auth(f):
    """Decorator for web pages - requires Basic Auth only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


def requires_api_auth(f):
    """Decorator for API endpoints - requires Basic Auth + API Key (unless from browser)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # First check Basic Auth
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()

        # For browser requests (from web UI), allow without API key
        if is_browser_request():
            return f(*args, **kwargs)

        # For direct API access, require API key
        if not check_api_key():
            return api_key_required()

        return f(*args, **kwargs)
    return decorated

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "fte_model_v5.pkl"
DATA_PATH = PROJECT_ROOT / "data" / "ml_ready_v3.csv"
GROSS_FACTORS_PATH = PROJECT_ROOT / "data" / "gross_factors.json"

# Load model package
with open(MODEL_PATH, 'rb') as f:
    model_pkg = pickle.load(f)

# Segment productivity means for computing prod_residual (v5: asymmetric)
# Updated Dec 2024: Using WEIGHTED average (by bloky/transactions) - larger pharmacies have more influence
# This better reflects true segment benchmarks than simple mean
SEGMENT_PROD_MEANS = model_pkg.get('segment_prod_means', {
    'A - shopping premium': 7.25,  # weighted avg (simple: 7.53)
    'B - shopping': 9.14,          # weighted avg (simple: 8.92)
    'C - street +': 6.85,          # weighted avg (simple: 7.12)
    'D - street': 6.44,            # weighted avg (simple: 6.83)
    'E - poliklinika': 6.11        # weighted avg (simple: 6.51)
})

# Segment proportions for FTE role distribution (F/L/ZF)
# Calculated from training data - used for gross FTE conversion
SEGMENT_PROPORTIONS = model_pkg.get('proportions', {
    'A - shopping premium': {'prop_F': 0.4149, 'prop_L': 0.5350, 'prop_ZF': 0.1037},
    'B - shopping': {'prop_F': 0.3759, 'prop_L': 0.4470, 'prop_ZF': 0.1547},
    'C - street +': {'prop_F': 0.3488, 'prop_L': 0.3563, 'prop_ZF': 0.2699},
    'D - street': {'prop_F': 0.2942, 'prop_L': 0.3659, 'prop_ZF': 0.2990},
    'E - poliklinika': {'prop_F': 0.4715, 'prop_L': 0.3734, 'prop_ZF': 0.2243},
})

# Load reference data
df = pd.read_csv(DATA_PATH)
defaults = df.median(numeric_only=True).to_dict()

# Load pharmacy-specific gross factors (from payroll data)
import json
with open(GROSS_FACTORS_PATH, 'r') as f:
    gross_factors_data = json.load(f)
PHARMACY_GROSS_FACTORS = {int(k): v for k, v in gross_factors_data['factors'].items()}
NETWORK_MEDIAN_FACTORS = gross_factors_data['network_medians']


@app.route('/')
@requires_auth
def index():
    return send_from_directory('static', 'index-v2.html')


@app.route('/v1')
@requires_auth
def index_v1():
    return send_from_directory('static', 'index.html')


@app.route('/utilization')
@requires_auth
def utilization():
    return send_from_directory('static', 'utilization.html')


def calculate_sensitivity(bloky, trzby, podiel_rx, typ, model_pkg, defaults, conv):
    """Calculate FTE sensitivity to input changes."""
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)

    def predict_fte(b, t, rx):
        """Helper to predict FTE for given inputs."""
        features = defaults.copy()
        features['bloky'] = b
        features['trzby'] = t
        features['typ'] = typ
        features['effective_bloky'] = b * (1 + rx_time_factor * rx)
        features['revenue_per_transaction'] = t / b if b > 0 else 20
        features['bloky_range'] = b * 0.028
        features['podiel_rx'] = rx
        features['prod_residual'] = 0  # Assume average efficiency for sensitivity calc

        X = pd.DataFrame([{col: features.get(col, 0) for col in model_pkg['feature_cols']}])
        fte_net = model_pkg['models']['fte'].predict(X)[0]
        fte_net = max(0.5, fte_net)

        # Get proportions and convert to GROSS
        props = model_pkg['proportions'].get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})
        fte_F_gross = fte_net * props['prop_F'] * conv['F']['factor']
        fte_L_gross = fte_net * props['prop_L'] * conv['L']['factor']
        fte_ZF_gross = fte_net * props['prop_ZF'] * conv['ZF']['factor']

        return fte_F_gross + fte_L_gross + fte_ZF_gross

    # Calculate base FTE
    base_fte = predict_fte(bloky, trzby, podiel_rx)

    # Calculate sensitivity for each variable
    bloky_plus10 = predict_fte(bloky * 1.1, trzby, podiel_rx)
    trzby_plus10 = predict_fte(bloky, trzby * 1.1, podiel_rx)
    rx_plus10pp = predict_fte(bloky, trzby, min(1.0, podiel_rx + 0.1))

    return {
        'bloky_10pct': round(bloky_plus10 - base_fte, 2),
        'trzby_10pct': round(trzby_plus10 - base_fte, 2),
        'rx_10pp': round(rx_plus10pp - base_fte, 2)
    }


def calculate_revenue_at_risk(predicted_fte, actual_fte, trzby, is_above_avg_productivity):
    """Calculate potential revenue at risk due to understaffing in productive pharmacies."""
    if not actual_fte or predicted_fte <= actual_fte or trzby <= 0 or not is_above_avg_productivity:
        return 0

    # Using rounded values for consistency with display
    actual_fte_rounded = round(actual_fte, 1)
    predicted_fte_rounded = round(predicted_fte, 1)

    if predicted_fte_rounded <= actual_fte_rounded:
        return 0

    overload_ratio = predicted_fte_rounded / actual_fte_rounded if actual_fte_rounded > 0 else 1
    # Loss = (Overload_ratio - 1) × 50% × Revenue
    revenue_at_risk = int((overload_ratio - 1) * 0.5 * trzby)
    return revenue_at_risk


@app.route('/api/predict', methods=['POST'])
@requires_api_auth
def predict():
    """Predict FTE with role breakdown - returns GROSS FTE (contracted positions)."""
    data = request.json

    # Get inputs (only key predictors)
    bloky = float(data.get('bloky', 50000))
    trzby = float(data.get('trzby', 1000000))
    typ = data.get('typ', 'B - shopping')
    podiel_rx = float(data.get('podiel_rx', 0.5))
    pharmacy_id = data.get('pharmacy_id')  # Optional: for pharmacy-specific factors

    # Advanced parameters (z-scores: -1, 0, 1)
    productivity_z = float(data.get('productivity_z', 0))  # -1=low, 0=avg, 1=high
    variability_z = float(data.get('variability_z', 0))    # 0=steady, 0.5=seasonal, 1=volatile

    # Check if pharmacy-specific gross factors should be used
    use_pharmacy_factors = False
    if pharmacy_id is not None:
        pharmacy_id = int(pharmacy_id)
        if pharmacy_id in PHARMACY_GROSS_FACTORS:
            use_pharmacy_factors = True

    # NET to GROSS conversion factors by role (from payroll data analysis)
    # Factor = median gross/net ratio, CV = coefficient of variation (capped at 0.30)
    # High CV in street types due to flying pharmacists - capped for practical ranges
    GROSS_CONVERSION = {
        'A - shopping premium': {
            'F': {'factor': 1.17, 'cv': 0.12},
            'L': {'factor': 1.22, 'cv': 0.04},
            'ZF': {'factor': 1.23, 'cv': 0.30},  # Capped from 0.53
        },
        'B - shopping': {
            'F': {'factor': 1.22, 'cv': 0.16},
            'L': {'factor': 1.22, 'cv': 0.08},
            'ZF': {'factor': 1.18, 'cv': 0.30},  # Capped from 0.47
        },
        'C - street +': {
            'F': {'factor': 1.23, 'cv': 0.30},   # Capped from 0.98
            'L': {'factor': 1.22, 'cv': 0.21},
            'ZF': {'factor': 1.20, 'cv': 0.25},
        },
        'D - street': {
            'F': {'factor': 1.29, 'cv': 0.30},   # Capped from 1.04
            'L': {'factor': 1.22, 'cv': 0.30},   # Capped from 0.67
            'ZF': {'factor': 1.25, 'cv': 0.18},
        },
        'E - poliklinika': {
            'F': {'factor': 1.27, 'cv': 0.30},   # Capped from 0.46
            'L': {'factor': 1.24, 'cv': 0.29},
            'ZF': {'factor': 1.23, 'cv': 0.30},  # Capped from 0.35
        },
    }
    conv = GROSS_CONVERSION.get(typ, {
        'F': {'factor': 1.22, 'cv': 0.20},
        'L': {'factor': 1.22, 'cv': 0.15},
        'ZF': {'factor': 1.20, 'cv': 0.30},
    })

    # RX time factor (from model training)
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)

    # Build features for model v5 (with asymmetric prod_residual)
    features = defaults.copy()
    features['bloky'] = bloky
    features['trzby'] = trzby
    features['typ'] = typ
    features['effective_bloky'] = bloky * (1 + rx_time_factor * podiel_rx)
    features['revenue_per_transaction'] = trzby / bloky if bloky > 0 else 20
    features['bloky_range'] = bloky * 0.028 * (1 + variability_z)  # ~2.8% matches training data
    features['podiel_rx'] = podiel_rx
    # prod_residual: ASYMMETRIC - only positive values count (v5)
    # productivity_z = 0 means average efficiency, +1 = 1.5 above avg, -1 = below avg (clipped to 0)
    # Efficient pharmacies: rewarded with fewer FTE
    # Inefficient pharmacies: no extra FTE (clipped to 0)
    prod_residual_raw = productivity_z * 1.5
    features['prod_residual'] = max(0, prod_residual_raw)  # Clip negative to 0
    # Use median values for features not directly controllable by user
    # trzby_cv, bloky_cv, kpi_mean, seasonal_peak_factor come from defaults

    # Create DataFrame
    X = pd.DataFrame([{col: features.get(col, 0) for col in model_pkg['feature_cols']}])

    # Predict total FTE (NET)
    fte_net = model_pkg['models']['fte'].predict(X)[0]
    fte_std = model_pkg['metrics']['fte']['std']

    # Note: Productivity adjustment is now in the model via prod_residual feature
    # No post-hoc adjustment needed (was required for v3 which had no productivity signal)

    # Ensure minimum FTE
    fte_net = max(0.5, fte_net)

    # Get role proportions for this store type (for NET FTE)
    props = model_pkg['proportions'].get(typ, {
        'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2,
        'avg_fte': 3.5, 'std_fte': 1.0
    })

    # Calculate NET role breakdown first
    fte_F_net = fte_net * props['prop_F']
    fte_L_net = fte_net * props['prop_L']
    fte_ZF_net = fte_net * props['prop_ZF']

    # Convert each role to GROSS using role-specific factors
    # Use pharmacy-specific factors if pharmacy_id provided, otherwise type-based
    if use_pharmacy_factors:
        pf = PHARMACY_GROSS_FACTORS[pharmacy_id]
        fte_F_gross = fte_F_net * pf['F']
        fte_L_gross = fte_L_net * pf['L']
        fte_ZF_gross = fte_ZF_net * pf['ZF']
        gross_factors_used = pf
    else:
        fte_F_gross = fte_F_net * conv['F']['factor']
        fte_L_gross = fte_L_net * conv['L']['factor']
        fte_ZF_gross = fte_ZF_net * conv['ZF']['factor']
        gross_factors_used = {'F': conv['F']['factor'], 'L': conv['L']['factor'], 'ZF': conv['ZF']['factor']}

    # Total GROSS FTE
    fte_pred = fte_F_gross + fte_L_gross + fte_ZF_gross

    # Round for display
    fte_F = round(fte_F_gross, 1)
    fte_L = round(fte_L_gross, 1)
    fte_ZF = round(fte_ZF_gross, 1)

    # Recalculate total
    fte_pred = fte_F + fte_L + fte_ZF

    # Tolerance based on model accuracy (RMSE converted to GROSS)
    avg_conv = (gross_factors_used['F'] + gross_factors_used['L'] + gross_factors_used['ZF']) / 3
    tolerance = fte_std * avg_conv  # ~±0.5 FTE typical error

    # Type-based conversion for benchmarks (always use type-based, not pharmacy-specific)
    type_conv = (conv['F']['factor'] + conv['L']['factor'] + conv['ZF']['factor']) / 3

    # Benchmark - same store type
    type_data = df[df['typ'] == typ]

    # Comparable pharmacies - similar bloky and trzby (±10%)
    comparable = df[
        (df['typ'] == typ) &
        (df['bloky'] >= bloky * 0.9) & (df['bloky'] <= bloky * 1.1) &
        (df['trzby'] >= trzby * 0.9) & (df['trzby'] <= trzby * 1.1)
    ]
    comparable_ids = comparable['id'].astype(int).tolist()

    # Productivity analysis
    # Network average: effective_bloky / gross_fte for all pharmacies
    df['effective_bloky_calc'] = df['bloky'] * (1 + rx_time_factor * df['podiel_rx'])
    df['gross_fte'] = df['fte'] * df['typ'].map({
        'A - shopping premium': 1.21, 'B - shopping': 1.21,
        'C - street +': 1.22, 'D - street': 1.25, 'E - poliklinika': 1.25
    }).fillna(1.22)
    network_avg_productivity = df['effective_bloky_calc'].sum() / df['gross_fte'].sum()

    # This pharmacy's productivity if at recommended FTE
    pharmacy_productivity = features['effective_bloky'] / fte_pred if fte_pred > 0 else 0
    productivity_vs_avg = ((pharmacy_productivity / network_avg_productivity) - 1) * 100 if network_avg_productivity > 0 else 0

    # Basket value
    basket_value = trzby / bloky if bloky > 0 else 0

    # Hourly metrics (176 hours per FTE per month × 12 = 2112 hours/year)
    HOURS_PER_FTE_YEAR = 176 * 12  # 2112
    recommended_hours = fte_pred * HOURS_PER_FTE_YEAR
    bloky_per_hour = bloky / recommended_hours if recommended_hours > 0 else 0
    trzby_per_hour = trzby / recommended_hours if recommended_hours > 0 else 0

    # Segment ranges for hourly metrics
    type_data['gross_fte'] = type_data['fte'] * avg_conv
    type_data['hours'] = type_data['gross_fte'] * HOURS_PER_FTE_YEAR
    type_data['bloky_per_hour'] = type_data['bloky'] / type_data['hours']
    type_data['trzby_per_hour'] = type_data['trzby'] / type_data['hours']
    type_data['basket'] = type_data['trzby'] / type_data['bloky']

    segment_bloky_hour_min = round(type_data['bloky_per_hour'].min(), 1)
    segment_bloky_hour_max = round(type_data['bloky_per_hour'].max(), 1)
    segment_bloky_hour_avg = round(type_data['bloky_per_hour'].mean(), 1)
    segment_trzby_hour_min = round(type_data['trzby_per_hour'].min(), 0)
    segment_trzby_hour_max = round(type_data['trzby_per_hour'].max(), 0)
    segment_trzby_hour_avg = round(type_data['trzby_per_hour'].mean(), 0)
    segment_basket_min = round(type_data['basket'].min(), 1)
    segment_basket_max = round(type_data['basket'].max(), 1)
    segment_basket_avg = round(type_data['basket'].mean(), 1)
    segment_rx_avg = round(type_data['podiel_rx'].mean() * 100, 0)
    segment_rx_min = round(type_data['podiel_rx'].min() * 100, 0)
    segment_rx_max = round(type_data['podiel_rx'].max() * 100, 0)
    segment_bloky_avg = round(type_data['bloky'].mean() / 1000, 0)
    segment_trzby_avg = round(type_data['trzby'].mean() / 1000000, 1)

    # Segment ranges for bloky and trzby (in thousands/millions)
    segment_bloky_min = round(type_data['bloky'].min() / 1000, 0)
    segment_bloky_max = round(type_data['bloky'].max() / 1000, 0)
    segment_trzby_min = round(type_data['trzby'].min() / 1000000, 1)
    segment_trzby_max = round(type_data['trzby'].max() / 1000000, 1)

    # Histogram data for segment position charts (10 bins)
    def compute_histogram(values, num_bins=10):
        """Compute normalized histogram for display."""
        counts, bin_edges = np.histogram(values, bins=num_bins)
        max_count = counts.max() if counts.max() > 0 else 1
        return [round(c / max_count, 2) for c in counts]  # Normalized 0-1

    hist_bloky = compute_histogram(type_data['bloky'] / 1000)
    hist_trzby = compute_histogram(type_data['trzby'] / 1000000)
    hist_rx = compute_histogram(type_data['podiel_rx'] * 100)
    hist_fte = compute_histogram(type_data['fte'] * type_conv)
    hist_basket = compute_histogram(type_data['basket'])
    hist_blokyhod = compute_histogram(type_data['bloky_per_hour'])
    hist_trzbyhod = compute_histogram(type_data['trzby_per_hour'])

    # Get actual FTE if pharmacy_id provided (for revenue at risk calc)
    actual_fte = None
    if pharmacy_id is not None:
        try:
            pharmacy_id_int = int(pharmacy_id)
            pharmacy_matches = df[df['id'] == pharmacy_id_int]
            if not pharmacy_matches.empty:
                p_row = pharmacy_matches.iloc[0]
                # Determine factors for actuals (specific or default)
                if pharmacy_id_int in PHARMACY_GROSS_FACTORS:
                    a_conv = PHARMACY_GROSS_FACTORS[pharmacy_id_int]
                else:
                    a_conv = GROSS_CONVERSION.get(p_row['typ'], {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
                
                actual_fte = p_row['fte_F'] * a_conv['F'] + \
                             p_row['fte_L'] * a_conv['L'] + \
                             p_row['fte_ZF'] * a_conv['ZF']
        except ValueError:
            pass  # Invalid pharmacy_id format

    # Revenue at risk
    is_above_avg_productivity = productivity_z > 0
    revenue_at_risk = calculate_revenue_at_risk(fte_pred, actual_fte, trzby, is_above_avg_productivity)

    return jsonify({
        'meta': {
            'version': '5.1',
            'model': 'fte_model_v5',
            'fte_type': 'gross',  # Returns GROSS FTE (contracted positions)
            'notes': 'v5: Asymmetric prod_residual - rewards efficiency, no compensation for inefficiency',
            'pharmacy_id': pharmacy_id if use_pharmacy_factors else None,
            'gross_factors': gross_factors_used
        },
        'fte': {
            'total': round(fte_pred, 1),
            'min': round(max(1.0, fte_pred - tolerance), 1),
            'max': round(fte_pred + tolerance, 1),
            'tolerance': round(tolerance, 1),
            'net': round(fte_net, 1)  # Original NET FTE for reference
        },
        'breakdown': {
            'F': fte_F,
            'L': fte_L,
            'ZF': fte_ZF
        },
        'revenue_at_risk': revenue_at_risk,
        'benchmark': {
            'avg': round(type_data['fte'].mean() * type_conv, 1),  # Convert to GROSS using type-based factors
            'min': round(type_data['fte'].min() * type_conv, 1),
            'max': round(type_data['fte'].max() * type_conv, 1),
            'count': len(type_data)
        },
        'comparable': {
            'count': len(comparable),
            'ids': comparable_ids,
            'fte_values': [round(v * type_conv, 1) for v in comparable['fte'].tolist()] if len(comparable) > 0 else [],
            'avg_fte': round(comparable['fte'].mean() * type_conv, 1) if len(comparable) > 0 else None,
            'min_fte': round(comparable['fte'].min() * type_conv, 1) if len(comparable) > 0 else None,
            'max_fte': round(comparable['fte'].max() * type_conv, 1) if len(comparable) > 0 else None,
            'productivity_min': round((comparable['bloky'] * (1 + rx_time_factor * comparable['podiel_rx']) / (comparable['fte'] * type_conv)).min() / 1000, 1) if len(comparable) > 0 else None,
            'productivity_max': round((comparable['bloky'] * (1 + rx_time_factor * comparable['podiel_rx']) / (comparable['fte'] * type_conv)).max() / 1000, 1) if len(comparable) > 0 else None
        },
        'inputs': {
            'bloky': bloky,
            'trzby': trzby,
            'typ': typ,
            'podiel_rx': podiel_rx,
            'productivity_z': productivity_z,
            'variability_z': variability_z,
            'effective_bloky': features['effective_bloky'],
            'basket_value': round(basket_value, 2)
        },
        'hourly': {
            'bloky_per_hour': round(bloky_per_hour, 1),
            'trzby_per_hour': round(trzby_per_hour, 0),
            'basket_value': round(basket_value, 1),
            'segment_bloky_hour_min': segment_bloky_hour_min,
            'segment_bloky_hour_max': segment_bloky_hour_max,
            'segment_bloky_hour_avg': segment_bloky_hour_avg,
            'segment_trzby_hour_min': segment_trzby_hour_min,
            'segment_trzby_hour_max': segment_trzby_hour_max,
            'segment_trzby_hour_avg': segment_trzby_hour_avg,
            'segment_basket_min': segment_basket_min,
            'segment_basket_max': segment_basket_max,
            'segment_basket_avg': segment_basket_avg
        },
        'segment': {
            'bloky_min': segment_bloky_min,
            'bloky_max': segment_bloky_max,
            'bloky_avg': segment_bloky_avg,
            'trzby_min': segment_trzby_min,
            'trzby_max': segment_trzby_max,
            'trzby_avg': segment_trzby_avg,
            'rx_min': segment_rx_min,
            'rx_max': segment_rx_max,
            'rx_avg': segment_rx_avg,
            'histograms': {
                'bloky': hist_bloky,
                'trzby': hist_trzby,
                'rx': hist_rx,
                'fte': hist_fte,
                'basket': hist_basket,
                'blokyhod': hist_blokyhod,
                'trzbyhod': hist_trzbyhod
            }
        },
        'productivity': {
            'recommended': round(features['effective_bloky'] / fte_pred / 1000, 1) if fte_pred > 0 else None,
            'pharmacy': round(pharmacy_productivity, 0),
            'network_avg': round(network_avg_productivity, 0),
            'vs_avg_pct': round(productivity_vs_avg, 0)
        },
        'sensitivity': calculate_sensitivity(bloky, trzby, podiel_rx, typ, model_pkg, defaults, conv)
    })



@app.route('/api/network', methods=['GET'])
@requires_api_auth
def get_network():
    """Get network-wide staffing analysis with predictions for all pharmacies."""
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)

    # Prepare data for predictions
    df_calc = df.copy()
    df_calc['effective_bloky'] = df_calc['bloky'] * (1 + rx_time_factor * df_calc['podiel_rx'])

    # Apply asymmetric prod_residual (v5: only positive values count, negative clipped to 0)
    # This matches how the model was trained
    df_calc['prod_residual'] = df_calc['prod_residual'].clip(lower=0)

    # Build features and predict
    X = pd.DataFrame([{col: row.get(col, 0) for col in model_pkg['feature_cols']}
                      for _, row in df_calc.iterrows()])
    df_calc['predicted_fte_net'] = model_pkg['models']['fte'].predict(X)

    # Role-specific GROSS conversion (same as /api/predict)
    GROSS_CONVERSION = {
        'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
        'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
        'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
        'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
        'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
    }

    def calc_gross_fte_predicted(fte_net, typ, pharmacy_id):
        """Calculate GROSS FTE for predicted using pharmacy-specific or type-based factors."""
        props = SEGMENT_PROPORTIONS.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})
        # Use pharmacy-specific factors if available, otherwise type-based
        if int(pharmacy_id) in PHARMACY_GROSS_FACTORS:
            conv = PHARMACY_GROSS_FACTORS[int(pharmacy_id)]
        else:
            conv = GROSS_CONVERSION.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        fte_F = fte_net * props['prop_F'] * conv['F']
        fte_L = fte_net * props['prop_L'] * conv['L']
        fte_ZF = fte_net * props['prop_ZF'] * conv['ZF']
        return fte_F + fte_L + fte_ZF

    def calc_gross_fte_actual(row):
        """Calculate actual GROSS FTE using pharmacy-specific or type-based factors."""
        # Use pharmacy-specific factors if available, otherwise type-based
        if int(row['id']) in PHARMACY_GROSS_FACTORS:
            conv = PHARMACY_GROSS_FACTORS[int(row['id'])]
        else:
            conv = GROSS_CONVERSION.get(row['typ'], {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        # Use actual role breakdown from data, not segment proportions
        fte_F = row['fte_F'] * conv['F']
        fte_L = row['fte_L'] * conv['L']
        fte_ZF = row['fte_ZF'] * conv['ZF']
        return fte_F + fte_L + fte_ZF

    df_calc['predicted_fte'] = df_calc.apply(
        lambda row: calc_gross_fte_predicted(row['predicted_fte_net'], row['typ'], row['id']), axis=1)
    df_calc['actual_fte'] = df_calc.apply(calc_gross_fte_actual, axis=1)
    df_calc['fte_diff'] = df_calc['predicted_fte'] - df_calc['actual_fte']

    # Summary
    total_actual = df_calc['actual_fte'].sum()
    total_predicted = df_calc['predicted_fte'].sum()
    total_diff = total_predicted - total_actual

    # Segment breakdown
    segments = []
    for typ in ['A - shopping premium', 'B - shopping', 'C - street +', 'D - street', 'E - poliklinika']:
        seg = df_calc[df_calc['typ'] == typ]
        if len(seg) == 0:
            continue
        actual = seg['actual_fte'].sum()
        pred = seg['predicted_fte'].sum()
        diff = pred - actual

        # Count by status
        ok_count = len(seg[(seg['fte_diff'] >= -0.5) & (seg['fte_diff'] <= 0.5)])
        under_count = len(seg[seg['fte_diff'] > 0.5])
        over_count = len(seg[seg['fte_diff'] < -0.5])

        segments.append({
            'typ': typ,
            'count': len(seg),
            'actual_fte': round(actual, 1),
            'predicted_fte': round(pred, 1),
            'diff': round(diff, 1),
            'ok_count': ok_count,
            'understaffed_count': under_count,
            'overstaffed_count': over_count
        })

    # Outliers (|diff| > 1.0 FTE)
    understaffed = df_calc[df_calc['fte_diff'] > 1.0].nlargest(15, 'fte_diff')
    overstaffed = df_calc[df_calc['fte_diff'] < -1.0].nsmallest(15, 'fte_diff')

    def pharmacy_to_dict(row, include_priority_data=False):
        # Always compute productivity status using prod_residual
        # prod_residual > 0 means above segment average productivity
        prod_residual = row.get('prod_residual', 0)
        is_above_avg = prod_residual > 0

        result = {
            'id': int(row['id']),
            'mesto': row['mesto'],
            'typ': row['typ'],
            'actual_fte': round(row['actual_fte'], 1),
            'predicted_fte': round(row['predicted_fte'], 1),
            'diff': round(row['fte_diff'], 1),
            'bloky': int(row['bloky']),
            'trzby': int(row['trzby']),
            'podiel_rx': round(row['podiel_rx'] * 100, 0),
            'is_above_avg_productivity': is_above_avg
        }
        if include_priority_data:
            # Add fields needed for priority dashboard
            # Use prod_residual for productivity calculation (already normalized by segment)
            prod_residual = row.get('prod_residual', 0)
            is_above_avg = prod_residual > 0
            prod_pct = round(prod_residual * 100, 0)  # prod_residual is already a ratio
            bloky_trend = round(row.get('bloky_trend', 0) * 100, 0)

            # Revenue at risk calculation (from utilization.html formula)
            # Loss = (Overload_ratio - 1) × 50% × Revenue
            # IMPORTANT: Use rounded values (same as displayed) for consistency
            revenue_at_risk = 0
            actual_fte_rounded = round(row['actual_fte'], 1)
            predicted_fte_rounded = round(row['predicted_fte'], 1)
            if predicted_fte_rounded > actual_fte_rounded and is_above_avg:  # understaffed + productive
                overload_ratio = predicted_fte_rounded / actual_fte_rounded if actual_fte_rounded > 0 else 1
                revenue_at_risk = int((overload_ratio - 1) * 0.5 * row['trzby'])

            result.update({
                'is_above_avg_productivity': is_above_avg,
                'prod_pct': prod_pct,
                'bloky_trend': bloky_trend,
                'revenue_at_risk': revenue_at_risk
            })
        return result

    # All pharmacies for filtering (include priority data for revenue_at_risk)
    all_pharmacies = [pharmacy_to_dict(row, include_priority_data=True) for _, row in df_calc.iterrows()]

    # Get unique regions for filter
    regions = sorted(df_calc['regional'].dropna().unique().tolist())

    # Priority categories for dashboard
    # Compute priority fields for each pharmacy
    def get_priority_data(row):
        # Use prod_residual for productivity (positive = above segment average)
        prod_residual = row.get('prod_residual', 0)
        is_above_avg = prod_residual > 0
        bloky_trend = row.get('bloky_trend', 0)
        return {
            'is_above_avg': is_above_avg,
            'bloky_trend': bloky_trend
        }

    # Urgent: understaffed (gap > 0.5) + above-avg productivity (losing revenue)
    # Returns ALL qualifying pharmacies (UI will display top 10, CSV exports all)
    urgent_candidates = df_calc[df_calc['fte_diff'] > 0.5].copy()
    urgent_list = []
    for _, row in urgent_candidates.iterrows():
        priority_data = get_priority_data(row)
        if priority_data['is_above_avg']:
            urgent_list.append(pharmacy_to_dict(row, include_priority_data=True))
    # Sort by revenue_at_risk descending
    urgent_list.sort(key=lambda x: x.get('revenue_at_risk', 0), reverse=True)

    # Optimize: overstaffed (gap < -0.7) - can reallocate
    # Returns ALL qualifying pharmacies sorted by gap (most overstaffed first)
    optimize_candidates = df_calc[df_calc['fte_diff'] < -0.7].copy()
    optimize_list = [pharmacy_to_dict(row, include_priority_data=True) for _, row in optimize_candidates.sort_values('fte_diff').iterrows()]

    # Monitor: growing significantly (bloky_trend > 15%) - watch for future needs
    # Returns ALL qualifying pharmacies sorted by growth (highest first)
    monitor_candidates = df_calc[df_calc['bloky_trend'] > 0.15].copy()
    monitor_list = [pharmacy_to_dict(row, include_priority_data=True) for _, row in monitor_candidates.sort_values('bloky_trend', ascending=False).iterrows()]

    # Calculate total revenue at risk for ALL urgent pharmacies
    total_revenue_at_risk = sum(p.get('revenue_at_risk', 0) for p in urgent_list)

    return jsonify({
        'summary': {
            'total_pharmacies': len(df_calc),
            'total_actual_fte': round(total_actual, 1),
            'total_predicted_fte': round(total_predicted, 1),
            'diff': round(total_diff, 1),
            'diff_pct': round(total_diff / total_actual * 100, 1) if total_actual > 0 else 0,
            'status': 'balanced' if abs(total_diff) < 10 else ('understaffed' if total_diff > 0 else 'overstaffed')
        },
        'segments': segments,
        'outliers': {
            'understaffed': [pharmacy_to_dict(row) for _, row in understaffed.iterrows()],
            'overstaffed': [pharmacy_to_dict(row) for _, row in overstaffed.iterrows()],
            'understaffed_count': len(df_calc[df_calc['fte_diff'] > 1.0]),
            'overstaffed_count': len(df_calc[df_calc['fte_diff'] < -1.0])
        },
        'priorities': {
            'urgent': urgent_list,  # Understaffed + high productivity = losing revenue
            'optimize': optimize_list,  # Overstaffed = can reallocate
            'monitor': monitor_list,  # Growing = watch for future needs
            'urgent_count': len(urgent_list),
            'optimize_count': len(optimize_list),
            'monitor_count': len(monitor_list),
            'total_revenue_at_risk': total_revenue_at_risk
        },
        'pharmacies': all_pharmacies,
        'filters': {
            'regions': regions,
            'types': ['A - shopping premium', 'B - shopping', 'C - street +', 'D - street', 'E - poliklinika']
        }
    })


@app.route('/api/pharmacies', methods=['GET'])
@requires_api_auth
def get_pharmacies():
    """Get list of all pharmacies for selector dropdown."""
    pharmacies = []
    for _, row in df.iterrows():
        pharmacies.append({
            'id': int(row['id']),
            'mesto': row['mesto'],
            'typ': row['typ']
        })
    # Sort by mesto
    pharmacies.sort(key=lambda x: x['mesto'])
    return jsonify({'pharmacies': pharmacies})


@app.route('/api/pharmacies/search', methods=['GET'])
@requires_api_auth
def search_pharmacies():
    """Search pharmacies with filters - for AI assistant queries.

    Query params:
    - typ: filter by segment (e.g., "B - shopping")
    - min_gap: minimum FTE gap (e.g., 1.0 for understaffed)
    - max_gap: maximum FTE gap (e.g., -1.0 for overstaffed)
    - productivity: 'above' or 'below' average
    - sort_by: 'gap', 'bloky', 'trzby', 'fte' (default: gap)
    - sort_order: 'asc' or 'desc' (default: desc for gap)
    - limit: max results (default: 10)
    """
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)

    # Prepare data with predictions
    df_calc = df.copy()
    df_calc['effective_bloky'] = df_calc['bloky'] * (1 + rx_time_factor * df_calc['podiel_rx'])
    df_calc['prod_residual'] = df_calc['prod_residual'].clip(lower=0)

    X = pd.DataFrame([{col: row.get(col, 0) for col in model_pkg['feature_cols']}
                      for _, row in df_calc.iterrows()])
    df_calc['predicted_fte_net'] = model_pkg['models']['fte'].predict(X)

    GROSS_CONVERSION = {
        'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
        'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
        'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
        'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
        'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
    }

    def calc_gross(fte_net, typ):
        props = SEGMENT_PROPORTIONS.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})
        conv = GROSS_CONVERSION.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        return fte_net * props['prop_F'] * conv['F'] + \
               fte_net * props['prop_L'] * conv['L'] + \
               fte_net * props['prop_ZF'] * conv['ZF']

    def calc_actual_gross(row):
        conv = GROSS_CONVERSION.get(row['typ'], {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        return row['fte_F'] * conv['F'] + row['fte_L'] * conv['L'] + row['fte_ZF'] * conv['ZF']

    df_calc['predicted_fte'] = df_calc.apply(lambda r: calc_gross(r['predicted_fte_net'], r['typ']), axis=1)
    df_calc['actual_fte'] = df_calc.apply(calc_actual_gross, axis=1)
    df_calc['fte_gap'] = df_calc['predicted_fte'] - df_calc['actual_fte']

    # Apply filters
    result = df_calc.copy()

    # Filter by segment
    typ = request.args.get('typ')
    if typ:
        result = result[result['typ'] == typ]

    # Filter by gap
    min_gap = request.args.get('min_gap', type=float)
    max_gap = request.args.get('max_gap', type=float)
    if min_gap is not None:
        result = result[result['fte_gap'] >= min_gap]
    if max_gap is not None:
        result = result[result['fte_gap'] <= max_gap]

    # Filter by productivity
    productivity = request.args.get('productivity')
    if productivity == 'above':
        result = result[result['prod_residual'] > 0]
    elif productivity == 'below':
        result = result[result['prod_residual'] <= 0]

    # Sort
    sort_by = request.args.get('sort_by', 'gap')
    sort_order = request.args.get('sort_order', 'desc')
    ascending = sort_order == 'asc'

    sort_map = {
        'gap': 'fte_gap',
        'bloky': 'bloky',
        'trzby': 'trzby',
        'fte': 'actual_fte'
    }
    sort_col = sort_map.get(sort_by, 'fte_gap')
    result = result.sort_values(sort_col, ascending=ascending)

    # Limit
    limit = request.args.get('limit', 10, type=int)
    result = result.head(limit)

    # Format output
    pharmacies = []
    for _, row in result.iterrows():
        pharmacies.append({
            'id': int(row['id']),
            'mesto': row['mesto'],
            'typ': row['typ'],
            'bloky': int(row['bloky']),
            'trzby': int(row['trzby']),
            'podiel_rx': round(row['podiel_rx'] * 100, 0),
            'actual_fte': round(row['actual_fte'], 1),
            'predicted_fte': round(row['predicted_fte'], 1),
            'gap': round(row['fte_gap'], 1),
            'productivity': 'above_avg' if row['prod_residual'] > 0 else 'avg_or_below',
            'prod_residual': round(row['prod_residual'], 2)
        })

    return jsonify({
        'count': len(pharmacies),
        'pharmacies': pharmacies,
        'filters_applied': {
            'typ': typ,
            'min_gap': min_gap,
            'max_gap': max_gap,
            'productivity': productivity,
            'sort_by': sort_by,
            'limit': limit
        }
    })


@app.route('/api/model/info', methods=['GET'])
@requires_api_auth
def get_model_info():
    """Get model coefficients and info - for AI assistant awareness."""
    # Extract coefficients from the model
    pipeline = model_pkg['models']['fte']
    model = pipeline.named_steps['model']
    preprocessor = pipeline.named_steps['preprocessor']

    # Get feature names after preprocessing
    num_features = model_pkg['num_features']
    cat_features = model_pkg['cat_features']

    # Get one-hot encoded category names
    cat_encoder = preprocessor.named_transformers_['cat']
    cat_encoded_names = list(cat_encoder.get_feature_names_out(cat_features))

    all_feature_names = num_features + cat_encoded_names
    coefs = model.coef_
    intercept = model.intercept_

    # Build coefficient dict
    coefficients = {}
    for name, coef in zip(all_feature_names, coefs):
        coefficients[name] = round(float(coef), 4)

    # Segment coefficients (relative to A-shopping premium which is baseline)
    segment_coefs = {
        'A - shopping premium': 0.0,  # baseline (dropped in one-hot)
    }
    for name in cat_encoded_names:
        if name.startswith('typ_'):
            segment_name = name.replace('typ_', '')
            segment_coefs[segment_name] = coefficients[name]

    # Get metrics
    metrics = model_pkg.get('metrics', {}).get('fte', {})

    return jsonify({
        'version': model_pkg.get('version', 'v5'),
        'notes': model_pkg.get('notes', ''),
        'metrics': {
            'r2': round(metrics.get('r2', 0), 3),
            'rmse': round(metrics.get('rmse', 0), 3),
            'cv_r2_mean': round(metrics.get('cv_r2_mean', 0), 3),
        },
        'intercept': round(float(intercept), 4),
        'coefficients': coefficients,
        'segment_coefficients': segment_coefs,
        'segment_prod_means': SEGMENT_PROD_MEANS,
        'feature_importance': {
            'most_positive': sorted(
                [(k, v) for k, v in coefficients.items() if not k.startswith('typ_')],
                key=lambda x: x[1], reverse=True
            )[:5],
            'most_negative': sorted(
                [(k, v) for k, v in coefficients.items() if not k.startswith('typ_')],
                key=lambda x: x[1]
            )[:3]
        },
        'rx_time_factor': model_pkg.get('rx_time_factor', 0.41),
        'training_data': {
            'n_pharmacies': len(df),
            'period': 'Sep 2020 - Aug 2021'
        }
    })


@app.route('/api/pharmacy/<int:pharmacy_id>', methods=['GET'])
@requires_api_auth
def get_pharmacy(pharmacy_id):
    """Get details for a specific pharmacy including predicted FTE (same as network)."""
    pharmacy = df[df['id'] == pharmacy_id]
    if len(pharmacy) == 0:
        return jsonify({'error': 'Pharmacy not found'}), 404

    row = pharmacy.iloc[0]
    typ = row['typ']
    pharmacy_id = int(row['id'])

    # Use pharmacy-specific gross factors if available, otherwise fall back to type-based
    TYPE_GROSS_CONV = {
        'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
        'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
        'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
        'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
        'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
    }

    if pharmacy_id in PHARMACY_GROSS_FACTORS:
        conv = PHARMACY_GROSS_FACTORS[pharmacy_id]
    else:
        conv = TYPE_GROSS_CONV.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})

    props = model_pkg['proportions'].get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})

    # Calculate actual GROSS FTE using actual role breakdown and pharmacy-specific factors
    fte_F_gross = float(row['fte_F']) * conv['F']
    fte_L_gross = float(row['fte_L']) * conv['L']
    fte_ZF_gross = float(row['fte_ZF']) * conv['ZF']
    actual_fte = fte_F_gross + fte_L_gross + fte_ZF_gross

    # Calculate PREDICTED FTE (same as /api/network for consistency)
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)
    effective_bloky = row['bloky'] * (1 + rx_time_factor * row['podiel_rx'])

    # Build features for prediction (same as network)
    features = {col: row.get(col, 0) for col in model_pkg['feature_cols']}
    features['effective_bloky'] = effective_bloky  # Must be calculated, not from row
    X = pd.DataFrame([features])
    predicted_fte_net = model_pkg['models']['fte'].predict(X)[0]

    # Convert predicted NET to GROSS using pharmacy-specific factors (same conv as actual)
    fte_F_pred = predicted_fte_net * props['prop_F'] * conv['F']
    fte_L_pred = predicted_fte_net * props['prop_L'] * conv['L']
    fte_ZF_pred = predicted_fte_net * props['prop_ZF'] * conv['ZF']
    predicted_fte = fte_F_pred + fte_L_pred + fte_ZF_pred

    # Calculate difference
    fte_diff = predicted_fte - actual_fte

    # Revenue at risk calculation (same as in get_network)
    revenue_at_risk = 0
    actual_fte_rounded = round(actual_fte, 1)
    predicted_fte_rounded = round(predicted_fte, 1)
    is_above_avg = float(row.get('prod_residual', 0)) > 0
    if predicted_fte_rounded > actual_fte_rounded and is_above_avg:
        overload_ratio = predicted_fte_rounded / actual_fte_rounded if actual_fte_rounded > 0 else 1
        revenue_at_risk = int((overload_ratio - 1) * 0.5 * row['trzby'])

    return jsonify({
        'id': int(row['id']),
        'mesto': row['mesto'],
        'typ': row['typ'],
        'bloky': int(row['bloky']),
        'trzby': float(row['trzby']),
        'podiel_rx': float(row['podiel_rx']),
        'actual_fte': round(actual_fte, 1),
        'actual_fte_F': round(fte_F_gross, 1),
        'actual_fte_L': round(fte_L_gross, 1),
        'actual_fte_ZF': round(fte_ZF_gross, 1),
        'predicted_fte': round(predicted_fte, 1),
        'predicted_fte_F': round(fte_F_pred, 1),
        'predicted_fte_L': round(fte_L_pred, 1),
        'predicted_fte_ZF': round(fte_ZF_pred, 1),
        'fte_diff': round(fte_diff, 1),
        'revenue_at_risk': revenue_at_risk,
        'gross_factors': conv,  # Pharmacy-specific or type-based factors
        'prod_residual': round(float(row.get('prod_residual', 0)), 2),
        'is_above_avg_productivity': float(row.get('prod_residual', 0)) > 0,
        # Productivity percentage above/below segment average
        'prod_pct': round(float(row.get('prod_residual', 0)) / SEGMENT_PROD_MEANS.get(row['typ'], 8.0) * 100, 0),
        # Trend: bloky growth rate (already stored as percentage in data)
        'bloky_trend': round(float(row.get('bloky_trend', 0)) * 100, 0)  # Convert to percentage points
    })


@app.route('/api/benchmarks', methods=['GET'])
@requires_api_auth
def get_benchmarks():
    """Get benchmarks for all store types."""
    benchmarks = []
    for typ in sorted(df['typ'].unique()):
        type_data = df[df['typ'] == typ]
        benchmarks.append({
            'typ': typ,
            'avg_fte': round(type_data['fte'].mean(), 2),
            'avg_bloky': int(type_data['bloky'].mean()),
            'avg_trzby': int(type_data['trzby'].mean()),
            'count': len(type_data)
        })
    return jsonify(benchmarks)


# Vertex AI Configuration
VERTEX_PROJECT = os.environ.get('VERTEX_PROJECT', 'gen-lang-client-0415148507')
VERTEX_LOCATION = os.environ.get('VERTEX_LOCATION', 'global')  # Gemini 3 requires global location
VERTEX_MODEL = 'gemini-3-flash-preview'

# Tool definitions for function calling
CHAT_TOOLS = {
    "function_declarations": [
        {
            "name": "search_pharmacies",
            "description": "Vyhľadaj lekárne podľa filtrov. Použi pre otázky typu 'ktoré lekárne...', 'ukáž mi B lekárne s...', 'nájdi poddimenzované lekárne', 'existuje lekáreň v meste X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mesto": {
                        "type": "string",
                        "description": "Mesto/lokalita lekárne (case-insensitive, partial match). Napr. 'Čadca', 'Bratislava', 'Košice'"
                    },
                    "typ": {
                        "type": "string",
                        "description": "Segment lekárne: 'A - shopping premium', 'B - shopping', 'C - street +', 'D - street', 'E - poliklinika'",
                        "enum": ["A - shopping premium", "B - shopping", "C - street +", "D - street", "E - poliklinika"]
                    },
                    "productivity": {
                        "type": "string",
                        "description": "Filter podľa produktivity: 'above' = nadpriemerná, 'below' = podpriemerná",
                        "enum": ["above", "below"]
                    },
                    "min_gap": {
                        "type": "number",
                        "description": "Minimálny FTE gap (kladné = poddimenzované). Napr. 1.0 pre lekárne ktorým chýba aspoň 1 FTE"
                    },
                    "max_gap": {
                        "type": "number",
                        "description": "Maximálny FTE gap (záporné = predimenzované). Napr. -1.0 pre lekárne s prebytkom aspoň 1 FTE"
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Zoradiť podľa: 'gap' (FTE rozdiel), 'bloky' (transakcie), 'trzby' (tržby), 'fte' (aktuálne FTE)",
                        "enum": ["gap", "bloky", "trzby", "fte"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximálny počet výsledkov (default 10, max 20)"
                    }
                },
                "required": []
            }
        },
        {
            "name": "get_network_summary",
            "description": "Získaj celkový prehľad siete lekární - súhrn FTE, štatistiky podľa segmentov, outliers. Použi pre otázky typu 'koľko máme lekární', 'celkový prehľad', 'stav siete'.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "get_pharmacy_details",
            "description": "Získaj detaily konkrétnej lekárne podľa ID. Použi keď používateľ pýta na konkrétnu lekáreň alebo chce porovnať s inou.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pharmacy_id": {
                        "type": "integer",
                        "description": "ID lekárne"
                    }
                },
                "required": ["pharmacy_id"]
            }
        },
        {
            "name": "get_model_info",
            "description": "Získaj informácie o ML modeli - koeficienty, metriky presnosti, váhy segmentov. Použi pre otázky typu 'aký model používate', 'ako funguje výpočet', 'aký vplyv má produktivita', 'prečo B segment má nižšie FTE'.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "detect_growth_opportunities",
            "description": "Nájdi lekárne s potenciálom rastu ale možným neobslúženým dopytom. Toto sú lekárne ktoré RASTÚ a majú VYSOKÚ PRODUKTIVITU - model im preto odporúča menej personálu, ale v skutočnosti môžu mať kapacitné problémy počas špičiek. Použi pre otázky typu 'ktoré lekárne majú potenciál rastu', 'kde môže byť neobslúžený dopyt', 'kapacitné problémy', 'rastúce lekárne s vysokou produktivitou'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_growth": {
                        "type": "number",
                        "description": "Minimálny rast v % (default 3). Vyššia hodnota = prísnejší filter."
                    },
                    "segment": {
                        "type": "string",
                        "description": "Filter podľa segmentu: 'A', 'B', 'C', 'D', 'E'"
                    }
                },
                "required": []
            }
        }
    ]
}


def execute_tool(tool_name, args):
    """Execute a tool and return the result."""
    if tool_name == "search_pharmacies":
        return execute_search_pharmacies(args)
    elif tool_name == "get_network_summary":
        return execute_get_network_summary()
    elif tool_name == "get_pharmacy_details":
        return execute_get_pharmacy_details(args.get("pharmacy_id"))
    elif tool_name == "get_model_info":
        return execute_get_model_info()
    elif tool_name == "detect_growth_opportunities":
        return execute_detect_growth_opportunities(args)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


def execute_search_pharmacies(args):
    """Execute pharmacy search with filters."""
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)

    df_calc = df.copy()
    df_calc['effective_bloky'] = df_calc['bloky'] * (1 + rx_time_factor * df_calc['podiel_rx'])
    df_calc['prod_residual'] = df_calc['prod_residual'].clip(lower=0)

    X = pd.DataFrame([{col: row.get(col, 0) for col in model_pkg['feature_cols']}
                      for _, row in df_calc.iterrows()])
    df_calc['predicted_fte_net'] = model_pkg['models']['fte'].predict(X)

    GROSS_CONVERSION = {
        'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
        'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
        'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
        'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
        'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
    }

    def calc_gross(fte_net, typ):
        props = SEGMENT_PROPORTIONS.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})
        conv = GROSS_CONVERSION.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        return fte_net * props['prop_F'] * conv['F'] + \
               fte_net * props['prop_L'] * conv['L'] + \
               fte_net * props['prop_ZF'] * conv['ZF']

    def calc_actual_gross(row):
        conv = GROSS_CONVERSION.get(row['typ'], {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        return row['fte_F'] * conv['F'] + row['fte_L'] * conv['L'] + row['fte_ZF'] * conv['ZF']

    df_calc['predicted_fte'] = df_calc.apply(lambda r: calc_gross(r['predicted_fte_net'], r['typ']), axis=1)
    df_calc['actual_fte'] = df_calc.apply(calc_actual_gross, axis=1)
    df_calc['fte_gap'] = df_calc['predicted_fte'] - df_calc['actual_fte']

    # Calculate productivity percentage
    df_calc['prod_pct'] = df_calc.apply(
        lambda r: round(r['prod_residual'] / SEGMENT_PROD_MEANS.get(r['typ'], 8.0) * 100, 0), axis=1)

    result = df_calc.copy()

    # Apply filters
    # Filter by city (case-insensitive, partial match)
    if args.get('mesto'):
        mesto_search = args['mesto'].lower()
        result = result[result['mesto'].str.lower().str.contains(mesto_search, na=False)]

    if args.get('typ'):
        result = result[result['typ'] == args['typ']]

    if args.get('min_gap') is not None:
        result = result[result['fte_gap'] >= args['min_gap']]

    if args.get('max_gap') is not None:
        result = result[result['fte_gap'] <= args['max_gap']]

    if args.get('productivity') == 'above':
        result = result[result['prod_residual'] > 0]
    elif args.get('productivity') == 'below':
        result = result[result['prod_residual'] <= 0]

    # Sort
    sort_by = args.get('sort_by', 'gap')
    sort_map = {'gap': 'fte_gap', 'bloky': 'bloky', 'trzby': 'trzby', 'fte': 'actual_fte'}
    sort_col = sort_map.get(sort_by, 'fte_gap')

    # For gap and fte, sort descending by default; for bloky/trzby ascending
    ascending = sort_by in ['bloky', 'trzby']
    result = result.sort_values(sort_col, ascending=ascending)

    limit = min(args.get('limit', 10), 20)
    result = result.head(limit)

    pharmacies = []
    for _, row in result.iterrows():
        pharmacies.append({
            'id': int(row['id']),
            'mesto': row['mesto'],
            'typ': row['typ'],
            'bloky': int(row['bloky']),
            'trzby': int(row['trzby']),
            'podiel_rx': round(row['podiel_rx'] * 100, 0),
            'actual_fte': round(row['actual_fte'], 1),
            'predicted_fte': round(row['predicted_fte'], 1),
            'gap': round(row['fte_gap'], 1),
            'prod_pct': int(row['prod_pct']),
            'productivity': 'nadpriemerná' if row['prod_residual'] > 0 else 'podpriemerná/priemerná'
        })

    return {
        'count': len(pharmacies),
        'filters': args,
        'pharmacies': pharmacies
    }


def execute_get_network_summary():
    """Get network-wide summary."""
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)

    df_calc = df.copy()
    df_calc['effective_bloky'] = df_calc['bloky'] * (1 + rx_time_factor * df_calc['podiel_rx'])
    df_calc['prod_residual'] = df_calc['prod_residual'].clip(lower=0)

    X = pd.DataFrame([{col: row.get(col, 0) for col in model_pkg['feature_cols']}
                      for _, row in df_calc.iterrows()])
    df_calc['predicted_fte_net'] = model_pkg['models']['fte'].predict(X)

    GROSS_CONVERSION = {
        'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
        'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
        'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
        'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
        'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
    }

    def calc_gross_pred(fte_net, typ):
        props = SEGMENT_PROPORTIONS.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})
        conv = GROSS_CONVERSION.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        return fte_net * props['prop_F'] * conv['F'] + \
               fte_net * props['prop_L'] * conv['L'] + \
               fte_net * props['prop_ZF'] * conv['ZF']

    def calc_actual_gross(row):
        conv = GROSS_CONVERSION.get(row['typ'], {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        return row['fte_F'] * conv['F'] + row['fte_L'] * conv['L'] + row['fte_ZF'] * conv['ZF']

    df_calc['predicted_fte'] = df_calc.apply(lambda r: calc_gross_pred(r['predicted_fte_net'], r['typ']), axis=1)
    df_calc['actual_fte'] = df_calc.apply(calc_actual_gross, axis=1)
    df_calc['fte_gap'] = df_calc['predicted_fte'] - df_calc['actual_fte']

    total_actual = df_calc['actual_fte'].sum()
    total_predicted = df_calc['predicted_fte'].sum()

    segments = []
    for typ in ['A - shopping premium', 'B - shopping', 'C - street +', 'D - street', 'E - poliklinika']:
        seg = df_calc[df_calc['typ'] == typ]
        if len(seg) == 0:
            continue
        segments.append({
            'typ': typ,
            'count': len(seg),
            'actual_fte': round(seg['actual_fte'].sum(), 1),
            'predicted_fte': round(seg['predicted_fte'].sum(), 1),
            'gap': round(seg['fte_gap'].sum(), 1),
            'understaffed': len(seg[seg['fte_gap'] > 0.5]),
            'overstaffed': len(seg[seg['fte_gap'] < -0.5])
        })

    return {
        'total_pharmacies': len(df_calc),
        'total_actual_fte': round(total_actual, 1),
        'total_predicted_fte': round(total_predicted, 1),
        'total_gap': round(total_predicted - total_actual, 1),
        'understaffed_count': len(df_calc[df_calc['fte_gap'] > 0.5]),
        'overstaffed_count': len(df_calc[df_calc['fte_gap'] < -0.5]),
        'segments': segments
    }


def execute_get_pharmacy_details(pharmacy_id):
    """Get details for a specific pharmacy."""
    pharmacy = df[df['id'] == pharmacy_id]
    if len(pharmacy) == 0:
        return {"error": f"Lekáreň s ID {pharmacy_id} nenájdená"}

    row = pharmacy.iloc[0]
    typ = row['typ']

    TYPE_GROSS_CONV = {
        'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
        'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
        'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
        'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
        'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
    }
    conv = TYPE_GROSS_CONV.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})

    actual_fte = row['fte_F'] * conv['F'] + row['fte_L'] * conv['L'] + row['fte_ZF'] * conv['ZF']

    # Calculate predicted
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)
    features = {col: row.get(col, 0) for col in model_pkg['feature_cols']}
    features['effective_bloky'] = row['bloky'] * (1 + rx_time_factor * row['podiel_rx'])
    X = pd.DataFrame([features])
    predicted_fte_net = model_pkg['models']['fte'].predict(X)[0]

    props = SEGMENT_PROPORTIONS.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})
    predicted_fte = predicted_fte_net * props['prop_F'] * conv['F'] + \
                    predicted_fte_net * props['prop_L'] * conv['L'] + \
                    predicted_fte_net * props['prop_ZF'] * conv['ZF']

    prod_pct = round(float(row.get('prod_residual', 0)) / SEGMENT_PROD_MEANS.get(typ, 8.0) * 100, 0)

    return {
        'id': int(row['id']),
        'mesto': row['mesto'],
        'typ': typ,
        'bloky': int(row['bloky']),
        'trzby': int(row['trzby']),
        'podiel_rx': round(row['podiel_rx'] * 100, 0),
        'actual_fte': round(actual_fte, 1),
        'predicted_fte': round(predicted_fte, 1),
        'gap': round(predicted_fte - actual_fte, 1),
        'prod_pct': int(prod_pct),
        'productivity': 'nadpriemerná' if row.get('prod_residual', 0) > 0 else 'podpriemerná/priemerná'
    }


def execute_get_model_info():
    """Get ML model information - coefficients, metrics, segment weights."""
    pipeline = model_pkg['models']['fte']
    model = pipeline.named_steps['model']
    preprocessor = pipeline.named_steps['preprocessor']

    # Get feature names
    num_features = model_pkg['num_features']
    cat_features = model_pkg['cat_features']
    cat_encoder = preprocessor.named_transformers_['cat']
    cat_encoded_names = list(cat_encoder.get_feature_names_out(cat_features))
    all_feature_names = num_features + cat_encoded_names

    coefs = model.coef_
    intercept = model.intercept_

    # Build coefficient dict
    coefficients = {}
    for name, coef in zip(all_feature_names, coefs):
        coefficients[name] = round(float(coef), 4)

    # Segment coefficients
    segment_coefs = {'A - shopping premium': 0.0}
    for name in cat_encoded_names:
        if name.startswith('typ_'):
            segment_name = name.replace('typ_', '')
            segment_coefs[segment_name] = coefficients[name]

    metrics = model_pkg.get('metrics', {}).get('fte', {})

    return {
        'version': model_pkg.get('version', 'v5'),
        'type': 'Ridge Regression (L2 regularization)',
        'training_data': '286 lekární, Sep 2020 - Aug 2021',
        'metrics': {
            'r2': round(metrics.get('r2', 0), 3),
            'rmse': round(metrics.get('rmse', 0), 3),
            'cv_r2_mean': round(metrics.get('cv_r2_mean', 0), 3),
        },
        'intercept': round(float(intercept), 4),
        'segment_coefficients': segment_coefs,
        'segment_productivity_means': SEGMENT_PROD_MEANS,
        'feature_importance': {
            'most_positive': sorted(
                [(k, v) for k, v in coefficients.items() if not k.startswith('typ_')],
                key=lambda x: x[1], reverse=True
            )[:5],
            'most_negative': sorted(
                [(k, v) for k, v in coefficients.items() if not k.startswith('typ_')],
                key=lambda x: x[1]
            )[:3]
        },
        'rx_time_factor': model_pkg.get('rx_time_factor', 0.41),
        'productivity_rule': 'Asymetrické: nadpriemerná produktivita = odmena (nižšie FTE), podpriemerná = žiadna penalizácia'
    }


def execute_detect_growth_opportunities(args):
    """Find pharmacies with growth + high productivity = potential unserved demand."""
    min_growth = args.get('min_growth', 3.0)
    segment = args.get('segment')

    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)

    df_calc = df.copy()
    df_calc['effective_bloky'] = df_calc['bloky'] * (1 + rx_time_factor * df_calc['podiel_rx'])
    df_calc['prod_residual'] = df_calc['prod_residual'].clip(lower=0)

    # Calculate predictions
    X = pd.DataFrame([{col: row.get(col, 0) for col in model_pkg['feature_cols']}
                      for _, row in df_calc.iterrows()])
    df_calc['predicted_fte_net'] = model_pkg['models']['fte'].predict(X)

    GROSS_CONVERSION = {
        'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
        'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
        'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
        'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
        'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
    }

    def calc_gross(fte_net, typ):
        props = SEGMENT_PROPORTIONS.get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})
        conv = GROSS_CONVERSION.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        return fte_net * props['prop_F'] * conv['F'] + \
               fte_net * props['prop_L'] * conv['L'] + \
               fte_net * props['prop_ZF'] * conv['ZF']

    def calc_actual_gross(row):
        conv = GROSS_CONVERSION.get(row['typ'], {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        return row['fte_F'] * conv['F'] + row['fte_L'] * conv['L'] + row['fte_ZF'] * conv['ZF']

    df_calc['predicted_fte'] = df_calc.apply(lambda r: calc_gross(r['predicted_fte_net'], r['typ']), axis=1)
    df_calc['actual_fte'] = df_calc.apply(calc_actual_gross, axis=1)
    df_calc['fte_gap'] = df_calc['predicted_fte'] - df_calc['actual_fte']

    # Calculate productivity percentage
    df_calc['prod_pct'] = df_calc.apply(
        lambda r: round(r['prod_residual'] / SEGMENT_PROD_MEANS.get(r['typ'], 8.0) * 100, 0), axis=1)

    # Filter for growth risk pattern: growing + high productivity
    # bloky_trend > min_growth AND prod_residual > 0 (above segment average)
    risk_pharmacies = df_calc[
        (df_calc['bloky_trend'] > min_growth) &
        (df_calc['prod_residual'] > 0)
    ].copy()

    if segment:
        risk_pharmacies = risk_pharmacies[risk_pharmacies['typ'].str.startswith(segment)]

    # Sort by growth rate descending
    risk_pharmacies = risk_pharmacies.sort_values('bloky_trend', ascending=False)

    results = []
    for _, row in risk_pharmacies.head(20).iterrows():
        bloky_trend = row.get('bloky_trend', 0)
        risk_level = 'vysoké' if bloky_trend > 7 else 'stredné'

        results.append({
            'id': int(row['id']),
            'mesto': row['mesto'],
            'typ': row['typ'],
            'bloky_trend': round(bloky_trend, 1),
            'prod_pct': int(row.get('prod_pct', 0)),
            'actual_fte': round(row['actual_fte'], 1),
            'predicted_fte': round(row['predicted_fte'], 1),
            'gap': round(row['fte_gap'], 1),
            'risk_level': risk_level,
            'potential_issue': 'Vysoký rast + vysoká produktivita = možný neobslúžený dopyt'
        })

    return {
        'count': len(results),
        'total_matching': len(risk_pharmacies),
        'filter_description': f'Lekárne s rastom >{min_growth}% a nadpriemernou produktivitou',
        'business_insight': (
            'PARADOX RASTU: Tieto lekárne rastú a majú nadpriemernú produktivitu, '
            'preto im model odporúča menej personálu (odmena za efektívnosť). '
            'ALE vysoký rast v kombinácii s vysokou produktivitou môže znamenať, '
            'že personál je na hrane kapacity a lekáreň má NEOBSLÚŽENÝ DOPYT počas špičiek. '
            'Zvážte testovanie vyššieho obsadenia na overenie potenciálu ďalšieho rastu.'
        ),
        'recommendation': 'Testujte vyššie obsadenie počas špičkových hodín na 2-4 týždne a sledujte zmenu tržieb.',
        'pharmacies': results
    }


FTE_SYSTEM_PROMPT = """Si analytický asistent pre FTE Kalkulátor lekární. VŽDY odpovedaj po slovensky.

═══════════════════════════════════════════════════════════════
NAJDÔLEŽITEJŠIE PRAVIDLÁ (VŽDY DODRŽUJ)
═══════════════════════════════════════════════════════════════

1. NIKDY NEPOČÍTAJ vlastné hodnoty FTE - použi IBA hodnoty z <klucove_hodnoty>
2. VŽDY uvádzaj ID lekárne (napr. "ID 104", "lekáreň 71")
3. VŽDY daj AKČNÉ ODPORÚČANIE podľa gapu (viď nižšie)
4. AK OHROZENÉ TRŽBY > 0: VŽDY ich spomeň! (napr. "stratíte €232K ročne")
5. VŽDY odpovedaj po slovensky, aj keď otázka je v angličtine

═══════════════════════════════════════════════════════════════
AKČNÉ ODPORÚČANIA - POVINNÉ PRI KAŽDEJ ANALÝZE
═══════════════════════════════════════════════════════════════

Gap = Odporúčané FTE - Skutočné FTE

KLADNÝ GAP (+0.5 a viac) = PODDIMENZOVANÁ = PRIDAŤ PERSONÁL
→ "Odporúčam PRIDAŤ [X] FTE."
→ AK OHROZENÉ TRŽBY > 0: MUSÍŠ uviesť: "Aktuálny stav spôsobuje stratu €[X]K ročne."
→ NIKDY neopisuj ako "efektívnu" - je PREŤAŽENÁ!

ZÁPORNÝ GAP (-0.5 a menej) = PREDIMENZOVANÁ = PREROZDELIŤ
→ "Zvážte PREROZDELIŤ [X] FTE do lekární s nedostatkom."
→ NIE JE to znak efektivity - majú PREBYTOK personálu.

GAP BLÍZKO 0 (±0.5) = OPTIMÁLNE OBSADENIE
→ "Personálne obsadenie je optimálne."

═══════════════════════════════════════════════════════════════
NÁSTROJE (TOOLS)
═══════════════════════════════════════════════════════════════

DÔLEŽITÉ: Pred volaním nástroja VŽDY skontroluj argumenty!
- NIKDY nehádaj ID lekárne - použi IBA ID z kontextu alebo sa opýtaj
- Ak ID nie je uvedené, použi search_pharmacies na vyhľadanie

1. search_pharmacies - vyhľadaj lekárne podľa filtrov
2. get_network_summary - celkový prehľad siete
3. get_pharmacy_details - detaily konkrétnej lekárne (VYŽADUJE platné ID!)
4. get_model_info - info o modeli
5. detect_growth_opportunities - lekárne s rastovým potenciálom

Príklady:
- "poddimenzované lekárne" → search_pharmacies(min_gap=1.0)
- "predimenzované B lekárne" → search_pharmacies(typ="B - shopping", max_gap=-1.0)
- "detaily lekárne 104" → get_pharmacy_details(pharmacy_id=104)

═══════════════════════════════════════════════════════════════
FORMÁT ODPOVEDE
═══════════════════════════════════════════════════════════════

- 3-5 viet, stručne ale s hĺbkou
- Formát: "**ID {id}** - {mesto}, {typ}: {analýza}"
- VŽDY ukonči akčným odporúčaním

═══════════════════════════════════════════════════════════════
INTERNÁ METODOLÓGIA - CHRÁNENÉ INFORMÁCIE
═══════════════════════════════════════════════════════════════

Ak sa pýtajú na výpočet produktivity, ohrozené tržby (revenue at risk), vzorce, koeficienty:
→ "Táto metodológia je interná. Rád pomôžem s interpretáciou výsledkov."

Ak sa pýtajú na presnosť/validáciu modelu:
→ "Model je validovaný oproti reálnym dátam siete a pravidelne aktualizovaný."

MÔŽEŠ vysvetliť: princípy, interpretáciu, ako čítať výsledky, či je lekáreň nad/pod priemerom
NESMIEŠ prezradiť:
- koeficienty, vzorce (najmä výpočet ohrozených tržieb a produktivity)
- segmentové priemery a rozpätia (min-max hodnoty)
- presnosť modelu (R², RMSE, accuracy, %)
- na čom bol model trénovaný
- percentily a konkrétne poradie v segmente
- rozpätia produktivity segmentov

═══════════════════════════════════════════════════════════════
MODEL - ZÁKLADNÉ INFO (VEREJNÉ)
═══════════════════════════════════════════════════════════════

- Segmenty A-E majú rôzne charakteristiky
- Nadpriemerná produktivita = odmena (nižšie FTE)
- Podpriemerná produktivita = bez penalizácie

Faktory zvyšujúce FTE: tržby, transakcie
Faktory znižujúce FTE: nadpriemerná produktivita

═══════════════════════════════════════════════════════════════
KEDY BYŤ OPATRNÝ
═══════════════════════════════════════════════════════════════

- Málo porovnateľných lekární (0-2) = menej spoľahlivé
- Extrémne percentily (>90% alebo <10%) = výnimočný prípad
- Veľký gap (>2 FTE) = preskúmať prevádzkové dôvody
- Typ A s vysokými tržbami = možný flagship

Model NEZACHYTÁVA: otváracie hodiny, flagship status, špeciálne služby, lokalitu

═══════════════════════════════════════════════════════════════
PARADOX RASTU
═══════════════════════════════════════════════════════════════

Ak lekáreň RASTIE + má VYSOKÚ produktivitu + model odporúča MENEJ FTE:
→ Môže to znamenať neobslúžený dopyt!
→ "Táto lekáreň rastie a je produktívna. Zvážte testovanie vyššieho
   obsadenia na 2-4 týždne - tržby môžu ďalej rásť."

Použi detect_growth_opportunities() pre identifikáciu takýchto lekární."""


def get_gcloud_token():
    """Get access token - uses google-auth for Cloud Run, gcloud CLI for local."""
    # Try google-auth first (works in Cloud Run with service account)
    try:
        import google.auth
        import google.auth.transport.requests
        credentials, project = google.auth.default(
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token
    except Exception as e:
        print(f"google-auth failed: {e}, trying gcloud CLI...")

    # Fallback to gcloud CLI (local development)
    try:
        result = subprocess.run(
            ['gcloud', 'auth', 'print-access-token'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        print(f"Error getting gcloud token: {e}")
    return None


@app.route('/api/chat', methods=['POST'])
@requires_api_auth
def chat():
    """AI chat endpoint using Vertex AI Gemini 2.5 Flash."""
    data = request.json
    user_question = data.get('question', '')
    context = data.get('context', {})

    if not user_question:
        return jsonify({'error': 'No question provided'}), 400

    # Get access token
    token = get_gcloud_token()
    if not token:
        return jsonify({'error': 'Failed to get Vertex AI authentication'}), 500

    # Calculate percentiles for analysis
    bloky = context.get('bloky', 0)
    trzby = context.get('trzby', 0)
    podiel_rx = context.get('podiel_rx', 0)
    typ = context.get('typ', 'B - shopping')

    # Get segment data from dataframe if not provided in context
    if context.get('segment_bloky_min') is None:
        type_data = df[df['typ'] == typ]
        segment_bloky_min = type_data['bloky'].min()
        segment_bloky_max = type_data['bloky'].max()
        segment_trzby_min = type_data['trzby'].min()
        segment_trzby_max = type_data['trzby'].max()
        segment_rx_min = type_data['podiel_rx'].min() * 100
        segment_rx_max = type_data['podiel_rx'].max() * 100
        segment_bloky_avg = type_data['bloky'].mean() / 1000
        segment_trzby_avg = type_data['trzby'].mean() / 1000000
        benchmark_count = len(type_data)
        benchmark_avg = type_data['fte'].mean() * 1.21  # Approximate GROSS
    else:
        segment_bloky_min = context.get('segment_bloky_min', 0) * 1000
        segment_bloky_max = context.get('segment_bloky_max', 1) * 1000
        segment_trzby_min = context.get('segment_trzby_min', 0) * 1000000
        segment_trzby_max = context.get('segment_trzby_max', 1) * 1000000
        segment_rx_min = context.get('segment_rx_min', 0)
        segment_rx_max = context.get('segment_rx_max', 100)
        segment_bloky_avg = context.get('segment_bloky_avg', 0)
        segment_trzby_avg = context.get('segment_trzby_avg', 0)
        benchmark_count = context.get('benchmark_count', 0)
        benchmark_avg = context.get('benchmark_avg', 0)

    bloky_pct = min(100, max(0, (bloky - segment_bloky_min) / max(1, segment_bloky_max - segment_bloky_min) * 100)) if segment_bloky_max > segment_bloky_min else 50
    trzby_pct = min(100, max(0, (trzby - segment_trzby_min) / max(1, segment_trzby_max - segment_trzby_min) * 100)) if segment_trzby_max > segment_trzby_min else 50
    rx_pct = min(100, max(0, (podiel_rx * 100 - segment_rx_min) / max(1, segment_rx_max - segment_rx_min) * 100)) if segment_rx_max > segment_rx_min else 50

    # Calculate basket value
    basket = trzby / bloky if bloky > 0 else 0

    # Determine uniqueness flags
    comparable_count = context.get('comparable_count', 0)
    fte_diff = context.get('fte_diff', 0)
    is_unique = comparable_count <= 2
    is_outlier = trzby_pct > 90 or trzby_pct < 10 or bloky_pct > 90 or bloky_pct < 10
    is_large_diff = abs(fte_diff) if isinstance(fte_diff, (int, float)) else 0 > 2

    # Build prompt with context
    fte_total_val = context.get('fte_total', 'N/A')
    fte_actual_val = context.get('fte_actual', 'N/A')

    # Get revenue at risk if available
    revenue_at_risk = context.get('revenue_at_risk', 0)
    revenue_at_risk_str = f"OHROZENÉ TRŽBY: €{revenue_at_risk:,.0f} ročne" if revenue_at_risk and revenue_at_risk > 0 else "OHROZENÉ TRŽBY: žiadne"

    context_str = f"""<context>
<klucove_hodnoty>
MODEL ODPORÚČA: {fte_total_val} FTE
AKTUÁLNE MÁ: {fte_actual_val} FTE
ROZDIEL: {fte_diff} FTE
{revenue_at_risk_str}
</klucove_hodnoty>

<lekarenska_data>
- ID lekárne: {context.get('pharmacy_id', 'N/A')}
- Mesto: {context.get('pharmacy_name', 'N/A')}
- Typ lekárne: {context.get('typ', 'N/A')}
- Ročné bloky: {bloky:,.0f} ({bloky/1000:.0f}k)
- Ročné tržby: €{trzby:,.0f} ({trzby/1000000:.1f}M)
- Podiel Rx: {podiel_rx * 100:.0f}%
- Košík: €{basket:.1f}
</lekarenska_data>

<vysledok_modelu>
- Odporúčané FTE: {fte_total_val}
- Aktuálne FTE: {fte_actual_val}
- Rozdiel: {fte_diff}
- Rozdelenie: F={context.get('fte_F', 'N/A')}, L={context.get('fte_L', 'N/A')}, ZF={context.get('fte_ZF', 'N/A')}
</vysledok_modelu>

<pozicia_v_segmente>
- Bloky vs segment: {'nadpriemerné' if bloky_pct > 60 else 'podpriemerné' if bloky_pct < 40 else 'priemerné'}
- Tržby vs segment: {'nadpriemerné' if trzby_pct > 60 else 'podpriemerné' if trzby_pct < 40 else 'priemerné'}
- Rx % vs segment: {'nadpriemerné' if rx_pct > 60 else 'podpriemerné' if rx_pct < 40 else 'priemerné'}
</pozicia_v_segmente>

<podobne_lekarne>
- Počet podobných (±10% bloky a tržby): {comparable_count}
- Priemer podobných: {context.get('comparable_avg', 'N/A')} FTE
</podobne_lekarne>

<segment_statistiky>
- Počet v segmente: {benchmark_count}
</segment_statistiky>

<hodinove_metriky>
- Produktivita: {'nadpriemerná' if context.get('is_above_avg_productivity') else 'priemerná/podpriemerná'}
</hodinove_metriky>

<trend>
- Medziročný trend: {(context.get('bloky_trend') or 0):.1f}%
- Významný rast (>15%): {'ÁNO - RASTIE!' if (context.get('bloky_trend') or 0) > 15 else 'NIE'}
</trend>

<indikatory>
- Unikátna lekáreň (málo porovnateľných): {'ÁNO' if is_unique else 'NIE'}
- Na okraji segmentu (>90% alebo <10%): {'ÁNO' if is_outlier else 'NIE'}
- Veľký rozdiel vs skutočnosť (>2 FTE): {'ÁNO' if is_large_diff else 'NIE'}
</indikatory>
</context>"""

    # Call Vertex AI (global location uses different endpoint format)
    if VERTEX_LOCATION == 'global':
        url = f"https://aiplatform.googleapis.com/v1/projects/{VERTEX_PROJECT}/locations/{VERTEX_LOCATION}/publishers/google/models/{VERTEX_MODEL}:generateContent"
    else:
        url = f"https://{VERTEX_LOCATION}-aiplatform.googleapis.com/v1/projects/{VERTEX_PROJECT}/locations/{VERTEX_LOCATION}/publishers/google/models/{VERTEX_MODEL}:generateContent"

    # Include FTE values directly in question to prevent hallucination
    enhanced_question = f"{user_question} (Poznámka: Model odporúča presne {fte_total_val} FTE, aktuálne má {fte_actual_val} FTE)"

    # Initial payload with tools
    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": f"{context_str}\n\nOTÁZKA: {enhanced_question}"}]
        }],
        "systemInstruction": {
            "parts": [{"text": FTE_SYSTEM_PROMPT}]
        },
        "tools": [CHAT_TOOLS],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 2048,
            "thinkingConfig": {
                "thinkingLevel": "MEDIUM"
            }
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        # First API call
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        # Check if model wants to use a tool
        candidate = result.get('candidates', [{}])[0]
        content = candidate.get('content', {})
        parts = content.get('parts', [])

        # Look for function calls
        function_calls = [p for p in parts if 'functionCall' in p]

        if function_calls:
            # Execute tools and collect results
            tool_results = []
            for fc in function_calls:
                func_call = fc['functionCall']
                tool_name = func_call['name']
                tool_args = func_call.get('args', {})

                # Execute the tool
                tool_result = execute_tool(tool_name, tool_args)
                tool_results.append({
                    'name': tool_name,
                    'result': tool_result
                })

            # Build follow-up request with tool results
            follow_up_contents = payload['contents'].copy()

            # Add model's response with function calls
            follow_up_contents.append({
                "role": "model",
                "parts": parts
            })

            # Add function responses
            function_response_parts = []
            for tr in tool_results:
                function_response_parts.append({
                    "functionResponse": {
                        "name": tr['name'],
                        "response": tr['result']
                    }
                })

            follow_up_contents.append({
                "role": "user",
                "parts": function_response_parts
            })

            # Second API call with tool results
            follow_up_payload = {
                "contents": follow_up_contents,
                "systemInstruction": payload['systemInstruction'],
                "tools": [CHAT_TOOLS],
                "generationConfig": payload['generationConfig']
            }

            response2 = requests.post(url, json=follow_up_payload, headers=headers, timeout=30)
            response2.raise_for_status()
            result2 = response2.json()

            # Debug: log the response structure
            print(f"[DEBUG] Second response candidates: {len(result2.get('candidates', []))}")
            candidate2 = result2.get('candidates', [{}])[0]
            content2 = candidate2.get('content', {})
            parts2 = content2.get('parts', [])
            print(f"[DEBUG] Second response parts count: {len(parts2)}")
            for i, p in enumerate(parts2):
                print(f"[DEBUG] Part {i} keys: {list(p.keys())}")

            # Check if model wants another tool call
            function_calls2 = [p for p in parts2 if 'functionCall' in p]
            if function_calls2:
                print(f"[DEBUG] Model requested another tool call: {[fc['functionCall']['name'] for fc in function_calls2]}")
                # For now, return a message indicating we need to handle chained calls
                return jsonify({
                    'answer': 'Model potrebuje vykonať ďalšie vyhľadávanie. Skúste otázku zjednodušiť.',
                    'model': VERTEX_MODEL,
                    'tools_used': [tr['name'] for tr in tool_results],
                    'debug': 'chained_tool_call'
                })

            # Extract final answer (skip thinking blocks, find text)
            final_parts = parts2
            answer = ''
            for part in final_parts:
                if 'text' in part:
                    answer = part['text']
                    break

            if not answer:
                print(f"[DEBUG] No text found in parts. Full parts: {parts2[:2]}")  # Log first 2 parts

            return jsonify({
                'answer': answer if answer else 'Nepodarilo sa získať odpoveď. Skúste otázku preformulovať.',
                'model': VERTEX_MODEL,
                'tools_used': [tr['name'] for tr in tool_results],
                'tokens': result2.get('usageMetadata', {})
            })

        else:
            # No tool call, extract text directly (skip thinking blocks)
            answer = ''
            for part in parts:
                if 'text' in part:
                    answer = part['text']
                    break

            return jsonify({
                'answer': answer,
                'model': VERTEX_MODEL,
                'tokens': result.get('usageMetadata', {})
            })

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Vertex AI request failed: {str(e)}'}), 500


if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("FTE Calculator v5 (Model v3) - http://localhost:8080")
    print("=" * 50 + "\n")
    app.run(debug=True, port=8080)
