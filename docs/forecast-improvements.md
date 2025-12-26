# Revenue Forecast - Implementation & Improvements

## Current Implementation (v2 - Optimized)

**Method:** 55% Relative Seasonal Adjustment
- Base: Recent 3-month average
- Adjustment: Relative seasonal factor (target vs base period strength)
- Works for ANY current month → next 3 months forecast

**Formula:**
```
base_seasonal = avg(seasonal_factor[base_month] for base_month in last_3_months)
relative_factor = seasonal_factor[target_month] / base_seasonal
forecast = recent_avg × (0.45 + 0.55 × relative_factor)
```

**Seasonal Factors (2019 baseline, normalized to annual avg = 1.0):**
| Month | Factor | Pattern |
|-------|--------|---------|
| Jan | 1.003 | — Normal |
| Feb | 0.981 | — Normal |
| Mar | 0.990 | — Normal |
| Apr | 0.959 | ↓ Soft |
| May | 0.992 | — Normal |
| Jun | 0.962 | ↓ Soft |
| Jul | 0.954 | ↓ Soft |
| Aug | 0.887 | ↓ WEAK |
| Sep | 1.028 | ↑ Strong |
| Oct | 1.082 | ↑ Strong |
| Nov | 1.026 | ↑ Strong |
| Dec | 1.135 | 🔥 Peak |

**Accuracy (backtested on 280 pharmacies, 840 predictions):**
- MAPE: 11.1%
- <10% error: 58.6%
- <15% error: 75.7%

**Why 55% seasonal weight?**
- Tested weights from 0% to 100% in 5% increments
- 55% minimizes overall MAPE
- Balances recent momentum with seasonal patterns

## Previous Implementation (v1 - Deprecated)

**Method:** YoY Growth Adjustment
- Formula: `forecast[month] = revenue_2020[month] × (1 + yoy_growth_2021)`
- MAPE: ~22% (poor due to COVID distortion in 2020)

---

## Potential Improvements

### 1. Alternative Base Year
Use 2019 (pre-COVID) as base instead of 2020, or weighted average:
```
forecast = 0.3 × (2019_value × growth_factor²) + 0.7 × (2020_value × growth_factor)
```

### 2. Confidence Intervals
Add upper/lower bounds to show uncertainty:
- Simple: ±10-15% of forecast value
- Better: Based on historical variance for each pharmacy

Visual: Light shaded band around forecast line

### 3. Holt-Winters Exponential Smoothing
Triple exponential smoothing that handles:
- Level (baseline)
- Trend (growth/decline)
- Seasonality (monthly patterns)

Python implementation:
```python
from statsmodels.tsa.holtwinters import ExponentialSmoothing

model = ExponentialSmoothing(
    revenue_series,
    seasonal_periods=12,
    trend='add',
    seasonal='add'
)
fitted = model.fit()
forecast = fitted.forecast(3)
```

### 4. Pharmacy Clustering
Group pharmacies by behavior patterns:
- High seasonality vs stable
- Growing vs declining vs volatile
- Urban vs rural patterns

Apply different forecast models per cluster.

### 5. External Factors
Incorporate additional signals:
- Day count per month
- Holiday calendar
- Local events/competition changes
- Weather patterns (if available)

### 6. Ensemble Approach
Combine multiple methods:
```
final_forecast = 0.4 × seasonal_naive + 0.3 × holt_winters + 0.3 × linear_trend
```

### 7. Forecast Quality Metrics
Track and display forecast accuracy:
- MAPE (Mean Absolute Percentage Error)
- Show historical forecast vs actual for validation
- Color-code pharmacies by forecast reliability

---

## Implementation Priority

| Improvement | Effort | Impact | Priority |
|-------------|--------|--------|----------|
| Confidence intervals | Low | Medium | High |
| 2019 base option | Low | Medium | High |
| Holt-Winters | Medium | High | Medium |
| Pharmacy clustering | High | Medium | Low |
| External factors | High | Medium | Low |
| Ensemble | Medium | High | Medium |

---

## Notes

- Current implementation is sufficient for directional staffing guidance
- Any improvements should maintain explainability for end users
- Consider A/B testing new methods against current approach before full rollout
