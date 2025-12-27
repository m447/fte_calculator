# FTE Data Sources and Known Discrepancies

## Overview

This document describes the data sources used for training the FTE prediction model and known discrepancies between different data sources.

## Data Source Flow

```
Payroll Data (monthly CSVs)
         │
         ├──► fte.csv (role breakdown: F, L, ZF)
         │
         └──► efektivita_3.xlsx ──► all.csv ──► ml_ready_v3.csv ──► Model
                   │
                   └── fte = zam - fte_n (NET FTE)
```

## Primary Data Sources

### 1. Efektivita (efektivita_3.xlsx → all.csv)

Source of the main `fte` column used in the model.

| Column | Description | Formula |
|--------|-------------|---------|
| `fte` | NET FTE (actual hours worked) | `zam - fte_n` |
| `fte_n` | Neprítomnosť (absence/leave) | From payroll |
| `zam` | Total contracted positions | - |

**GROSS FTE** = `fte + fte_n`

### 2. Role Breakdown (fte.csv)

Provides FTE breakdown by role:

| Column | Description |
|--------|-------------|
| `fte_F` | Farmaceut (Pharmacist) |
| `fte_L` | Laborant (Lab technician) |
| `fte_ZF` | Zodpovedný farmaceut (Responsible pharmacist) |

**Note:** Sanitár and Dohoda roles are excluded from FTE calculations.

### 3. Payroll Data (/data/payroll/)

Raw monthly payroll files used to derive gross conversion factors.

| Column | Description |
|--------|-------------|
| `hodiny` | Actual hours worked |
| `fond` | Contracted hours (full allocation) |
| `uvazok` | Contract position (0.0 - 1.0) |

**Gross Factor** = `fond / hodiny` (typically 1.17 - 1.29)

**NET FTE** = `hodiny / 12 / 176` (176 = avg monthly hours)

## Known Discrepancies

### 1. FTE vs Role Breakdown Mismatch

The `fte` column from efektivita does not exactly match `fte_F + fte_L + fte_ZF` from fte.csv.

**Analysis Results (Non-E pharmacies):**

| Threshold | Count | Percentage |
|-----------|-------|------------|
| Within 0.3 FTE | 153 | 71% |
| 0.3 - 0.5 FTE | 19 | 9% |
| 0.5 - 0.7 FTE | 19 | 9% |
| 0.7 - 1.0 FTE | 10 | 5% |
| > 1.0 FTE | 5 | 2% |

**Pharmacies with >1.0 FTE discrepancy:**

| ID | Mesto | Typ | Payroll FTE | All.csv FTE | Diff |
|----|-------|-----|-------------|-------------|------|
| 280 | Fiľakovo | C - street + | 0.95 | 2.08 | -1.13 |
| 294 | Zvolen, Tesco | B - shopping | 2.50 | 3.58 | -1.08 |
| 626 | Skalica, TESCO | B - shopping | 3.38 | 4.45 | -1.08 |
| 223 | Bratislava, Aupark | A - shopping premium | 9.77 | 8.71 | +1.06 |
| 48 | Čadca, TESCO | B - shopping | 2.94 | 3.99 | -1.05 |

**Note:** Negative diff means payroll shows fewer FTE than efektivita data.

### 2. E-Type Pharmacy Discrepancy (Hospital Supply)

E-type pharmacies (poliklinika) consistently show higher FTE in payroll data than in efektivita.

**Reason:** These pharmacies have additional FTE dedicated to hospital supply chain operations. This FTE is:
- Included in payroll data
- NOT included in retail FTE metrics (efektivita)

**Impact:** E pharmacies often appear "overstaffed" when comparing predicted vs actual FTE, because the model predicts retail FTE needs while actual staffing includes hospital logistics.

**Solution:** Added `hospital_supply` flag to identify these pharmacies in the app.

### 3. GROSS FTE Calculation Methods

Two methods were used historically:

| Method | Formula | Source |
|--------|---------|--------|
| Factor-based | `(fte_F × factor_F) + (fte_L × factor_L) + (fte_ZF × factor_ZF)` | Role FTE × payroll factors |
| Direct | `fte + fte_n` | Efektivita data |

**Comparison:**
- Mean difference: +0.12 FTE
- Standard deviation: 0.51 FTE
- Range: -2.3 to +1.9 FTE

**Current approach:** Using direct method (`fte + fte_n`) as it's simpler and uses data from a single source.

## Model Training Data

The model was trained on `ml_ready_v3.csv` which includes:

### Input Features
- `bloky` - Transaction count
- `trzby` - Revenue (EUR)
- `podiel_rx` - Prescription ratio
- `typ` - Pharmacy type (A-E)
- Various derived features (productivity, seasonality, etc.)

### Target Variable
- `predicted_fte` - Recommended FTE based on workload

### Comparison Metric
- `actual_fte_gross` = `fte + fte_n` (current staffing)
- `fte_diff` = `actual_fte_gross - predicted_fte`

## Flags and Indicators

| Column | Type | Description |
|--------|------|-------------|
| `hospital_supply` | Boolean | True for E-type pharmacies with surplus FTE >0.5 (likely serving hospital) |
| `is_above_avg_productivity` | Boolean | Productivity above segment average |

**Hospital supply flagged pharmacies (10):**

Based on server's FTE calculation (gross factors method), E pharmacies with surplus > 0.5 FTE:

| ID | Mesto | Surplus |
|----|-------|---------|
| 262 | Michalovce | +2.7 FTE |
| 97 | Trebišov, Nemocnica s pol. | +2.6 FTE |
| 136 | Rožňava, nemocnica | +2.1 FTE |
| 98 | Spiš.N.Ves, poliklinika | +1.7 FTE |
| 240 | Topolčany, Nemocnica | +1.5 FTE |
| 41 | Žiar n.H., NsP 2 | +1.0 FTE |
| 277 | Nováky | +0.9 FTE |
| 22 | Rimavská Sobota, NsP | +0.9 FTE |
| 144 | Nemocnica Dunajská Streda | +0.8 FTE |
| 37 | Čierna n.T., poliklinika | +0.7 FTE |

## Recommendations

1. **E-pharmacy analysis:** When reviewing E-type pharmacies, consider that FTE includes hospital logistics
2. **Large discrepancies:** Pharmacies with >1.0 FTE discrepancy between data sources should be verified manually
3. **Future data updates:** Maintain consistency between efektivita and fte.csv sources
