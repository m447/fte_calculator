# Dr.Max Pharmacy FTE Prediction Model

Machine learning model to predict optimal Full-Time Equivalent (FTE) staffing for pharmacies based on operational characteristics.

## Latest Changes (v5)

### Asymmetric Productivity Model
- **prod_residual** feature with asymmetric clipping:
  - Efficient pharmacies (above segment average): **rewarded** with fewer predicted FTE
  - Inefficient pharmacies (below average): **no extra FTE** (clipped to 0)
- Creates fair incentive structure - no reward for inefficiency

### UI Updates
- Productivity toggle in calculator (Priemerná / Nadpriemerná)
- Fixed GROSS FTE calculation to use actual role breakdown
- Sensitivity slider for productivity impact visualization

### Model Versions
| Version | Description | R² |
|---------|-------------|-----|
| v3 | Base model (no productivity) | 0.873 |
| v4 | + prod_residual (symmetric) | 0.965 |
| v5 | + asymmetric prod_residual | 0.927 |

## Project Overview

This project analyzes pharmacy operational data to predict the optimal number of staff (FTE) required based on:
- Transaction volume
- Revenue
- Store type
- Prescription complexity
- Other operational metrics

## Model Performance

| Metric | Value |
|--------|-------|
| **R² Score** | 0.971 (97.1% variance explained) |
| **RMSE** | 0.29 FTE |
| **MAE** | 0.19 FTE |
| **Best Model** | Linear Regression |

### Top Predictive Features

| Rank | Feature | Importance |
|------|---------|------------|
| 1 | `bloky` (transactions) | 1.099 |
| 2 | `produktivita` (efficiency) | 0.915 |
| 3 | `trzby` (revenue) | 0.601 |
| 4 | `revenue_per_transaction` | 0.344 |
| 5 | `typ` (store type) | 0.289 |

## Project Structure

```
57_drmax/
├── data/
│   ├── raw/                    # Original source files
│   ├── payroll/                # Payroll data
│   ├── ml_ready_v3.csv         # ML-ready dataset
│   └── DATA_DICTIONARY.md      # Column documentation
├── models/
│   └── fte_model.pkl           # Trained model
├── results/
│   ├── model_evaluation.csv    # Model comparison
│   ├── feature_importance.csv  # Feature rankings
│   └── predictions.csv         # Test predictions
├── src/
│   ├── train_model.py          # Training script
│   └── predict.py              # Prediction script
├── venv/                       # Python virtual environment
├── requirements.txt            # Dependencies
└── README.md                   # This file
```

## Live Application

**Production URL:** https://fte-calculator-638044991573.europe-west1.run.app

**GCP Project:** `gen-lang-client-0415148507`

## Installation

```bash
# Clone/navigate to project
cd /Users/mariansvatko/Code/57_drmax

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Train Model

```bash
source venv/bin/activate
python src/train_model.py
```

### Predict FTE

#### Single Pharmacy Prediction

```bash
python src/predict.py \
    --bloky 50000 \
    --trzby 1000000 \
    --typ "B - shopping" \
    --podiel_rx 0.5
```

#### Predict for All Pharmacies

```bash
python src/predict.py --all
```

### Example Prediction

```
Input:
  Transactions (bloky): 50,000
  Revenue (trzby):      EUR 1,000,000
  Store type:           B - shopping
  RX ratio:             50%

Predicted FTE: 3.45
```

## Data Sources

| File | Description | Records |
|------|-------------|---------|
| `all.csv` | Aggregated annual metrics | 286 |
| `data.csv` | Monthly time series | 3,432 |
| `fte.csv` | FTE by function type | 937 |
| `mzdy.csv` | Payroll records | 17,727 |

See `data/DATA_DICTIONARY.md` for detailed column descriptions.

## Store Types

| Code | Description | Avg FTE |
|------|-------------|---------|
| A - shopping premium | Premium shopping centers | 5.76 |
| B - shopping | Shopping centers (Kaufland, TESCO) | 4.88 |
| C - street + | High-traffic street locations | 2.68 |
| D - street | Standard street locations | 2.35 |
| E - poliklinika | Clinic-attached pharmacies | 3.27 |

## Model Details

### Features Used

**Volume Metrics:**
- `bloky` - Annual transaction count
- `trzby` - Annual revenue (EUR)
- `bloky_range` - Seasonal transaction range

**Ratios:**
- `podiel_rx` - Prescription ratio
- `produktivita` - Revenue efficiency per FTE
- `revenue_per_transaction` - Average transaction value

**Store Characteristics:**
- `typ` - Store type (categorical)
- `is_shopping`, `is_street`, `is_poliklinika` - Binary flags

**Excluded (data leakage):**
- `naklady` - Wage costs (directly depends on FTE)

### Models Evaluated

| Model | Test R² | Test RMSE |
|-------|---------|-----------|
| Linear Regression | **0.971** | **0.293** |
| Ridge | 0.970 | 0.294 |
| Gradient Boosting | 0.938 | 0.425 |
| Random Forest | 0.919 | 0.485 |
| Lasso | 0.903 | 0.532 |

## Key Insights

1. **Transaction volume (`bloky`) is the strongest predictor** - more transactions = more staff needed

2. **Store type matters** - Shopping centers need ~2x more FTE than street pharmacies

3. **High RX ratio reduces FTE need** - Clinic pharmacies are more efficient per transaction

4. **Linear relationship** - Simple linear regression outperforms complex models, suggesting FTE scales linearly with workload

## Limitations

- Model trained on 286 pharmacies (Slovakia)
- Data period: Sep 2020 - Aug 2021 (COVID impact)
- Missing features: store size (m²), opening hours, competitor data

## Future Improvements

- [ ] Add store size data when available
- [ ] Include opening hours as feature
- [ ] Separate models for different store types
- [ ] Time-series forecasting for seasonal staffing

## Deployment

### Local Development

```bash
source venv/bin/activate
python -c "from app.server import app; app.run(host='0.0.0.0', port=5001)"
```

### Cloud Run Deployment

```bash
# Build and deploy
gcloud run deploy fte-calculator \
  --source . \
  --region europe-west1 \
  --project gen-lang-client-0415148507 \
  --allow-unauthenticated

# Update min instances (0 = cold start allowed, 1 = always warm)
gcloud run services update fte-calculator \
  --region europe-west1 \
  --min-instances 0 \
  --project gen-lang-client-0415148507
```

### Static Tools

- **FTE Calculator:** `/static/index-v2.html` - Main FTE prediction tool
- **Common Sense Calculator:** `/static/common-sense-calc.html` - Simple formula-based calculator
- **Utilization Analysis:** `/static/utilization.html` - Peak coverage analyzer

---

*Generated: December 2024*
