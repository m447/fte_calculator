# Productivity Metrics: NET vs GROSS

## Overview

This document explains the two productivity metrics used in the FTE prediction system and why different metrics are used for model training vs. UI display.

## Productivity Formulas

### NET Productivity (Model Training)

```
produktivita = bloky / fte / 2088
```

Where:
- `bloky` = annual transaction count
- `fte` = NET FTE (actual hours worked, excludes absences)
- `2088` = standard annual hours (174 hours/month × 12 months)

**Derivation:** `prod_residual = produktivita - segment_mean`

### GROSS Productivity (UI Display)

```
produktivita_gross = bloky / actual_fte_gross / 2088
```

Where:
- `bloky` = annual transaction count
- `actual_fte_gross` = GROSS FTE (includes contracted absences: `fte + fte_n`)
- `2088` = standard annual hours

## Why Two Metrics?

### The Paradox

Some pharmacies appeared both **highly productive** AND **overstaffed**, which seemed contradictory:

| Pharmacy | produktivita (NET) | Segment Mean | Status | FTE Diff (GROSS) |
|----------|-------------------|--------------|--------|------------------|
| ID 67    | 7.12              | 6.44         | Above avg | +0.5 (overstaffed) |

**Root cause:** Productivity was calculated using NET FTE while staffing used GROSS FTE.

### Resolution

- **Model uses NET productivity** (`prod_residual`) - measures actual efficiency during work hours
- **UI uses GROSS productivity** (`is_above_avg_gross`) - consistent with staffing metrics

## Segment Productivity Means

| Segment | Mean (NET) | Description |
|---------|------------|-------------|
| A - shopping premium | 7.25 | High-traffic shopping centers |
| B - shopping | 9.14 | Regular shopping centers |
| C - street + | 6.85 | Premium street locations |
| D - street | 6.44 | Regular street pharmacies |
| E - poliklinika | 6.11 | Hospital/clinic pharmacies |

## Classification Impact

Using GROSS-based classification affects the "above average productivity" flag:

| Metric | Above Average Count | % of Network |
|--------|---------------------|--------------|
| NET-based | 150 | 69% |
| GROSS-based | 134 | 62% |

**Difference:** 16 fewer pharmacies classified as "above average" when using GROSS.

## Correlation

The correlation between NET and GROSS productivity residuals is **0.95**, indicating:
- Both metrics identify similar productivity patterns
- Safe to use different metrics for model vs. display
- Minimal impact on overall rankings

## Data Columns

| Column | Type | Formula | Used For |
|--------|------|---------|----------|
| `produktivita` | Float | bloky / fte / 2088 | Model training (prod_residual) |
| `prod_residual` | Float | produktivita - segment_mean | Model feature |
| `produktivita_gross` | Float | bloky / actual_fte_gross / 2088 | UI display |
| `is_above_avg_gross` | Boolean | produktivita_gross > segment_mean | UI classification |

## Implementation

### Server (`core.py` and `server.py`)

```python
def is_above_avg_productivity(row):
    # Prefer GROSS-based classification (consistent with staffing metrics)
    if 'is_above_avg_gross' in row:
        return bool(row.get('is_above_avg_gross', False))
    # Fallback to NET-based (legacy)
    return float(row.get('prod_residual', 0)) > 0
```

### Revenue at Risk

Revenue at risk calculation uses the `is_above_avg_productivity()` function, which now returns GROSS-based classification. This means revenue at risk is only calculated for pharmacies that are:
1. Understaffed (predicted > actual GROSS FTE)
2. Above average productivity (GROSS-based)

## Summary

| Aspect | NET Productivity | GROSS Productivity |
|--------|------------------|-------------------|
| Formula base | Actual hours worked | Contracted positions |
| Used in | ML model (prod_residual) | UI display, classification |
| Measures | Efficiency during work | Staffing consistency |
| Column | `produktivita` | `produktivita_gross` |

**Recommendation:** Keep NET for model (captures true efficiency), use GROSS for display (consistent with staffing metrics shown to users).
