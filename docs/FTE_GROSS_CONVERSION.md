# FTE GROSS Conversion - Single Source of Truth

This document describes the standardized method for converting NET FTE to GROSS FTE, ensuring consistency between the CSV data and API calculations.

## Overview

The FTE model predicts **NET FTE** (working staff needed). To get **GROSS FTE** (total headcount including absences), we add the absence FTE (`fte_n`).

## Formula

```
GROSS = NET + fte_n
```

This formula applies to **both** actual and predicted FTE:

| Metric | Formula | Description |
|--------|---------|-------------|
| `actual_fte_gross` | `fte + fte_n` | Current GROSS staffing |
| `predicted_fte` | `predicted_net + fte_n` | Recommended GROSS staffing |
| `fte_gap` | `predicted_fte - actual_fte_gross` | Staffing gap (positive = understaffed) |

## Key Insight

Since both actual and predicted use the same `fte_n` value:

```
fte_gap = (predicted_net + fte_n) - (fte + fte_n)
        = predicted_net - fte
```

The `fte_n` cancels out - we're effectively comparing NET staffing needs.

## Variables

| Variable | Description | Source |
|----------|-------------|--------|
| `fte` | NET working staff (present, actively working) | CSV column |
| `fte_n` | Absence FTE (sick leave, vacation, etc.) | CSV column (from `all.csv`) |
| `fte_F`, `fte_L`, `fte_ZF` | NET FTE by role (Pharmacist, Lab, Support) | CSV columns |
| `predicted_net` | Model-predicted NET FTE | ML model output |

## Implementation Locations

### 1. API Endpoint (`app_v2/core.py`)

**Single pharmacy calculation** - `calculate_pharmacy_fte()`:
```python
# Predict NET FTE
predicted_fte_net = get_model()['models']['fte'].predict(X)[0]
predicted_fte_net = max(0.5, predicted_fte_net)  # Minimum 0.5 FTE

# GROSS = NET + fte_n (single source of truth)
fte_n = float(row.get('fte_n', 0))
predicted_fte = predicted_fte_net + fte_n
actual_fte = float(row.get('fte', 0)) + fte_n
```

**Batch calculation** - `prepare_fte_dataframe()`:
```python
# Predict NET and apply floor
df_calc['predicted_fte_net'] = get_model()['models']['fte'].predict(X)
df_calc['predicted_fte_net'] = df_calc['predicted_fte_net'].clip(lower=0.5)

# GROSS = NET + fte_n
df_calc['predicted_fte'] = df_calc['predicted_fte_net'] + df_calc['fte_n']
df_calc['actual_fte'] = df_calc['fte'] + df_calc['fte_n']
```

### 2. CSV Generation (`scripts/add_predictions_to_csv.py`)

```python
# GROSS = NET + fte_n (single source of truth)
predicted_gross = predicted_net + fte_n
actual_gross = row['fte'] + fte_n
```

## Critical Model Behavior

### prod_residual Clipping (v5 Asymmetric Model)

The v5 model uses asymmetric treatment of productivity:
- **Positive** `prod_residual`: High productivity → model may recommend more FTE
- **Negative** `prod_residual`: Low productivity → **CLIPPED TO 0** (not used to reduce FTE)

```python
features['prod_residual'] = max(0, features.get('prod_residual', 0))
```

**Rationale**: We don't reduce FTE recommendations just because a pharmacy is currently underperforming. The recommendation is based on workload, not current productivity.

### Minimum FTE Floor

All predictions have a minimum floor of 0.5 FTE:
```python
predicted_fte_net = max(0.5, predicted_fte_net)
```

## Historical Context

### Previous Methods (Deprecated)

Before this standardization, two different methods were used:

**Method A (Current)**: Simple addition
```python
gross = net + fte_n
```

**Method B (Deprecated)**: Conversion factors
```python
gross = (fte_F * factor_F) + (fte_L * factor_L) + (fte_ZF * factor_ZF)
```

Method B used pharmacy-specific or segment-based conversion factors from `gross_factors.json`. This was deprecated because:
1. It created inconsistency between actual and predicted calculations
2. The factors were derived differently than the actual `fte_n` values
3. Role breakdowns (`fte_F`, `fte_L`, `fte_ZF`) don't sum to `fte` due to rounding

### Why fte_n?

The `fte_n` column represents actual absence data from payroll/HR systems:
- Sick leave
- Vacation
- Parental leave
- Other authorized absences

Using actual `fte_n` values ensures:
1. Consistency with how actual GROSS is measured
2. Pharmacy-specific absence patterns are captured
3. Same conversion method for actual and predicted

## CSV Columns

| Column | Type | Description |
|--------|------|-------------|
| `fte` | NET | Working staff (present) |
| `fte_n` | - | Absence FTE |
| `fte_F`, `fte_L`, `fte_ZF` | NET | Role breakdown |
| `actual_fte_gross` | GROSS | `fte + fte_n` |
| `predicted_fte_net` | NET | Model prediction |
| `predicted_fte` | GROSS | `predicted_net + fte_n` |
| `fte_gap` | - | `predicted - actual` |
| `fte_diff` | - | `actual - predicted` (legacy, opposite sign) |

## Verification

To verify consistency between CSV and API:

```python
# API calculation
predicted_net = model.predict(features)
predicted_net = max(0.5, predicted_net)
predicted_gross = predicted_net + fte_n
actual_gross = fte + fte_n

# Should match CSV values
assert abs(predicted_gross - csv['predicted_fte']) < 0.15
assert abs(actual_gross - csv['actual_fte_gross']) < 0.15
```

## Change Log

| Date | Change |
|------|--------|
| 2025-12-28 | Standardized GROSS conversion to `NET + fte_n` for both actual and predicted |
| 2025-12-28 | Added `prod_residual` clipping to CSV generation script |
| 2025-12-28 | Added 0.5 FTE minimum floor to all prediction paths |
| 2025-12-28 | Deprecated conversion factor method for predictions |
