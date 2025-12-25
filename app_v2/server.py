"""
FTE Kalkulačka v5.1 - Refactored Version
Dr.Max Pharmacy Staffing Tool

REFACTORED VERSION (app_v2):
- Imports business logic from app_v2.core (single source of truth)
- Imports configuration from app_v2.config
- Reduces code duplication while maintaining identical functionality

Run: python app_v2/server.py
Access: http://localhost:5001
"""

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from functools import wraps
import pandas as pd
import numpy as np
import os
import subprocess
import requests
import json
from pathlib import Path

# Import from app_v2.core - single source of truth for business logic
from app_v2.core import (
    SEGMENT_PROPORTIONS,
    GROSS_CONVERSION,
    GROSS_CONVERSION_WITH_CV,
    SEGMENT_PROD_MEANS,
    FTE_GAP_NOTABLE,
    FTE_GAP_URGENT,
    FTE_GAP_OPTIMIZE,
    FTE_GAP_OUTLIER,
    get_gross_factors,
    calculate_pharmacy_fte,
    calculate_fte_from_inputs,
    calculate_sensitivity,
    is_above_avg_productivity,
    calculate_prod_pct,
    calculate_revenue_at_risk,
    prepare_fte_dataframe,
    load_model,
    get_model,
    get_rx_time_factor,
    get_feature_cols,
    validate_pharmacy_dataframe,
    DataValidationError,
)

# Import configuration and logger
from app_v2.config import (
    PROJECT_ROOT,
    DATA_PATH,
    STATIC_DIR,
    APP_PASSWORD,
    API_KEY,
    ANTHROPIC_API_KEY,
    HOST,
    PORT,
    DEBUG,
    logger,
    setup_logging,
)

# Import Gemini agent components
from app_v2.gemini_agent import (
    VERTEX_PROJECT,
    VERTEX_LOCATION,
    VERTEX_MODEL,
    CHAT_TOOLS,
    FTE_SYSTEM_PROMPT,
    execute_tool,
    get_gcloud_token,
)

app = Flask(__name__, static_folder=str(STATIC_DIR))
CORS(app)

# Basic Auth Configuration
APP_USERNAME = os.environ.get('APP_USERNAME', 'drmax')

# GCS Logging Configuration
AGENT_LOG_BUCKET = os.environ.get('AGENT_LOG_BUCKET', 'drmax-agent-logs')
AGENT_LOG_ENABLED = os.environ.get('AGENT_LOG_ENABLED', 'true').lower() == 'true'

def log_agent_request_to_gcs(log_data: dict):
    """
    Log agent request/response to Google Cloud Storage.

    Stores JSON files in format: gs://bucket/agent-logs/YYYY/MM/DD/request_id.json
    """
    if not AGENT_LOG_ENABLED:
        return

    try:
        from google.cloud import storage
        from datetime import datetime
        import json

        client = storage.Client()
        bucket = client.bucket(AGENT_LOG_BUCKET)

        # Create path: agent-logs/2024/12/22/abc12345.json
        now = datetime.utcnow()
        blob_path = f"agent-logs/{now.year}/{now.month:02d}/{now.day:02d}/{log_data.get('request_id', 'unknown')}.json"

        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(log_data, ensure_ascii=False, indent=2, default=str),
            content_type='application/json'
        )
        logger.info(f"Logged to GCS: {blob_path}", extra={"request_id": log_data.get("request_id", "")})

    except Exception as e:
        # Don't fail the request if logging fails
        logger.warning(f"GCS logging failed: {type(e).__name__}: {e}")


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


# ============================================================
# INITIALIZATION
# ============================================================

# Load model and data at startup
model_pkg = load_model(PROJECT_ROOT)
logger.info(f"Loaded model v{model_pkg.get('version', '5')}")

# Load and validate reference data
try:
    df = pd.read_csv(DATA_PATH)
    df = validate_pharmacy_dataframe(df)
    defaults = df.median(numeric_only=True).to_dict()
    logger.info(f"Loaded and validated {len(df)} pharmacies from {DATA_PATH}")
except DataValidationError as e:
    logger.error(f"Data validation failed: {e}")
    raise SystemExit(f"Cannot start server: {e}")


# ============================================================
# WEB ROUTES
# ============================================================

@app.route('/')
@requires_auth
def index():
    return send_from_directory(str(STATIC_DIR), 'index-v2.html')


@app.route('/v1')
@requires_auth
def index_v1():
    return send_from_directory(str(STATIC_DIR), 'index.html')


@app.route('/utilization')
@requires_auth
def utilization():
    return send_from_directory(str(STATIC_DIR), 'utilization.html')


# ============================================================
# HELPER FUNCTIONS
# ============================================================
# Note: calculate_sensitivity() and calculate_fte_from_inputs() are now in core.py
# This ensures single source of truth for all FTE calculations.


# ============================================================
# API ENDPOINTS
# ============================================================

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

    # === Use core.calculate_fte_from_inputs() - single source of truth ===
    fte_result = calculate_fte_from_inputs(
        bloky=bloky,
        trzby=trzby,
        typ=typ,
        podiel_rx=podiel_rx,
        productivity_z=productivity_z,
        variability_z=variability_z,
        pharmacy_id=int(pharmacy_id) if pharmacy_id is not None else None,
        defaults=defaults
    )

    # Extract values from core calculation
    fte_pred = fte_result['fte_total']
    fte_F = fte_result['fte_F']
    fte_L = fte_result['fte_L']
    fte_ZF = fte_result['fte_ZF']
    tolerance = fte_result['tolerance']
    gross_factors_used = fte_result['gross_factors']
    use_pharmacy_factors = fte_result['use_pharmacy_factors']
    conv = fte_result['conv_with_cv']
    effective_bloky = fte_result['effective_bloky']

    # RX time factor for benchmark calculations
    rx_time_factor = get_rx_time_factor()

    # Average conversion factor for benchmarks
    avg_conv = sum(gross_factors_used.values()) / 3

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
    pharmacy_productivity = effective_bloky / fte_pred if fte_pred > 0 else 0
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
                # Use shared calculate_pharmacy_fte() - single source of truth
                pharmacy_fte = calculate_pharmacy_fte(p_row)
                actual_fte = pharmacy_fte['actual_fte']
        except ValueError:
            pass  # Invalid pharmacy_id format

    # Revenue at risk - use shared function
    is_above_avg_productivity_val = productivity_z > 0
    revenue_at_risk = calculate_revenue_at_risk(fte_pred, actual_fte, trzby, is_above_avg_productivity_val)

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
            'net': fte_result['fte_net']  # Original NET FTE for reference
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
            'effective_bloky': effective_bloky,
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
            'recommended': round(effective_bloky / fte_pred / 1000, 1) if fte_pred > 0 else None,
            'pharmacy': round(pharmacy_productivity, 0),
            'network_avg': round(network_avg_productivity, 0),
            'vs_avg_pct': round(productivity_vs_avg, 0)
        },
        'sensitivity': calculate_sensitivity(bloky, trzby, podiel_rx, typ, defaults)
    })


@app.route('/api/network', methods=['GET'])
@requires_api_auth
def get_network():
    """Get network-wide staffing analysis with predictions for all pharmacies."""
    # Use shared prepare_fte_dataframe() - single source of truth
    df_calc = prepare_fte_dataframe(df, include_revenue_at_risk=True)

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

        # Count by status (using FTE_GAP_NOTABLE from core)
        ok_count = len(seg[(seg['fte_gap'] >= -FTE_GAP_NOTABLE) & (seg['fte_gap'] <= FTE_GAP_NOTABLE)])
        under_count = len(seg[seg['fte_gap'] > FTE_GAP_NOTABLE])
        over_count = len(seg[seg['fte_gap'] < -FTE_GAP_NOTABLE])

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

    # Outliers (|diff| > FTE_GAP_OUTLIER)
    understaffed = df_calc[df_calc['fte_gap'] > FTE_GAP_OUTLIER].nlargest(15, 'fte_gap')
    overstaffed = df_calc[df_calc['fte_gap'] < -FTE_GAP_OUTLIER].nsmallest(15, 'fte_gap')

    def pharmacy_to_dict(row, include_priority_data=False):
        result = {
            'id': int(row['id']),
            'mesto': row['mesto'],
            'typ': row['typ'],
            'actual_fte': round(row['actual_fte'], 1),
            'predicted_fte': round(row['predicted_fte'], 1),
            'diff': round(row['fte_gap'], 1),
            'bloky': int(row['bloky']),
            'trzby': int(row['trzby']),
            'podiel_rx': round(row['podiel_rx'] * 100, 0),
            'is_above_avg_productivity': row['is_above_avg']
        }
        if include_priority_data:
            # Add fields needed for priority dashboard
            bloky_trend = round(row.get('bloky_trend', 0) * 100, 0)
            result.update({
                'is_above_avg_productivity': row['is_above_avg'],
                'prod_pct': row['prod_pct'],
                'bloky_trend': bloky_trend,
                'revenue_at_risk': int(row['revenue_at_risk'])
            })
        return result

    # All pharmacies for filtering (include priority data for revenue_at_risk)
    all_pharmacies = [pharmacy_to_dict(row, include_priority_data=True) for _, row in df_calc.iterrows()]

    # Get unique regions for filter
    regions = sorted(df_calc['regional'].dropna().unique().tolist())

    # Priority categories for dashboard
    # Urgent: understaffed (gap > FTE_GAP_URGENT) + above-avg productivity (losing revenue)
    urgent_candidates = df_calc[df_calc['fte_gap'] > FTE_GAP_URGENT].copy()
    urgent_list = []
    for _, row in urgent_candidates.iterrows():
        if row['is_above_avg']:
            urgent_list.append(pharmacy_to_dict(row, include_priority_data=True))
    # Sort by revenue_at_risk descending
    urgent_list.sort(key=lambda x: x.get('revenue_at_risk', 0), reverse=True)

    # Optimize: overstaffed (gap < -FTE_GAP_OPTIMIZE) - can reallocate
    optimize_candidates = df_calc[df_calc['fte_gap'] < -FTE_GAP_OPTIMIZE].copy()
    optimize_list = [pharmacy_to_dict(row, include_priority_data=True) for _, row in optimize_candidates.sort_values('fte_gap').iterrows()]

    # Monitor: growing significantly (bloky_trend > 15%) - watch for future needs
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
            'understaffed_count': len(df_calc[df_calc['fte_gap'] > FTE_GAP_OUTLIER]),
            'overstaffed_count': len(df_calc[df_calc['fte_gap'] < -FTE_GAP_OUTLIER])
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
    # Use shared prepare_fte_dataframe() - single source of truth
    df_calc = prepare_fte_dataframe(df, include_revenue_at_risk=True)

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
        result = result[result['is_above_avg'] == True]
    elif productivity == 'below':
        result = result[result['is_above_avg'] == False]

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
            'fte_gap': round(row['fte_gap'], 1),
            'is_above_avg': row['is_above_avg'],
            'revenue_at_risk': int(row['revenue_at_risk'])
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
        'rx_time_factor': get_rx_time_factor(),
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

    # Use shared calculate_pharmacy_fte() - single source of truth
    fte_result = calculate_pharmacy_fte(row)

    # Use shared helper functions - single source of truth
    is_above_avg = is_above_avg_productivity(row)
    revenue_at_risk = calculate_revenue_at_risk(
        fte_result['predicted_fte'], fte_result['actual_fte'], row['trzby'], is_above_avg
    )

    return jsonify({
        'id': int(row['id']),
        'mesto': row['mesto'],
        'typ': row['typ'],
        'bloky': int(row['bloky']),
        'trzby': float(row['trzby']),
        'podiel_rx': float(row['podiel_rx']),
        'actual_fte': round(fte_result['actual_fte'], 1),
        'actual_fte_F': round(fte_result['actual_fte_F'], 1),
        'actual_fte_L': round(fte_result['actual_fte_L'], 1),
        'actual_fte_ZF': round(fte_result['actual_fte_ZF'], 1),
        'predicted_fte': round(fte_result['predicted_fte'], 1),
        'predicted_fte_F': round(fte_result['predicted_fte_F'], 1),
        'predicted_fte_L': round(fte_result['predicted_fte_L'], 1),
        'predicted_fte_ZF': round(fte_result['predicted_fte_ZF'], 1),
        'fte_diff': round(fte_result['fte_diff'], 1),
        'revenue_at_risk': revenue_at_risk,
        'gross_factors': fte_result['gross_factors'],
        'prod_residual': round(float(row.get('prod_residual', 0)), 2),
        'is_above_avg_productivity': is_above_avg,
        'prod_pct': calculate_prod_pct(row),
        'bloky_trend': round(float(row.get('bloky_trend', 0)) * 100, 0)
    })


# Load historical revenue data for trend charts
from app_v2.config import REVENUE_MONTHLY_PATH, REVENUE_ANNUAL_PATH

if REVENUE_MONTHLY_PATH.exists() and REVENUE_ANNUAL_PATH.exists():
    df_revenue_monthly = pd.read_csv(REVENUE_MONTHLY_PATH)
    df_revenue_annual = pd.read_csv(REVENUE_ANNUAL_PATH)
    REVENUE_DATA_AVAILABLE = True
else:
    df_revenue_monthly = None
    df_revenue_annual = None
    REVENUE_DATA_AVAILABLE = False


@app.route('/api/pharmacy/<int:pharmacy_id>/revenue', methods=['GET'])
@requires_api_auth
def get_pharmacy_revenue(pharmacy_id):
    """Get historical revenue data for a pharmacy (for trend chart)."""
    if not REVENUE_DATA_AVAILABLE:
        return jsonify({'error': 'Revenue data not available'}), 404

    # Get monthly data for this pharmacy
    pharm_monthly = df_revenue_monthly[df_revenue_monthly['id'] == pharmacy_id]
    if len(pharm_monthly) == 0:
        return jsonify({'error': 'No revenue data for this pharmacy'}), 404

    # Organize by year
    monthly = {}
    for year in [2019, 2020, 2021]:
        year_data = pharm_monthly[pharm_monthly['year'] == year].sort_values('month')
        if len(year_data) > 0:
            monthly[year] = [
                {'month': int(row['month']), 'revenue': float(row['revenue'])}
                for _, row in year_data.iterrows()
            ]

    # Get YoY growth data
    pharm_annual = df_revenue_annual[df_revenue_annual['id'] == pharmacy_id]
    yoy_2020 = None
    yoy_2021 = None
    if len(pharm_annual) > 0:
        annual_row = pharm_annual.iloc[0]
        yoy_2020 = annual_row['yoy_growth_2020'] if pd.notna(annual_row['yoy_growth_2020']) else None
        yoy_2021 = annual_row['yoy_growth_2021'] if pd.notna(annual_row['yoy_growth_2021']) else None

    # Determine current month (last month with 2021 data)
    current_month = 8  # Default to August (last month in data)
    if 2021 in monthly and len(monthly[2021]) > 0:
        current_month = max(d['month'] for d in monthly[2021])

    # Calculate 3-month forecast using 55% seasonal adjustment (optimal from backtest: 11.1% MAPE)
    # Formula: forecast = recent_avg × (0.45 + 0.55 × relative_seasonal_factor)
    # Seasonal factors from 2019 (pre-COVID baseline), normalized to annual avg = 1.0
    forecast = []
    seasonal_factors = {
        1: 1.003, 2: 0.981, 3: 0.990, 4: 0.959, 5: 0.992, 6: 0.962,
        7: 0.954, 8: 0.887, 9: 1.028, 10: 1.082, 11: 1.026, 12: 1.135
    }

    if 2021 in monthly and len(monthly[2021]) >= 3:
        # Get last 3 months of data
        sorted_2021 = sorted(monthly[2021], key=lambda x: x['month'])
        last_3_months = sorted_2021[-3:]
        recent_avg = sum(d['revenue'] for d in last_3_months) / 3

        # Calculate base period seasonal strength
        base_months = [d['month'] for d in last_3_months]
        base_seasonal = sum(seasonal_factors.get(m, 1.0) for m in base_months) / 3

        # Forecast next 3 months with relative seasonal adjustment
        seasonal_weight = 0.55
        for i in range(1, 4):  # Next 3 months
            forecast_month = current_month + i
            if forecast_month > 12:
                forecast_month -= 12  # Wrap to next year

            target_seasonal = seasonal_factors.get(forecast_month, 1.0)
            relative_factor = target_seasonal / base_seasonal if base_seasonal > 0 else 1.0

            adjusted = recent_avg * ((1 - seasonal_weight) + seasonal_weight * relative_factor)
            forecast.append({
                'month': forecast_month,
                'revenue': round(adjusted, 2)
            })

    return jsonify({
        'monthly': monthly,
        'yoy_growth_2020': yoy_2020,
        'yoy_growth_2021': yoy_2021,
        'current_month': current_month,
        'forecast': forecast
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


# ============================================================
# VERTEX AI GEMINI CHAT
# (Tools and configuration imported from gemini_agent.py)
# ============================================================

# Wrapper to pass dataframe to execute_tool
def execute_gemini_tool(tool_name: str, args: dict):
    """Execute a Gemini tool with the global dataframe."""
    return execute_tool(tool_name, args, df)


@app.route('/api/chat', methods=['POST'])
@requires_api_auth
def chat():
    """AI chat endpoint using Vertex AI Gemini 2.5 Flash."""
    data = request.json
    user_question = data.get('question', '')
    context = data.get('context', {})

    # Debug: log productivity context
    import sys
    is_above = context.get('is_above_avg_productivity')
    logger.debug(f"Chat context - is_above_avg_productivity: {is_above} (type: {type(is_above).__name__})")
    logger.debug(f"Chat context - prod_residual: {context.get('prod_residual')}")
    logger.debug(f"Productivity text will be: {'nadpriemerná' if is_above else 'priemerná/podpriemerná'}")

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
- is_above_avg: {str(bool(context.get('is_above_avg_productivity'))).lower()}
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

    # Debug: log the productivity part of context
    logger.debug(f"Context produktivita line: {'nadpriemerná' if context.get('is_above_avg_productivity') else 'priemerná/podpriemerná'}")

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
            "maxOutputTokens": 4096,
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
        # Debug: log request details
        logger.debug(f"API URL: {url}")
        logger.debug(f"Token length: {len(token) if token else 0}")
        logger.debug(f"Token prefix: {token[:30] if token else 'None'}...")

        # First API call
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        logger.debug(f"Response status: {response.status_code}")
        if response.status_code != 200:
            logger.debug(f"Response body: {response.text[:500]}")
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
                tool_result = execute_gemini_tool(tool_name, tool_args)
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
            logger.debug(f"Second response candidates: {len(result2.get('candidates', []))}")
            candidate2 = result2.get('candidates', [{}])[0]
            content2 = candidate2.get('content', {})
            parts2 = content2.get('parts', [])
            logger.debug(f"Second response parts count: {len(parts2)}")
            for i, p in enumerate(parts2):
                logger.debug(f"Part {i} keys: {list(p.keys())}")

            # Check if model wants another tool call - support up to 2 more rounds
            all_tools_used = [tr['name'] for tr in tool_results]
            current_contents = follow_up_contents
            current_parts = parts2
            latest_result = result2

            for round_num in range(2):  # Up to 2 additional rounds
                function_calls_next = [p for p in current_parts if 'functionCall' in p]
                if not function_calls_next:
                    break  # No more tool calls needed

                logger.debug(f"Round {round_num + 2}: Model requested tool calls: {[fc['functionCall']['name'] for fc in function_calls_next]}")

                # Execute additional tools
                additional_results = []
                for fc in function_calls_next:
                    func_call = fc['functionCall']
                    tool_name = func_call['name']
                    tool_args = func_call.get('args', {})
                    tool_result = execute_gemini_tool(tool_name, tool_args)
                    additional_results.append({
                        'name': tool_name,
                        'result': tool_result
                    })
                    all_tools_used.append(tool_name)

                # Build next request
                current_contents = current_contents.copy()
                current_contents.append({
                    "role": "model",
                    "parts": current_parts
                })

                additional_response_parts = []
                for tr in additional_results:
                    additional_response_parts.append({
                        "functionResponse": {
                            "name": tr['name'],
                            "response": tr['result']
                        }
                    })

                current_contents.append({
                    "role": "user",
                    "parts": additional_response_parts
                })

                # Make API call
                next_payload = {
                    "contents": current_contents,
                    "systemInstruction": payload['systemInstruction'],
                    "tools": [CHAT_TOOLS],
                    "generationConfig": payload['generationConfig']
                }

                response_next = requests.post(url, json=next_payload, headers=headers, timeout=30)
                response_next.raise_for_status()
                result_next = response_next.json()

                candidate_next = result_next.get('candidates', [{}])[0]
                content_next = candidate_next.get('content', {})
                current_parts = content_next.get('parts', [])
                parts2 = current_parts  # Update for final answer extraction
                latest_result = result_next

            # Extract final answer (skip thinking blocks, find text)
            final_parts = parts2
            answer = ''
            for part in final_parts:
                if 'text' in part:
                    answer = part['text']
                    break

            if not answer:
                logger.debug(f"No text found in parts. Full parts: {parts2[:2]}")

            return jsonify({
                'answer': answer if answer else 'Nepodarilo sa získať odpoveď. Skúste otázku preformulovať.',
                'model': VERTEX_MODEL,
                'tools_used': all_tools_used,
                'tokens': latest_result.get('usageMetadata', {})
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
        # Log detailed error for debugging
        error_details = str(e)
        if hasattr(e, 'response') and e.response is not None:
            error_details += f" | Response: {e.response.text[:500]}"
        logger.error(f"Vertex AI request failed: {error_details}")
        return jsonify({'error': f'Vertex AI request failed: {str(e)}'}), 500


# === CLAUDE AGENT ENDPOINT ===

# Initialize agent (lazy loading)
_agent = None

def get_agent():
    """Get or create the Claude agent instance."""
    global _agent
    if _agent is None:
        try:
            from app_v2.claude_agent import DrMaxAgent
            data_path = PROJECT_ROOT / 'data'
            # Predictions are now pre-calculated in CSV - no cache needed
            _agent = DrMaxAgent(data_path)
            logger.info("Claude Agent initialized successfully")
        except Exception as e:
            logger.warning(f"Claude Agent not available: {e}")
            _agent = None
    return _agent


@app.route('/api/agent/analyze', methods=['POST'])
@requires_api_auth
def agent_analyze():
    """
    Claude Agent endpoint for complex multi-step analysis.

    Uses sanitized data with indexed productivity values.
    Protected information (formulas, coefficients) is never exposed.
    """
    import uuid
    request_id = str(uuid.uuid4())[:8]

    agent = get_agent()

    if agent is None:
        return jsonify({
            'error': 'Claude Agent not available. Set ANTHROPIC_API_KEY environment variable.',
            'fallback': 'Use /api/chat endpoint instead'
        }), 503

    data = request.json
    prompt = data.get('prompt', '') if data else ''

    # P1 FIX: Input validation
    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400

    if len(prompt) > 2000:
        return jsonify({'error': 'Prompt too long (max 2000 characters)'}), 400

    # Strip and sanitize
    prompt = prompt.strip()

    logger.info(f"Agent request: {prompt[:100]}...", extra={"request_id": request_id})

    try:
        from datetime import datetime
        request_timestamp = datetime.utcnow().isoformat() + 'Z'

        # Run synchronous analysis
        result = agent.analyze_sync(prompt, request_id=request_id)

        if 'error' in result and result['error']:
            logger.error(f"Agent error: {result['error']}", extra={"request_id": request_id})
            # Log error to GCS
            log_agent_request_to_gcs({
                'request_id': request_id,
                'timestamp': request_timestamp,
                'prompt': prompt,
                'status': 'error',
                'error': result['error'],
                'duration_seconds': result.get('duration_seconds')
            })
            return jsonify({'error': result['error']}), 500

        logger.info(f"Agent complete: tools={result.get('tools_used', [])}", extra={"request_id": request_id})

        # Log successful request to GCS (includes reasoning)
        log_agent_request_to_gcs({
            'request_id': request_id,
            'timestamp': request_timestamp,
            'prompt': prompt,
            'status': 'success',
            'response': result['response'],
            'tools_used': result['tools_used'],
            'tool_call_count': result.get('tool_call_count', 0),
            'duration_seconds': result.get('duration_seconds'),
            'architecture': result.get('architecture'),
            'reasoning': result.get('_reasoning', {})
        })

        return jsonify({
            'response': result['response'],
            'tools_used': result['tools_used'],
            'tool_call_count': result.get('tool_call_count', 0),
            'duration_seconds': result.get('duration_seconds'),
            'model': 'claude-opus-4-5',
            'request_id': request_id,
            'note': 'Productivity values are indexed (100 = segment average)'
        })

    except Exception as e:
        # P1 FIX: Don't expose internal errors
        logger.exception(f"Agent exception: {type(e).__name__}: {e}", extra={"request_id": request_id})
        # Log exception to GCS
        log_agent_request_to_gcs({
            'request_id': request_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z' if 'datetime' in dir() else None,
            'prompt': prompt,
            'status': 'exception',
            'error_type': type(e).__name__,
            'error': str(e)
        })
        return jsonify({
            'error': 'Agent processing failed. Please try again.',
            'request_id': request_id
        }), 500


@app.route('/api/agent/analyze/stream', methods=['POST'])
@requires_api_auth
def agent_analyze_stream():
    """
    Claude Agent endpoint with Server-Sent Events (SSE) streaming.

    Provides real-time progress updates during the Plan → Execute → Synthesize cycle.
    This makes the 10-30 second wait feel much shorter by showing what's happening.

    Event types:
        - status: Current phase (planning, executing, synthesizing)
        - tool: Tool being executed
        - progress: Progress percentage
        - result: Final result
        - error: Error message
    """
    import uuid
    import time
    from datetime import datetime

    request_id = str(uuid.uuid4())[:8]

    # Extract request data BEFORE generator (request context won't be available inside generator)
    data = request.json
    prompt = data.get('prompt', '').strip() if data else ''

    def generate():
        """SSE generator function."""
        nonlocal prompt
        try:
            # Send initial status
            yield f"data: {json.dumps({'type': 'status', 'phase': 'initializing', 'message': 'Inicializujem agenta...', 'request_id': request_id})}\n\n"

            agent = get_agent()
            if agent is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Claude Agent nie je dostupný. Nastavte ANTHROPIC_API_KEY.'})}\n\n"
                return

            if not prompt:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Žiadny prompt nebol poskytnutý.'})}\n\n"
                return

            if len(prompt) > 2000:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Prompt je príliš dlhý (max 2000 znakov).'})}\n\n"
                return

            start_time = time.time()

            # Phase 1: Planning
            yield f"data: {json.dumps({'type': 'status', 'phase': 'planning', 'message': 'Opus plánuje analýzu...', 'progress': 10})}\n\n"

            # Execute analysis with progress callbacks
            logger.info(f"SSE Agent request: {prompt[:100]}...", extra={"request_id": request_id})

            # Phase 2: Executing - we'll track via the agent's internal state
            yield f"data: {json.dumps({'type': 'status', 'phase': 'executing', 'message': 'Vykonávam nástroje...', 'progress': 30})}\n\n"

            # Run the actual analysis
            result = agent.analyze_sync(prompt, request_id=request_id)

            # Send tool execution updates
            tools_used = result.get('tools_used', [])
            for i, tool in enumerate(tools_used):
                progress = 30 + int((i + 1) / len(tools_used) * 40) if tools_used else 70
                yield f"data: {json.dumps({'type': 'tool', 'tool': tool, 'index': i + 1, 'total': len(tools_used), 'progress': progress})}\n\n"

            # Phase 3: Synthesizing
            yield f"data: {json.dumps({'type': 'status', 'phase': 'synthesizing', 'message': 'Opus syntetizuje výsledky...', 'progress': 80})}\n\n"

            if 'error' in result and result['error']:
                logger.error(f"SSE Agent error: {result['error']}", extra={"request_id": request_id})
                yield f"data: {json.dumps({'type': 'error', 'message': result['error']})}\n\n"
                return

            duration = time.time() - start_time
            logger.info(f"SSE Agent complete: tools={tools_used}", extra={"request_id": request_id})

            # Send final result
            yield f"data: {json.dumps({'type': 'result', 'response': result['response'], 'tools_used': tools_used, 'tool_call_count': result.get('tool_call_count', 0), 'duration_seconds': round(duration, 2), 'request_id': request_id, 'progress': 100})}\n\n"

            # Log to GCS
            log_agent_request_to_gcs({
                'request_id': request_id,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'prompt': prompt,
                'status': 'success',
                'response': result['response'],
                'tools_used': tools_used,
                'tool_call_count': result.get('tool_call_count', 0),
                'duration_seconds': round(duration, 2),
                'architecture': result.get('architecture'),
                'streaming': True
            })

        except Exception as e:
            logger.exception(f"SSE Agent exception: {type(e).__name__}: {e}", extra={"request_id": request_id})
            yield f"data: {json.dumps({'type': 'error', 'message': 'Spracovanie zlyhalo. Skúste to znova.'})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # Disable nginx buffering
        }
    )


@app.route('/api/agent/status', methods=['GET'])
def agent_status():
    """Check if Claude Agent is available."""
    agent = get_agent()
    return jsonify({
        'available': agent is not None,
        'model': 'claude-opus-4-5' if agent else None,
        'features': [
            'search_pharmacies',
            'get_pharmacy_details',
            'compare_to_peers',
            'get_understaffed',
            'get_regional_summary',
            'get_all_regions_summary',
            'generate_report',
            'get_segment_comparison',
            'get_city_summary',
            'get_network_overview',
            'get_trend_analysis',
            'get_priority_actions'
        ] if agent else []
    })


@app.route('/api/agent/diagnose', methods=['GET'])
@requires_api_auth
def agent_diagnose():
    """Diagnostic endpoint to test Anthropic API connectivity."""
    import socket
    import ssl
    import os as diag_os
    import urllib.request

    diagnostics = {
        'api_key_set': bool(diag_os.environ.get('ANTHROPIC_API_KEY')),
        'api_key_length': len(diag_os.environ.get('ANTHROPIC_API_KEY', '')),
        'api_key_prefix': diag_os.environ.get('ANTHROPIC_API_KEY', '')[:10] + '...' if diag_os.environ.get('ANTHROPIC_API_KEY') else None,
        'dns_resolution': None,
        'socket_test': None,
        'https_test': None,
        'api_test': None
    }

    # Test DNS resolution
    try:
        result = socket.gethostbyname('api.anthropic.com')
        diagnostics['dns_resolution'] = {'success': True, 'ip': result}
    except socket.gaierror as e:
        diagnostics['dns_resolution'] = {'success': False, 'error': str(e)}

    # Test raw socket connection
    try:
        sock = socket.create_connection(('api.anthropic.com', 443), timeout=10)
        sock.close()
        diagnostics['socket_test'] = {'success': True}
    except Exception as e:
        diagnostics['socket_test'] = {'success': False, 'error': str(e)}

    # Test HTTPS with urllib
    try:
        req = urllib.request.Request('https://api.anthropic.com', method='HEAD')
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            diagnostics['https_test'] = {'success': True, 'status': resp.status}
    except Exception as e:
        diagnostics['https_test'] = {'success': False, 'error_type': type(e).__name__, 'error': str(e)[:200]}

    # Test API connectivity with minimal call using requests
    try:
        import requests
        api_key = diag_os.environ.get('ANTHROPIC_API_KEY', '')
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json'
            },
            json={
                'model': 'claude-3-haiku-20240307',
                'max_tokens': 10,
                'messages': [{'role': 'user', 'content': 'Say OK'}]
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            diagnostics['api_test'] = {
                'success': True,
                'model': data.get('model'),
                'response': data.get('content', [{}])[0].get('text')
            }
        else:
            diagnostics['api_test'] = {
                'success': False,
                'status_code': resp.status_code,
                'error': resp.text[:200]
            }
    except Exception as e:
        diagnostics['api_test'] = {
            'success': False,
            'error_type': type(e).__name__,
            'error': str(e)[:200]
        }

    return jsonify(diagnostics)


@app.route('/api/agent/data-check', methods=['GET'])
@requires_api_auth
def agent_data_check():
    """Check agent's sanitized data."""
    agent = get_agent()
    if agent is None:
        return jsonify({'error': 'Agent not available'}), 503

    try:
        df = agent.sanitized_data
        pharmacy_33 = df[df['id'] == 33]
        sample_ids = df['id'].head(10).tolist()
        id_dtype = str(df['id'].dtype)

        return jsonify({
            'total_pharmacies': len(df),
            'columns': list(df.columns),
            'sample_ids': sample_ids,
            'id_dtype': id_dtype,
            'pharmacy_33_found': not pharmacy_33.empty,
            'pharmacy_33_data': pharmacy_33.iloc[0].to_dict() if not pharmacy_33.empty else None
        })
    except Exception as e:
        return jsonify({'error': str(e), 'error_type': type(e).__name__}), 500


if __name__ == '__main__':
    print("\n" + "=" * 50)
    print(f"FTE Calculator v5.1 (Refactored) - http://localhost:{PORT}")
    print("=" * 50 + "\n")
    app.run(host=HOST, port=PORT, debug=DEBUG)
