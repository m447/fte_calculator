"""
FTE Prediction Server v5 (Model v3 - Fixed Data Leakage)
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


def check_auth(username, password):
    """Check if username/password combination is valid."""
    return username == APP_USERNAME and password == APP_PASSWORD


def authenticate():
    """Send 401 response that enables basic auth."""
    return Response(
        'Prístup zamietnutý. Zadajte správne prihlasovacie údaje.',
        401,
        {'WWW-Authenticate': 'Basic realm="FTE Calculator"'}
    )


def requires_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
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
SEGMENT_PROD_MEANS = model_pkg.get('segment_prod_means', {
    'A - shopping premium': 7.53,
    'B - shopping': 9.80,
    'C - street +': 7.12,
    'D - street': 6.83,
    'E - poliklinika': 6.51
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
        fte_ZF_gross = max(1.0, fte_net * props['prop_ZF'] * conv['ZF']['factor'])

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


@app.route('/api/predict', methods=['POST'])
@requires_auth
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

    # ZF should be minimum 1.0 (every pharmacy needs 1 responsible pharmacist)
    if fte_ZF < 1.0:
        fte_ZF = 1.0

    # Recalculate total after ZF adjustment
    fte_pred = fte_F + fte_L + fte_ZF

    # Tolerance based on model accuracy (RMSE × 1.96 for 95% CI)
    avg_conv = (gross_factors_used['F'] + gross_factors_used['L'] + gross_factors_used['ZF']) / 3
    tolerance = fte_std * avg_conv * 1.96  # ~±1.0 FTE for 95% CI

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
@requires_auth
def get_network():
    """Get network-wide staffing analysis with predictions for all pharmacies."""
    rx_time_factor = model_pkg.get('rx_time_factor', 0.41)

    # Prepare data for predictions
    df_calc = df.copy()
    df_calc['effective_bloky'] = df_calc['bloky'] * (1 + rx_time_factor * df_calc['podiel_rx'])

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

    def calc_gross_fte_predicted(fte_net, typ):
        """Calculate GROSS FTE for predicted using role-specific factors."""
        props = model_pkg['proportions'].get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})
        conv = GROSS_CONVERSION.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        fte_F = fte_net * props['prop_F'] * conv['F']
        fte_L = fte_net * props['prop_L'] * conv['L']
        fte_ZF = max(1.0, fte_net * props['prop_ZF'] * conv['ZF'])
        return fte_F + fte_L + fte_ZF

    def calc_gross_fte_actual(row):
        """Calculate actual GROSS FTE using actual role breakdown and type-based factors."""
        conv = GROSS_CONVERSION.get(row['typ'], {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
        # Use actual role breakdown from data, not segment proportions
        fte_F = row['fte_F'] * conv['F']
        fte_L = row['fte_L'] * conv['L']
        fte_ZF = row['fte_ZF'] * conv['ZF']
        return fte_F + fte_L + fte_ZF

    df_calc['predicted_fte'] = df_calc.apply(
        lambda row: calc_gross_fte_predicted(row['predicted_fte_net'], row['typ']), axis=1)
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

    def pharmacy_to_dict(row):
        return {
            'id': int(row['id']),
            'mesto': row['mesto'],
            'typ': row['typ'],
            'actual_fte': round(row['actual_fte'], 1),
            'predicted_fte': round(row['predicted_fte'], 1),
            'diff': round(row['fte_diff'], 1),
            'bloky': int(row['bloky']),
            'trzby': int(row['trzby']),
            'podiel_rx': round(row['podiel_rx'] * 100, 0)
        }

    # All pharmacies for filtering
    all_pharmacies = [pharmacy_to_dict(row) for _, row in df_calc.iterrows()]

    # Get unique regions for filter
    regions = sorted(df_calc['regional'].dropna().unique().tolist())

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
        'pharmacies': all_pharmacies,
        'filters': {
            'regions': regions,
            'types': ['A - shopping premium', 'B - shopping', 'C - street +', 'D - street', 'E - poliklinika']
        }
    })


@app.route('/api/pharmacies', methods=['GET'])
@requires_auth
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


@app.route('/api/pharmacy/<int:pharmacy_id>', methods=['GET'])
@requires_auth
def get_pharmacy(pharmacy_id):
    """Get details for a specific pharmacy including predicted FTE (same as network)."""
    pharmacy = df[df['id'] == pharmacy_id]
    if len(pharmacy) == 0:
        return jsonify({'error': 'Pharmacy not found'}), 404

    row = pharmacy.iloc[0]
    typ = row['typ']

    # Type-based gross factors (same as network for consistency)
    GROSS_CONV = {
        'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
        'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
        'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
        'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
        'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
    }
    conv = GROSS_CONV.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
    props = model_pkg['proportions'].get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})

    # Calculate actual GROSS FTE using actual role breakdown and type-based factors
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

    # Convert predicted NET to GROSS using type-based factors (same as network)
    GROSS_CONVERSION_PRED = {
        'A - shopping premium': {'F': 1.17, 'L': 1.22, 'ZF': 1.23},
        'B - shopping': {'F': 1.22, 'L': 1.22, 'ZF': 1.18},
        'C - street +': {'F': 1.23, 'L': 1.22, 'ZF': 1.20},
        'D - street': {'F': 1.29, 'L': 1.22, 'ZF': 1.25},
        'E - poliklinika': {'F': 1.27, 'L': 1.24, 'ZF': 1.23},
    }
    conv_pred = GROSS_CONVERSION_PRED.get(typ, {'F': 1.21, 'L': 1.22, 'ZF': 1.20})
    props = model_pkg['proportions'].get(typ, {'prop_F': 0.4, 'prop_L': 0.4, 'prop_ZF': 0.2})

    fte_F_pred = predicted_fte_net * props['prop_F'] * conv_pred['F']
    fte_L_pred = predicted_fte_net * props['prop_L'] * conv_pred['L']
    fte_ZF_pred = max(1.0, predicted_fte_net * props['prop_ZF'] * conv_pred['ZF'])
    predicted_fte = fte_F_pred + fte_L_pred + fte_ZF_pred

    # Calculate difference
    fte_diff = predicted_fte - actual_fte

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
        'gross_factors': conv  # Type-based factors used for both actual and predicted
    })


@app.route('/api/benchmarks', methods=['GET'])
@requires_auth
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

FTE_SYSTEM_PROMPT = """Si analytický asistent pre FTE Kalkulátor lekární Dr.Max. Poskytuj hlbokú analýzu a interpretáciu výsledkov.

TVOJA ÚLOHA:
- Analyzovať pozíciu lekárne v segmente
- Identifikovať výnimočné prípady (flagship, unikátne lekárne)
- Vysvetliť prečo model odporúča konkrétny počet FTE
- Upozorniť na faktory ktoré model nezachytáva

MODEL:
- Typ: Ridge Regression (lineárna regresia s L2 regularizáciou)
- Tréningové dáta: 286 lekární, obdobie Sep 2020 - Aug 2021
- Presnosť (R²): 87.3%, RMSE: ±0.52 FTE

VSTUPY MODELU:
- typ: kategória lekárne (A-E)
- bloky: ročný počet transakcií
- trzby: ročné tržby v EUR
- podiel_rx: Rx recepty sú časovo náročnejšie, vyšší podiel = viac personálu

VÝSTUP:
- GROSS FTE (hrubé úväzky) = NET × ~1.2
- F (Farmaceut), L (Laborant), ZF (Zodpovedný farmaceut)

ANALÝZA POZÍCIE V SEGMENTE:
- Percentily ukazujú kde lekáreň stojí v porovnaní s ostatnými rovnakého typu
- >90% = špičková lekáreň, vyžaduje špeciálnu pozornosť
- <10% = malá lekáreň, model môže byť menej presný

KEDY UPOZORNIŤ NA OPATRNOSŤ:
1. Málo porovnateľných lekární (0-2) = model extrapoluje, odporúčanie menej spoľahlivé
2. Lekáreň je na okraji segmentu (>90% alebo <10% percentil) = výnimočný prípad
3. Veľký rozdiel medzi odporúčaním a skutočnosťou (>2 FTE) = preskúmať prevádzkové dôvody
4. Shopping premium (typ A) s vysokými tržbami = možný flagship store s osobitnými požiadavkami
5. Nízky košík pri vysokom obrate = veľa rýchlych transakcií, náročnejšia prevádzka

PREVÁDZKOVÉ FAKTORY KTORÉ MODEL MOMENTÁLNE NEZACHYTÁVA:
- Otváracie hodiny (rozšírené vs štandardné)
- Flagship/showcase status
- Špeciálne služby (konzultácie, príprava liekov)
- Lokalita (turistická oblasť, nemocnica)
- Sezónnosť a špičky

PRAVIDLÁ ODPOVEDE:
- Odpovedaj 3-5 vetami, stručne ale s hĺbkou
- Ak je lekáreň výnimočná, povedz to jasne
- Pri "predimenzované/poddimenzované" vždy zvážiť či ide o reálny problém alebo odôvodnený stav
- Používaj slovenčinu

KRITICKÉ - HODNOTY FTE:
- NIKDY NEPOČÍTAJ vlastné hodnoty FTE!
- Použi IBA hodnoty označené >>> ... <<< vyššie
- Ak vidíš ">>> ODPORÚČANÉ FTE = 8.6 <<<", povedz presne 8.6, nie 8.8 ani inú hodnotu
- Toto je najdôležitejšie pravidlo - porušenie = nesprávna odpoveď"""


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
@requires_auth
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

    context_str = f"""=== KĽÚČOVÉ HODNOTY (POUŽI PRESNE TIETO!) ===
MODEL ODPORÚČA: {fte_total_val} FTE
AKTUÁLNE MÁ: {fte_actual_val} FTE
ROZDIEL: {fte_diff} FTE
===============================================

KONTEXT VÝPOČTU:
- Lekáreň: {context.get('pharmacy_name', 'N/A')}
- Typ lekárne: {context.get('typ', 'N/A')}
- Ročné bloky: {bloky:,.0f} ({bloky/1000:.0f}k)
- Ročné tržby: €{trzby:,.0f} ({trzby/1000000:.1f}M)
- Podiel Rx: {podiel_rx * 100:.0f}%
- Košík: €{basket:.1f}

VÝSLEDOK MODELU:
- Odporúčané FTE: {fte_total_val}
- Aktuálne FTE: {fte_actual_val}
- Rozdiel: {fte_diff}
- Rozdelenie: F={context.get('fte_F', 'N/A')}, L={context.get('fte_L', 'N/A')}, ZF={context.get('fte_ZF', 'N/A')}

POZÍCIA V SEGMENTE (percentily, 0%=minimum, 100%=maximum):
- Bloky: {bloky_pct:.0f}% (rozsah: {segment_bloky_min/1000:.0f}k - {segment_bloky_max/1000:.0f}k)
- Tržby: {trzby_pct:.0f}% (rozsah: {segment_trzby_min/1000000:.1f}M - {segment_trzby_max/1000000:.1f}M €)
- Rx %: {rx_pct:.0f}% (rozsah: {segment_rx_min:.0f}% - {segment_rx_max:.0f}%)

PODOBNÉ LEKÁRNE (±10% bloky a tržby):
- Počet podobných: {comparable_count}
- Priemer podobných: {context.get('comparable_avg', 'N/A')} FTE

SEGMENT ŠTATISTIKY:
- Počet v segmente: {benchmark_count}
- Priemer FTE: {benchmark_avg:.1f}
- Priemer Rx: {(segment_rx_min + segment_rx_max) / 2:.0f}%

HODINOVÉ METRIKY:
- Bloky/hod: {context.get('bloky_per_hour', 'N/A')} (segment: {context.get('segment_bloky_hour_min', 'N/A')} - {context.get('segment_bloky_hour_max', 'N/A')})
- Tržby/hod: {context.get('trzby_per_hour', 'N/A')} €

INDIKÁTORY PRE ANALÝZU:
- Unikátna lekáreň (málo porovnateľných): {'ÁNO' if is_unique else 'NIE'}
- Na okraji segmentu (>90% alebo <10%): {'ÁNO' if is_outlier else 'NIE'}
- Veľký rozdiel vs skutočnosť (>2 FTE): {'ÁNO' if is_large_diff else 'NIE'}"""

    # Call Vertex AI (global location uses different endpoint format)
    if VERTEX_LOCATION == 'global':
        url = f"https://aiplatform.googleapis.com/v1/projects/{VERTEX_PROJECT}/locations/{VERTEX_LOCATION}/publishers/google/models/{VERTEX_MODEL}:generateContent"
    else:
        url = f"https://{VERTEX_LOCATION}-aiplatform.googleapis.com/v1/projects/{VERTEX_PROJECT}/locations/{VERTEX_LOCATION}/publishers/google/models/{VERTEX_MODEL}:generateContent"

    # Include FTE values directly in question to prevent hallucination
    enhanced_question = f"{user_question} (Poznámka: Model odporúča presne {fte_total_val} FTE, aktuálne má {fte_actual_val} FTE)"

    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": f"{context_str}\n\nOTÁZKA: {enhanced_question}"}]
        }],
        "systemInstruction": {
            "parts": [{"text": FTE_SYSTEM_PROMPT}]
        },
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 2048
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        # Extract text from response
        answer = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')

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
