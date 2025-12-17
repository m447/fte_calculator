# Data Dictionary: ml_ready_v3.csv

## Overview

| Property | Value |
|----------|-------|
| **File** | `ml_ready_v3.csv` |
| **Rows** | 286 pharmacies |
| **Columns** | 32 |
| **Primary Key** | `id` (pharmacy identifier) |

---

## Identifiers

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| `id` | int | Unique pharmacy identifier (range: 2-664) | all.csv |
| `mesto` | string | City/location name | all.csv |
| `regional` | string | Regional manager name (format: RR##_Name) | typ.csv |
| `region_code` | string | Regional code extracted from `regional` (e.g., RR15) | Derived from `regional` |
| `typ` | string | Store type classification | typ.csv |

### Store Types (`typ`)

| Code | Description |
|------|-------------|
| A - shopping premium | Premium shopping center locations |
| B - shopping | Standard shopping centers (Kaufland, TESCO) |
| C - street + | High-traffic street locations |
| D - street | Standard street locations |
| E - poliklinika | Clinic-attached pharmacies |

---

## Target Variables (to predict)

| Column | Type | Unit | Description | Calculation | Source |
|--------|------|------|-------------|-------------|--------|
| `fte` | float | FTE | Total Full-Time Equivalent staff required | Sum of all staff hours / 173.33 | all.csv |
| `fte_F` | float | FTE | Pharmacist (Farmaceut) FTE | Hours worked by F role / 173.33 | fte.csv |
| `fte_L` | float | FTE | Sales Assistant (Laborant) FTE | Hours worked by L role / 173.33 | fte.csv |
| `fte_ZF` | float | FTE | Additional Pharmacist (Zástupca) FTE | Hours worked by ZF role / 173.33 | fte.csv |

### FTE Explanation
- **FTE** = Full-Time Equivalent
- **1.0 FTE** = 173.33 hours/month (standard full-time)
- **Formula**: `FTE = monthly_hours_worked / 173.33`

---

## Features - Volume Metrics

| Column | Type | Unit | Description | Calculation | Source |
|--------|------|------|-------------|-------------|--------|
| `trzby` | float | EUR | Annual revenue | Sum of 12 months revenue | all.csv, data.csv |
| `bloky` | int | count | Annual transaction count | Sum of 12 months transactions | all.csv, data.csv |
| `naklady` | float | EUR | Annual wage costs (PnL 90101) | Sum of 12 months wages | all.csv, data_rec.xlsx |
| `bloky_per_day` | float | count | Average daily transactions | `bloky / 300` (working days) | Derived |
| `bloky_range` | float | count | Seasonal transaction range | `max(monthly_bloky) - min(monthly_bloky)` | Derived from data.csv |

⚠️ **Warning**: `naklady` = WAGES ONLY (not total operating costs). Has 0.974 correlation with `fte` because wages directly depend on staffing. **MUST EXCLUDE from ML features** - this is data leakage.

📝 **Note**: Rental costs are NOT available in the dataset. Store size/location is proxied by `typ`, `bloky`, and `mesto`.

---

## Features - Ratios & Efficiency

| Column | Type | Unit | Description | Calculation | Source |
|--------|------|------|-------------|-------------|--------|
| `podiel_rx` | float | ratio (0-1) | Prescription ratio | Prescriptions / Total transactions | all.csv |
| `revenue_per_transaction` | float | EUR | Average transaction value | `trzby / bloky` | Derived from all.csv |
| `produktivita` | float | ratio | Revenue efficiency per FTE | Revenue / FTE (normalized) | efektivita_3.xlsx |
| `pharmacist_ratio` | float | ratio (0-1) | Pharmacist staffing proportion | `fte_F / (fte_F + fte_L)` | Derived |

---

## Features - Variability & Seasonality

| Column | Type | Unit | Description | Calculation | Source |
|--------|------|------|-------------|-------------|--------|
| `trzby_cv` | float | ratio | Revenue coefficient of variation | `std(monthly_trzby) / mean(monthly_trzby)` | Derived from data.csv |
| `bloky_cv` | float | ratio | Transaction coefficient of variation | `std(monthly_bloky) / mean(monthly_bloky)` | Derived from data.csv |
| `bloky_trend` | float | ratio | Year-over-year transaction growth | `(last_month - first_month) / first_month` | Derived from bloky.xlsx |
| `seasonal_peak_factor` | float | ratio | Peak month intensity | `max(monthly_bloky) / mean(monthly_bloky)` | Derived from data.csv |

---

## Features - Performance Metrics

| Column | Type | Unit | Description | Calculation | Source |
|--------|------|------|-------------|-------------|--------|
| `kpi_mean` | float | score | Average KPI score | `mean(monthly_kpi)` | Derived from data.csv |
| `kpi_std` | float | score | KPI variability | `std(monthly_kpi)` | Derived from data.csv |
| `fte_zastup` | float | FTE | Substitute/backup FTE needed | Coverage for absences | efektivita_3.xlsx |

---

## Features - Wage & Labor

| Column | Type | Unit | Description | Calculation | Source |
|--------|------|------|-------------|-------------|--------|
| `avg_base_salary` | float | EUR | Average base monthly salary | `mean(mzda)` per pharmacy | mzdy.csv |
| `hourly_rate` | float | EUR/hr | Average hourly payment rate | `mean(vyplata) / mean(hodiny)` | Derived from mzdy.csv |
| `pharmacist_wage_premium` | float | ratio | Pharmacist vs Sales wage ratio | `avg_wage_F / avg_wage_L` | Derived from mzdy.csv |

---

## Features - Binary Flags

| Column | Type | Values | Description | Calculation | Source |
|--------|------|--------|-------------|-------------|--------|
| `high_rx_complexity` | int | 0, 1 | High prescription ratio flag | `1 if podiel_rx > 0.70 else 0` | Derived from all.csv |
| `is_shopping` | int | 0, 1 | Shopping center location | `1 if typ in ['A - shopping premium', 'B - shopping']` | Derived from typ.csv |
| `is_poliklinika` | int | 0, 1 | Clinic-attached pharmacy | `1 if typ == 'E - poliklinika'` | Derived from typ.csv |
| `is_street` | int | 0, 1 | Street location | `1 if typ in ['C - street +', 'D - street']` | Derived from typ.csv |

---

## Source Files

| File | Location | Description | Rows |
|------|----------|-------------|------|
| `all.csv` | data/raw/ | Aggregated annual metrics per pharmacy | 286 |
| `data.csv` | data/raw/ | Monthly time series (Sep 2020 - Aug 2021) | 3,432 |
| `fte.csv` | data/raw/ | FTE breakdown by function type | 937 |
| `typ.csv` | data/raw/ | Store classification | 286 |
| `bloky.xlsx` | data/raw/ | Monthly transaction counts | 330 |
| `efektivita_3.xlsx` | data/raw/ | Efficiency and performance metrics | 286 |
| `mzdy.csv` | data/payroll/ | Payroll records (Aug 2020 - Aug 2021) | 17,727 |

---

## Data Quality Notes

### Missing Values
| Column | Missing | Handling |
|--------|---------|----------|
| `fte_F` | 0 | Filled with 0 (no pharmacist) |
| `fte_L` | 0 | Filled with 0 (no sales staff) |
| `fte_ZF` | 0 | Filled with median |
| `fte_zastup` | 7 | Left as NaN |
| `pharmacist_ratio` | 48 | Left as NaN (division by zero) |
| `pharmacist_wage_premium` | 30 | Left as NaN |

### Correlations to Note
| Feature Pair | Correlation | Note |
|--------------|-------------|------|
| `naklady` ↔ `fte` | 0.974 | **Data leakage** - exclude from features |
| `bloky` ↔ `bloky_per_day` | 1.000 | Same information - use one |
| `revenue_per_transaction` ↔ `hodnota_bloku` | 1.000 | Duplicate removed |

---

## Recommended Feature Set for ML

### Include (strong predictors)
- `bloky` - transaction volume (0.895)
- `trzby` - revenue (0.841)
- `typ` - store type (categorical)
- `bloky_range` - seasonality (0.662)
- `podiel_rx` - complexity (-0.418)
- `produktivita` - efficiency (0.401)

### Exclude
- `naklady` - data leakage (costs depend on FTE)
- `bloky_per_day` - redundant with `bloky`
- `fte_*` targets when predicting `fte`

---

*Generated: December 2024*
*Dataset version: v3*
