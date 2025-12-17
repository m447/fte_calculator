"""
FTE Prediction Model v5 - Asymmetric Productivity Adjustment
=============================================================
Based on v4, but with ASYMMETRIC prod_residual:
  - Positive prod_residual (efficient): Full credit → fewer FTE predicted
  - Negative prod_residual (inefficient): Clipped to 0 → no extra FTE

This creates fair incentives:
  - Rewards efficiency
  - Does NOT compensate for inefficiency
  - Motivates underperforming pharmacies to improve

Output:
    - models/fte_model_v5.pkl - Model with asymmetric prod_residual
"""

import pandas as pd
import numpy as np
import pickle
import warnings
from pathlib import Path
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "ml_ready_v3.csv"
MODELS_PATH = PROJECT_ROOT / "models"
RESULTS_PATH = PROJECT_ROOT / "results"

RESULTS_PATH.mkdir(exist_ok=True)


def calculate_vif(X, feature_names):
    """Calculate Variance Inflation Factor for each feature."""
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    X_with_const = np.column_stack([np.ones(X.shape[0]), X])
    vif_data = []
    for i, feature in enumerate(feature_names):
        vif = variance_inflation_factor(X_with_const, i + 1)
        vif_data.append({'feature': feature, 'VIF': vif})
    return pd.DataFrame(vif_data).sort_values('VIF', ascending=False)


def load_and_prepare_data():
    """Load data and prepare for prediction with asymmetric prod_residual."""
    df = pd.read_csv(DATA_PATH)

    # RX time factor
    RX_TIME_FACTOR = 0.41
    df['effective_bloky'] = df['bloky'] * (1 + RX_TIME_FACTOR * df['podiel_rx'])

    # Calculate segment mean productivity
    segment_prod_means = df.groupby('typ')['produktivita'].mean()
    print("\nSegment productivity means:")
    for typ, mean in segment_prod_means.items():
        print(f"  {typ}: {mean:.2f} txn/emp/hr")

    # Calculate prod_residual (raw)
    df['prod_residual_raw'] = df.apply(
        lambda row: row['produktivita'] - segment_prod_means[row['typ']],
        axis=1
    )

    # ASYMMETRIC: Clip negative values to 0
    # Positive (efficient) = full credit
    # Negative (inefficient) = no extra FTE
    df['prod_residual'] = df['prod_residual_raw'].clip(lower=0)

    print(f"\nProd_residual statistics:")
    print(f"  Raw:     mean={df['prod_residual_raw'].mean():.3f}, std={df['prod_residual_raw'].std():.2f}")
    print(f"  Clipped: mean={df['prod_residual'].mean():.3f}, std={df['prod_residual'].std():.2f}")
    print(f"  Pharmacies with positive (rewarded): {(df['prod_residual_raw'] > 0).sum()}")
    print(f"  Pharmacies with negative (clipped):  {(df['prod_residual_raw'] < 0).sum()}")

    # Feature columns
    cat_features = ['typ']
    num_features = [
        'effective_bloky',          # Primary workload
        'trzby',                    # Revenue
        'revenue_per_transaction',  # Basket value
        'podiel_rx',                # RX complexity
        'bloky_range',              # Variability
        'trzby_cv', 'bloky_cv',     # Coefficients of variation
        'kpi_mean',                 # Quality proxy
        'seasonal_peak_factor',     # Seasonality
        'prod_residual',            # ASYMMETRIC: Only positive values count
    ]

    # Drop rows with missing values
    required_cols = num_features + ['fte', 'fte_F', 'fte_L', 'fte_ZF']
    df_clean = df.dropna(subset=required_cols)

    print(f"\nLoaded {len(df_clean)} complete records")
    print(f"\nFeatures ({len(num_features)} numeric + 1 categorical):")
    for f in num_features:
        marker = " <- ASYMMETRIC (clipped at 0)" if f == 'prod_residual' else ""
        print(f"  - {f}{marker}")

    return df_clean, cat_features, num_features, segment_prod_means.to_dict()


def validate_features(df, num_features):
    """Validate features for multicollinearity."""
    print("\n" + "=" * 60)
    print("VIF VALIDATION")
    print("=" * 60)

    X_numeric = df[num_features].values
    vif_df = calculate_vif(X_numeric, num_features)

    print("\nVariance Inflation Factors:")
    for _, row in vif_df.iterrows():
        vif = row['VIF']
        status = " [HIGH]" if vif > 10 else " [OK]" if vif < 5 else ""
        print(f"  {row['feature']:30s}: {vif:8.2f}{status}")

    return vif_df


def train_models(df, cat_features, num_features):
    """Train models for total FTE and each role."""
    feature_cols = cat_features + num_features
    X = df[feature_cols]

    targets = {
        'fte': df['fte'],
        'fte_F': df['fte_F'],
        'fte_L': df['fte_L'],
        'fte_ZF': df['fte_ZF']
    }

    X_train, X_test, idx_train, idx_test = train_test_split(
        X, df.index, test_size=0.2, random_state=42
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), num_features),
            ('cat', OneHotEncoder(drop='first', sparse_output=False), cat_features)
        ],
        remainder='drop'
    )

    models = {}

    print("\n" + "=" * 60)
    print("MODEL TRAINING")
    print("=" * 60)

    for target_name, y in targets.items():
        print(f"\n{target_name}:")

        y_train = y.loc[idx_train]
        y_test = y.loc[idx_test]

        pipeline = Pipeline([
            ('preprocessor', preprocessor),
            ('model', Ridge(alpha=1.0))
        ])

        pipeline.fit(X_train, y_train)

        y_pred = pipeline.predict(X_test)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)

        cv_scores = cross_val_score(pipeline, X, y.loc[X.index], cv=5, scoring='r2')

        residuals = y_test - y_pred
        pred_std = residuals.std()

        print(f"  R2: {r2:.3f}, RMSE: {rmse:.3f}, CV R2: {cv_scores.mean():.3f}")

        models[target_name] = {
            'pipeline': pipeline,
            'rmse': rmse,
            'r2': r2,
            'cv_r2_mean': cv_scores.mean(),
            'cv_r2_std': cv_scores.std(),
            'std': pred_std
        }

    # Print prod_residual coefficient
    fte_model = models['fte']['pipeline']
    feature_names = num_features + list(fte_model.named_steps['preprocessor'].named_transformers_['cat'].get_feature_names_out(cat_features))
    coefs = fte_model.named_steps['model'].coef_
    prod_idx = num_features.index('prod_residual')
    print(f"\nprod_residual coefficient: {coefs[prod_idx]:.4f}")
    print(f"  -> +1 txn/hr above segment avg = {abs(coefs[prod_idx]):.2f} fewer FTE (reward)")
    print(f"  -> Negative productivity: NO extra FTE (clipped to 0)")

    return models


def calculate_role_proportions(df):
    """Calculate typical role proportions by store type."""
    proportions = df.groupby('typ').apply(
        lambda x: pd.Series({
            'prop_F': x['fte_F'].sum() / x['fte'].sum(),
            'prop_L': x['fte_L'].sum() / x['fte'].sum(),
            'prop_ZF': x['fte_ZF'].sum() / x['fte'].sum(),
            'avg_fte': x['fte'].mean(),
            'std_fte': x['fte'].std(),
            'count': len(x)
        })
    ).to_dict('index')
    return proportions


def compare_with_v4(df, models, segment_prod_means):
    """Compare predictions with v4 model."""
    print("\n" + "=" * 60)
    print("COMPARISON: v5 (asymmetric) vs v4 (symmetric)")
    print("=" * 60)

    # Load v4 model for comparison
    v4_path = MODELS_PATH / "fte_model_v4.pkl"
    if not v4_path.exists():
        print("  v4 model not found, skipping comparison")
        return

    with open(v4_path, 'rb') as f:
        v4_pkg = pickle.load(f)

    # Prepare features for both models
    RX_TIME_FACTOR = 0.41

    results = []
    for _, row in df.iterrows():
        # Raw prod_residual
        prod_res_raw = row['produktivita'] - segment_prod_means[row['typ']]

        # v4 features (symmetric)
        features_v4 = {
            'typ': row['typ'],
            'effective_bloky': row['bloky'] * (1 + RX_TIME_FACTOR * row['podiel_rx']),
            'trzby': row['trzby'],
            'revenue_per_transaction': row['trzby'] / row['bloky'],
            'podiel_rx': row['podiel_rx'],
            'bloky_range': row['bloky_range'],
            'trzby_cv': row['trzby_cv'],
            'bloky_cv': row['bloky_cv'],
            'kpi_mean': row['kpi_mean'],
            'seasonal_peak_factor': row['seasonal_peak_factor'],
            'prod_residual': prod_res_raw,  # v4: raw value
        }

        # v5 features (asymmetric)
        features_v5 = features_v4.copy()
        features_v5['prod_residual'] = max(0, prod_res_raw)  # v5: clipped

        # Predictions
        X_v4 = pd.DataFrame([features_v4])
        X_v5 = pd.DataFrame([features_v5])

        pred_v4 = v4_pkg['models']['fte'].predict(X_v4)[0]
        pred_v5 = models['fte']['pipeline'].predict(X_v5)[0]

        results.append({
            'id': row['id'],
            'typ': row['typ'],
            'actual': row['fte'],
            'prod_residual_raw': prod_res_raw,
            'pred_v4': pred_v4,
            'pred_v5': pred_v5,
            'diff_v5_v4': pred_v5 - pred_v4,
        })

    results_df = pd.DataFrame(results)

    # Show impact on inefficient pharmacies
    inefficient = results_df[results_df['prod_residual_raw'] < -0.5]
    efficient = results_df[results_df['prod_residual_raw'] > 0.5]

    print(f"\nImpact on INEFFICIENT pharmacies (prod_residual < -0.5):")
    print(f"  Count: {len(inefficient)}")
    if len(inefficient) > 0:
        print(f"  Avg v4 prediction: {inefficient['pred_v4'].mean():.2f}")
        print(f"  Avg v5 prediction: {inefficient['pred_v5'].mean():.2f}")
        print(f"  Avg change: {inefficient['diff_v5_v4'].mean():+.2f} FTE (v5 predicts LESS)")

    print(f"\nImpact on EFFICIENT pharmacies (prod_residual > 0.5):")
    print(f"  Count: {len(efficient)}")
    if len(efficient) > 0:
        print(f"  Avg v4 prediction: {efficient['pred_v4'].mean():.2f}")
        print(f"  Avg v5 prediction: {efficient['pred_v5'].mean():.2f}")
        print(f"  Avg change: {efficient['diff_v5_v4'].mean():+.2f} FTE")

    # Example pharmacies
    print("\nExample comparisons:")
    examples = pd.concat([
        results_df.nsmallest(3, 'diff_v5_v4'),  # Most reduced (inefficient)
        results_df.nlargest(3, 'diff_v5_v4'),   # Least changed (efficient)
    ])
    for _, row in examples.iterrows():
        print(f"  ID {int(row['id']):3d} ({row['typ'][:10]:10s}): "
              f"prod_res={row['prod_residual_raw']:+.2f}, "
              f"v4={row['pred_v4']:.1f}, v5={row['pred_v5']:.1f}, "
              f"change={row['diff_v5_v4']:+.2f}")


def main():
    print("=" * 60)
    print("FTE PREDICTION MODEL v5 - Asymmetric Productivity")
    print("=" * 60)
    print("\nChanges from v4:")
    print("  + prod_residual clipped at 0 (asymmetric)")
    print("  + Efficient pharmacies: rewarded with fewer FTE")
    print("  + Inefficient pharmacies: NO extra FTE (fair incentive)")

    # Load data
    df, cat_features, num_features, segment_prod_means = load_and_prepare_data()

    # Validate features
    vif_df = validate_features(df, num_features)

    # Train models
    models = train_models(df, cat_features, num_features)

    # Calculate role proportions
    proportions = calculate_role_proportions(df)

    # Compare with v4
    compare_with_v4(df, models, segment_prod_means)

    # Package
    RX_TIME_FACTOR = 0.41
    model_package = {
        'models': {k: v['pipeline'] for k, v in models.items()},
        'metrics': {k: {'rmse': v['rmse'], 'std': v['std'], 'r2': v['r2'],
                       'cv_r2_mean': v['cv_r2_mean'], 'cv_r2_std': v['cv_r2_std']}
                   for k, v in models.items()},
        'proportions': proportions,
        'segment_prod_means': segment_prod_means,
        'feature_cols': cat_features + num_features,
        'cat_features': cat_features,
        'num_features': num_features,
        'rx_time_factor': RX_TIME_FACTOR,
        'version': 'v5',
        'notes': 'Asymmetric prod_residual: only positive values rewarded, negative clipped to 0'
    }

    # Save
    model_path = MODELS_PATH / "fte_model_v5.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump(model_package, f)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nFTE Model: R2 = {models['fte']['r2']:.3f}, RMSE = {models['fte']['rmse']:.3f}")
    print(f"\nModel saved: {model_path}")

    print("\nSegment productivity means (for prod_residual calculation):")
    for typ, mean in segment_prod_means.items():
        print(f"  '{typ}': {mean:.2f}")

    print("\nINCENTIVE STRUCTURE:")
    print("  + Above-average productivity → Fewer FTE predicted (reward)")
    print("  + Below-average productivity → Same FTE as average (no penalty, no reward)")
    print("  = Fair system that motivates improvement")


if __name__ == "__main__":
    main()
