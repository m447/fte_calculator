# Changelog

All notable changes to the FTE Calculator application will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - Changes not yet deployed to Google Cloud

### Bug Fixes

- **Fixed ID 107 appearing on both "Potential FTE Surplus" AND "Growth Alert" lists**
  - Root cause: `prod_residual` was not clipped to 0 in `/api/pharmacy` endpoint
  - Fix: Added clipping in `calculate_pharmacy_fte()` shared function

- **Fixed inconsistent FTE values between list view and detail view**
  - Root cause: Different GROSS calculation paths in different endpoints
  - Fix: Unified via `get_gross_factors()` shared function

- **Fixed wrong prod_pct calculation in /api/network**
  - Root cause: Used `prod_residual * 100` instead of `prod_residual / segment_mean * 100`
  - Fix: Created `calculate_prod_pct()` shared function

### Added

- **Created app_v2/ folder with refactored code structure**
  - `app_v2/core.py` - Single source of truth for all business logic
  - `app_v2/config.py` - Centralized configuration management
  - `app_v2/server.py` - Refactored server importing from core
  - `app_v2/data_sanitizer.py` - Refactored sanitizer importing from core

- **Added shared helper functions to eliminate code duplication**
  - `get_gross_factors()` - GROSS conversion factors
  - `calculate_pharmacy_fte()` - FTE calculation
  - `is_above_avg_productivity()` - Productivity check
  - `calculate_prod_pct()` - Productivity percentage
  - `calculate_revenue_at_risk()` - Revenue at risk formula
  - `prepare_fte_dataframe()` - Batch FTE calculations

- **Added centralized constants**
  - `FTE_GAP_NOTABLE = 0.5`
  - `FTE_GAP_URGENT = 0.5`
  - `FTE_GAP_OPTIMIZE = 0.7`
  - `FTE_GAP_OUTLIER = 1.0`

### Changed

- **Code Quality Improvements**
  - Eliminated code duplication across multiple endpoints
  - Unified business logic into single source of truth
  - Improved maintainability through centralized configuration

### Security

- **Removed hardcoded default passwords from config** (`app_v2/config.py`)
  - Application now requires environment variables for sensitive values
  - Improved security posture by eliminating credentials in source code
