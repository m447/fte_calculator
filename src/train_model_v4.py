"""
FTE Prediction Model v4 - With Relative Productivity
=====================================================
Based on v3 (no data leakage), adds prod_residual:
  prod_residual = produktivita - segment_mean_produktivita

This captures "Is this pharmacy more/less efficient than its segment?"
without the data leakage issue of raw produktivita.

Output:
    - models/fte_model_v4.pkl - Model with prod_residual
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
    """Load data and prepare for prediction with prod_residual."""
    df = pd.read_csv(DATA_PATH)

    # RX time factor
    RX_TIME_FACTOR = 0.41
    df['effective_bloky'] = df['bloky'] * (1 + RX_TIME_FACTOR * df['podiel_rx'])

    # Calculate segment mean productivity
    segment_prod_means = df.groupby('typ')['produktivita'].mean()
    print("\nSegment productivity means:")
    for typ, mean in segment_prod_means.items():
        print(f"  {typ}: {mean:.2f} txn/emp/hr")

    # Calculate prod_residual if not already in data
    if 'prod_residual' not in df.columns:
        df['prod_residual'] = df.apply(
            lambda row: row['produktivita'] - segment_prod_means[row['typ']],
            axis=1
        )
        print(f"\nCalculated prod_residual: mean={df['prod_residual'].mean():.4f}, std={df['prod_residual'].std():.2f}")

    # Feature columns - v3 features PLUS prod_residual
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
        'prod_residual',            # NEW: Relative efficiency vs segment
    ]

    # Drop rows with missing values
    required_cols = num_features + ['fte', 'fte_F', 'fte_L', 'fte_ZF']
    df_clean = df.dropna(subset=required_cols)

    print(f"\nLoaded {len(df_clean)} complete records")
    print(f"\nFeatures ({len(num_features)} numeric + 1 categorical):")
    for f in num_features:
        marker = " <- NEW" if f == 'prod_residual' else ""
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
    print(f"  -> +1 txn/hr above segment avg = {abs(coefs[prod_idx]):.2f} fewer FTE")

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


def main():
    print("=" * 60)
    print("FTE PREDICTION MODEL v4 - With Relative Productivity")
    print("=" * 60)
    print("\nChanges from v3:")
    print("  + Added 'prod_residual' = produktivita - segment_mean")
    print("  + Captures relative efficiency without data leakage")

    # Load data
    df, cat_features, num_features, segment_prod_means = load_and_prepare_data()

    # Validate features
    vif_df = validate_features(df, num_features)

    # Train models
    models = train_models(df, cat_features, num_features)

    # Calculate role proportions
    proportions = calculate_role_proportions(df)

    # Package
    RX_TIME_FACTOR = 0.41
    model_package = {
        'models': {k: v['pipeline'] for k, v in models.items()},
        'metrics': {k: {'rmse': v['rmse'], 'std': v['std'], 'r2': v['r2'],
                       'cv_r2_mean': v['cv_r2_mean'], 'cv_r2_std': v['cv_r2_std']}
                   for k, v in models.items()},
        'proportions': proportions,
        'segment_prod_means': segment_prod_means,  # NEW: for computing prod_residual
        'feature_cols': cat_features + num_features,
        'cat_features': cat_features,
        'num_features': num_features,
        'rx_time_factor': RX_TIME_FACTOR,
        'version': 'v4',
        'notes': 'Added prod_residual (relative productivity vs segment)'
    }

    # Save
    model_path = MODELS_PATH / "fte_model_v4.pkl"
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


if __name__ == "__main__":
    main()
