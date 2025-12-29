# Revenue at Risk Calculation

This document describes the FTE gap thresholds and revenue at risk calculation used in the DrMax FTE Calculator.

## FTE Gap Thresholds

Two threshold constants control pharmacy classification:

| Constant | Value | Description |
|----------|-------|-------------|
| `FTE_GAP_NOTABLE` | 0.05 | Minimum gap to classify as understaffed/overstaffed (~1.5 hrs/week) |
| `FTE_GAP_URGENT` | 0.05 | Gap threshold for urgent priority (requires above-avg productivity) |

These are defined in `app_v2/core.py`:

```python
FTE_GAP_NOTABLE = 0.05  # ~1.5 hours per week
FTE_GAP_URGENT = 0.05   # Same as notable for aggressive value demonstration
```

### Threshold Rationale

| Threshold | Pharmacies | Revenue at Risk | Use Case |
|-----------|------------|-----------------|----------|
| 0.5 FTE | 8 | 961K EUR | Conservative (20 hrs/week gap) |
| 0.25 FTE | 42 | 2.78M EUR | Moderate (10 hrs/week gap) |
| 0.1 FTE | 73 | 3.52M EUR | Sensitive (4 hrs/week gap) |
| **0.05 FTE** | **94** | **3.74M EUR** | Aggressive (1.5 hrs/week gap) |

The aggressive 0.05 threshold maximizes demonstrated app value by capturing all pharmacies with measurable understaffing.

---

## FTE Calculation

### GROSS vs NET FTE

The system uses two FTE metrics:

- **NET FTE** (`fte`): Staff actually working (excluding absences)
- **GROSS FTE**: Total staff capacity including absence coverage

**Single Source of Truth Formula:**
```
GROSS FTE = NET FTE + fte_n
```

Where `fte_n` is the absence/zastup FTE component.

### FTE Gap Calculation

```python
fte_gap = predicted_gross - actual_gross
```

- **Positive gap**: Understaffed (need more FTE)
- **Negative gap**: Overstaffed (excess FTE)

---

## Revenue at Risk Calculation

Revenue at risk quantifies potential lost revenue due to understaffing at high-performing pharmacies.

### Formula

```python
def calculate_revenue_at_risk(predicted_fte, actual_fte, annual_revenue, is_above_avg_productivity):
    # Only applies to understaffed, above-average productivity pharmacies
    if not is_above_avg_productivity:
        return 0
    if predicted_fte <= actual_fte:  # Not understaffed
        return 0
    if annual_revenue <= 0 or actual_fte <= 0:
        return 0

    # Calculate overload ratio
    overload_ratio = predicted_fte / actual_fte

    # Revenue at risk = (overload - 1) × 50% × annual_revenue
    revenue_at_risk = (overload_ratio - 1) * 0.5 * annual_revenue

    return int(revenue_at_risk)
```

### Formula Breakdown

1. **Overload Ratio**: `predicted_fte / actual_fte`
   - Example: 4.5 predicted / 4.0 actual = 1.125 (12.5% overload)

2. **Excess Workload**: `overload_ratio - 1`
   - Example: 1.125 - 1 = 0.125 (12.5% excess)

3. **Revenue Impact Factor**: `0.5` (50%)
   - Conservative estimate that 50% of excess workload translates to lost revenue
   - Accounts for: reduced customer service, longer wait times, missed upselling

4. **Revenue at Risk**: `excess × 0.5 × annual_revenue`
   - Example: 0.125 × 0.5 × 2,000,000 = 125,000 EUR

### Eligibility Criteria

Revenue at risk is only calculated when ALL conditions are met:

| Condition | Rationale |
|-----------|-----------|
| `is_above_avg_productivity = True` | Only high performers have capacity to generate more revenue |
| `predicted_fte > actual_fte` | Must be understaffed |
| `actual_fte > 0` | Valid staffing data |
| `annual_revenue > 0` | Valid revenue data |

### Productivity Classification

Pharmacies are classified as "above average" based on GROSS productivity compared to segment mean:

```python
SEGMENT_PRODUCTIVITY_MEANS = {
    'A - shopping premium': 6.27,
    'B - shopping': 7.96,
    'C - street +': 5.68,
    'D - street': 5.55,
    'E - poliklinika': 5.23
}

is_above_avg = pharmacy_productivity_gross > segment_mean
```

---

## Priority Classification

Pharmacies are classified into priority buckets:

| Priority | Criteria | Action |
|----------|----------|--------|
| **Urgent** | `fte_gap >= 0.05` AND `is_above_avg_productivity` | Immediate staffing increase needed |
| **Optimize** | `fte_gap >= 0.05` AND NOT `is_above_avg_productivity` | Review efficiency before adding staff |
| **Monitor** | `fte_gap < -0.05` (overstaffed) | Potential reallocation opportunity |
| **Optimal** | `-0.05 < fte_gap < 0.05` | No action needed |

---

## Example Calculation

**Pharmacy ID 185 (Trebišov)**:
- Actual GROSS FTE: 3.5
- Predicted GROSS FTE: 4.2
- Annual Revenue: 1,200,000 EUR
- Productivity: 7.1 (Segment D average: 5.55) → Above average

```
fte_gap = 4.2 - 3.5 = 0.7 (understaffed)
overload_ratio = 4.2 / 3.5 = 1.20
excess = 1.20 - 1 = 0.20 (20% overload)
revenue_at_risk = 0.20 × 0.5 × 1,200,000 = 120,000 EUR
```

---

## Data Flow

```
┌─────────────────────┐
│  ML Model (v5)      │
│  Predicts NET FTE   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  GROSS Conversion   │
│  + fte_n (absence)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  FTE Gap Calc       │
│  predicted - actual │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Priority Class     │
│  + Revenue at Risk  │
└─────────────────────┘
```

---

## Configuration

Settings are centralized in `app_v2/core.py`:

```python
# FTE gap thresholds
FTE_GAP_NOTABLE = 0.05  # For understaffed/overstaffed classification
FTE_GAP_URGENT = 0.05   # For urgent priority (with productivity check)

# Segment productivity means (GROSS-based)
SEGMENT_PROD_MEANS_GROSS = {
    'A - shopping premium': 6.27,
    'B - shopping': 7.96,
    'C - street +': 5.68,
    'D - street': 5.55,
    'E - poliklinika': 5.23
}
```

To adjust thresholds, modify these constants and restart the server.
