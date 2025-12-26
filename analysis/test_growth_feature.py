"""
Test if adding YoY revenue growth improves FTE model accuracy.

Hypothesis: Knowing the revenue trend helps predict optimal FTE better.
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import cross_val_score, KFold
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import warnings
warnings.filterwarnings('ignore')

# Load data
print("Loading data...")
df_train = pd.read_csv('data/ml_ready_v3.csv')
df_revenue = pd.read_csv('data/revenue_annual.csv')

# Merge with revenue growth data
df = df_train.merge(df_revenue[['id', 'yoy_growth_2020', 'yoy_growth_2021']], on='id', how='left')

# Clean up - fill missing growth values with 0 (no growth info)
df['yoy_growth_2020'] = df['yoy_growth_2020'].fillna(0)
df['yoy_growth_2021'] = df['yoy_growth_2021'].fillna(0)

print(f"Total pharmacies: {len(df)}")
print(f"With growth data: {(df['yoy_growth_2021'] != 0).sum()}")

# Define features
base_features = ['trzby', 'bloky', 'podiel_rx', 'produktivita', 'is_shopping', 'is_poliklinika', 'is_street']
categorical_features = ['typ']
target = 'fte'

# Filter to rows with valid data
df_clean = df.dropna(subset=base_features + [target])
print(f"Valid rows: {len(df_clean)}")

# Prepare X and y
X_base = df_clean[base_features + categorical_features].copy()
X_with_growth = df_clean[base_features + categorical_features + ['yoy_growth_2021']].copy()
y = df_clean[target]

# Create preprocessing pipeline
def create_pipeline(features, categorical_features):
    numeric_features = [f for f in features if f not in categorical_features]

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numeric_features),
            ('cat', OneHotEncoder(drop='first', sparse_output=False, handle_unknown='ignore'), categorical_features)
        ])

    return Pipeline([
        ('preprocessor', preprocessor),
        ('regressor', Ridge(alpha=1.0))
    ])

# Cross-validation setup
cv = KFold(n_splits=5, shuffle=True, random_state=42)

print("\n" + "="*60)
print("MODEL COMPARISON: Base vs Base + Growth Feature")
print("="*60)

# Model 1: Base features only
print("\n[Model 1] Base features only")
print(f"Features: {base_features + categorical_features}")
pipeline_base = create_pipeline(base_features + categorical_features, categorical_features)

scores_base = cross_val_score(pipeline_base, X_base, y, cv=cv, scoring='r2')
mae_base = -cross_val_score(pipeline_base, X_base, y, cv=cv, scoring='neg_mean_absolute_error')
rmse_base = np.sqrt(-cross_val_score(pipeline_base, X_base, y, cv=cv, scoring='neg_mean_squared_error'))

print(f"  R² Score:  {scores_base.mean():.4f} (±{scores_base.std():.4f})")
print(f"  MAE:       {mae_base.mean():.4f} FTE (±{mae_base.std():.4f})")
print(f"  RMSE:      {rmse_base.mean():.4f} FTE (±{rmse_base.std():.4f})")

# Model 2: Base + Growth feature
print("\n[Model 2] Base + YoY Growth 2021")
print(f"Features: {base_features + categorical_features + ['yoy_growth_2021']}")
pipeline_growth = create_pipeline(base_features + categorical_features + ['yoy_growth_2021'], categorical_features)

scores_growth = cross_val_score(pipeline_growth, X_with_growth, y, cv=cv, scoring='r2')
mae_growth = -cross_val_score(pipeline_growth, X_with_growth, y, cv=cv, scoring='neg_mean_absolute_error')
rmse_growth = np.sqrt(-cross_val_score(pipeline_growth, X_with_growth, y, cv=cv, scoring='neg_mean_squared_error'))

print(f"  R² Score:  {scores_growth.mean():.4f} (±{scores_growth.std():.4f})")
print(f"  MAE:       {mae_growth.mean():.4f} FTE (±{mae_growth.std():.4f})")
print(f"  RMSE:      {rmse_growth.mean():.4f} FTE (±{rmse_growth.std():.4f})")

# Comparison
print("\n" + "="*60)
print("COMPARISON")
print("="*60)
r2_diff = scores_growth.mean() - scores_base.mean()
mae_diff = mae_growth.mean() - mae_base.mean()
rmse_diff = rmse_growth.mean() - rmse_base.mean()

print(f"\nR² change:   {r2_diff:+.4f} ({'better' if r2_diff > 0 else 'worse'})")
print(f"MAE change:  {mae_diff:+.4f} FTE ({'better' if mae_diff < 0 else 'worse'})")
print(f"RMSE change: {rmse_diff:+.4f} FTE ({'better' if rmse_diff < 0 else 'worse'})")

# Statistical significance check
from scipy import stats
t_stat, p_value = stats.ttest_rel(scores_growth, scores_base)
print(f"\nPaired t-test p-value: {p_value:.4f}")
if p_value < 0.05:
    print("Result: Statistically significant difference")
else:
    print("Result: No statistically significant difference")

# Feature importance (train on full data)
print("\n" + "="*60)
print("FEATURE IMPORTANCE (with growth feature)")
print("="*60)

pipeline_growth.fit(X_with_growth, y)
feature_names = (base_features +
                 list(pipeline_growth.named_steps['preprocessor']
                      .named_transformers_['cat']
                      .get_feature_names_out(categorical_features)) +
                 ['yoy_growth_2021'])

# Get coefficients
coefficients = pipeline_growth.named_steps['regressor'].coef_
importance = pd.DataFrame({
    'feature': feature_names[:len(coefficients)],
    'coefficient': coefficients
})
importance['abs_coef'] = importance['coefficient'].abs()
importance = importance.sort_values('abs_coef', ascending=False)

print("\nTop features by absolute coefficient:")
for _, row in importance.head(10).iterrows():
    print(f"  {row['feature']:25s}: {row['coefficient']:+.4f}")

# Check growth feature specifically
growth_coef = importance[importance['feature'] == 'yoy_growth_2021']['coefficient'].values
if len(growth_coef) > 0:
    print(f"\n>> yoy_growth_2021 coefficient: {growth_coef[0]:+.4f}")
    print(f"   Interpretation: {abs(growth_coef[0]):.4f} FTE change per 1% revenue growth")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)
if r2_diff > 0.01 and p_value < 0.05:
    print("✓ Adding revenue growth IMPROVES model accuracy significantly")
elif r2_diff > 0:
    print("~ Adding revenue growth shows slight improvement (not significant)")
else:
    print("✗ Adding revenue growth does NOT improve model accuracy")
