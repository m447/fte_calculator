"""
app_v2/config.py - Configuration Management

Centralizes all configuration, paths, and environment variables.
Security: No default values for secrets - application will fail to start
if required environment variables are not set.
"""

import os
import sys
import logging
import json
from pathlib import Path
from datetime import datetime


# ============================================================
# LOGGING CONFIGURATION
# ============================================================

class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in cloud environments."""

    def format(self, record):
        log_obj = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, 'request_id'):
            log_obj['request_id'] = record.request_id
        if hasattr(record, 'pharmacy_id'):
            log_obj['pharmacy_id'] = record.pharmacy_id
        if hasattr(record, 'duration_ms'):
            log_obj['duration_ms'] = record.duration_ms

        # Add exception info if present
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def setup_logging(name: str = 'app_v2') -> logging.Logger:
    """
    Set up logging with environment-based configuration.

    LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: INFO)
    LOG_FORMAT: json, text (default: text for local, json in Cloud Run)
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers on re-import
    if logger.handlers:
        return logger

    # Determine log level from environment
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Determine format (JSON in Cloud Run, text locally)
    is_cloud_run = os.environ.get('K_SERVICE') is not None
    log_format = os.environ.get('LOG_FORMAT', 'json' if is_cloud_run else 'text')

    handler = logging.StreamHandler(sys.stderr)

    if log_format == 'json':
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))

    logger.addHandler(handler)
    return logger


# Create root logger for app_v2
logger = setup_logging('app_v2')

# ============================================================
# PATHS
# ============================================================

# Project root is parent of app_v2/
PROJECT_ROOT = Path(__file__).parent.parent

# Data paths
DATA_DIR = PROJECT_ROOT / 'data'
DATA_PATH = DATA_DIR / 'ml_ready_v3.csv'
GROSS_FACTORS_PATH = DATA_DIR / 'gross_factors.json'
REVENUE_MONTHLY_PATH = DATA_DIR / 'revenue_monthly.csv'
REVENUE_ANNUAL_PATH = DATA_DIR / 'revenue_annual.csv'

# Model path
MODELS_DIR = PROJECT_ROOT / 'models'
MODEL_PATH = MODELS_DIR / 'fte_model_v5.pkl'

# Static files
STATIC_DIR = PROJECT_ROOT / 'app' / 'static'  # Reuse existing static folder

# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

def get_required_env(key: str) -> str:
    """
    Get required environment variable.

    Raises ValueError if not set - this ensures the app fails fast
    at startup rather than silently using insecure defaults.
    """
    value = os.environ.get(key)
    if not value:
        raise ValueError(
            f"Required environment variable '{key}' is not set. "
            f"Please set it in your environment or .env file."
        )
    return value


def get_optional_env(key: str, default: str = '') -> str:
    """Get optional environment variable with default."""
    return os.environ.get(key, default)


# ============================================================
# SECURITY CONFIGURATION
# ============================================================

# In production, these MUST be set via environment variables
# The app will fail to start if they are not set
try:
    APP_PASSWORD = get_required_env('APP_PASSWORD')
    API_KEY = get_required_env('API_KEY')
except ValueError as e:
    # For development, allow fallback but log warning
    logger.warning(str(e))
    logger.warning("Using development defaults - DO NOT USE IN PRODUCTION")
    APP_PASSWORD = os.environ.get('APP_PASSWORD', 'dev-password-change-me')
    API_KEY = os.environ.get('API_KEY', 'dev-api-key-change-me')

# Anthropic API key for AI agent
ANTHROPIC_API_KEY = get_optional_env('ANTHROPIC_API_KEY')

# ============================================================
# APPLICATION SETTINGS
# ============================================================

# Debug mode
DEBUG = get_optional_env('DEBUG', 'false').lower() == 'true'

# Server settings
HOST = get_optional_env('HOST', '0.0.0.0')
PORT = int(get_optional_env('PORT', '5001'))

# ============================================================
# AI AGENT CONFIGURATION
# ============================================================

# Claude Agent model configuration (easily upgradeable via env vars)
AGENT_ARCHITECT_MODEL = get_optional_env('AGENT_ARCHITECT_MODEL', 'claude-sonnet-4-5-20250929')
AGENT_WORKER_MODEL = get_optional_env('AGENT_WORKER_MODEL', 'claude-haiku-4-5-20251001')
AGENT_ARCHITECT_MAX_TOKENS = int(get_optional_env('AGENT_ARCHITECT_MAX_TOKENS', '4096'))
AGENT_WORKER_MAX_TOKENS = int(get_optional_env('AGENT_WORKER_MAX_TOKENS', '2048'))
AGENT_MAX_TOOL_CALLS = int(get_optional_env('AGENT_MAX_TOOL_CALLS', '10'))
AGENT_MAX_PLAN_STEPS = int(get_optional_env('AGENT_MAX_PLAN_STEPS', '5'))

# Tool execution timeouts (in seconds)
TOOL_TIMEOUTS: dict = {
    'get_pharmacy_details': 5,
    'get_pharmacy_revenue_trend': 5,
    'search_pharmacies': 10,
    'get_segment_position': 5,
    'simulate_fte': 15,
    'compare_to_peers': 10,
    'get_understaffed': 10,
    'get_regional_summary': 5,
    'get_all_regions_summary': 10,
    'generate_report': 30,
    'get_segment_comparison': 5,
    'get_city_summary': 5,
    'get_cities_pharmacy_count': 5,
    'get_network_overview': 10,
    'get_trend_analysis': 10,
    'get_priority_actions': 10,
    'get_zastup_analysis': 10,
    'get_overstaffed_with_zastup': 10,
}
TOOL_TIMEOUT_DEFAULT: int = 15

# Context summarization limits (to avoid overflowing Claude's context)
CONTEXT_LIMITS: dict = {
    'pharmacies': 15,      # Max pharmacies in list results
    'peers': 5,            # Max peer comparisons
    'cities': 20,          # Max cities in list
    'actions': 10,         # Max priority actions
    'monthly_data': 12,    # Max months of data per year
}

# ============================================================
# VALIDATION
# ============================================================

def validate_paths():
    """Validate that all required paths exist."""
    required_paths = [
        (DATA_PATH, "Training data"),
        (GROSS_FACTORS_PATH, "Gross factors"),
        (MODEL_PATH, "ML model"),
    ]

    missing = []
    for path, name in required_paths:
        if not path.exists():
            missing.append(f"  - {name}: {path}")

    if missing:
        raise FileNotFoundError(
            f"Required files not found:\n" + "\n".join(missing)
        )


# Validate paths on import (fail fast)
if not DEBUG:
    try:
        validate_paths()
    except FileNotFoundError as e:
        logger.warning(str(e))
