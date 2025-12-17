"""
FTE Prediction Model v3 - Fixed Data Leakage
=============================================
Removed produktivita (trzby/FTE) which contained target variable.
Added VIF validation to check for multicollinearity.

Output:
    - models/fte_model_v3.pkl - Model for total FTE with role breakdown
    - results/vif_report.csv - Variance Inflation Factors
    - results/correlation_matrix.csv - Feature correlations
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

# Ensure results directory exists
RESULTS_PATH.mkdir(exist_ok=True)


def calculate_vif(X, feature_names):
    """Calculate Variance Inflation Factor for each feature."""
    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor

        # Add constant for VIF calculation
        X_with_const = np.column_stack([np.ones(X.shape[0]), X])

        vif_data = []
        for i, feature in enumerate(feature_names):
            vif = variance_inflation_factor(X_with_const, i + 1)  # +1 for constant
            vif_data.append({'feature': feature, 'VIF': vif})

        vif_df = pd.DataFrame(vif_data).sort_values('VIF', ascending=False)
        return vif_df
    except ImportError:
        print("  [WARNING] statsmodels not installed, using correlation-based VIF approximation")
        # Approximate VIF using R² from regression
        vif_data = []
        for i, feature in enumerate(feature_names):
            # VIF ≈ 1 / (1 - R²) where R² is from regressing feature on others
            other_features = [f for j, f in enumerate(feature_names) if j != i]
            if len(other_features) > 0:
                X_others = X[:, [j for j in range(len(feature_names)) if j != i]]
                y_feature = X[:, i]
                # Simple correlation-based approximation
                corr_matrix = np.corrcoef(X.T)
                r_squared = 1 - (1 / (1 + np.sum(corr_matrix[i, :] ** 2) - 1))
                vif = 1 / (1 - min(r_squared, 0.99))
            else:
                vif = 1.0
            vif_data.append({'feature': feature, 'VIF': vif})
        return pd.DataFrame(vif_data).sort_values('VIF', ascending=False)


def load_and_prepare_data():
    """Load data and prepare for multi-target prediction."""
    df = pd.read_csv(DATA_PATH)

    # RX transactions take ~41% more time than OTC (empirically measured)
    RX_TIME_FACTOR = 0.41
    df['effective_bloky'] = df['bloky'] * (1 + RX_TIME_FACTOR * df['podiel_rx'])

    # Feature columns - NO produktivita (data leakage), NO bloky_per_day (= bloky)
    cat_features = ['typ']
    num_features = [
        'effective_bloky',          # Primary workload (bloky × RX adjustment)
        'trzby',                    # Revenue
        'revenue_per_transaction',  # Basket value (trzby/bloky - no FTE)
        'podiel_rx',                # RX complexity ratio
        'bloky_range',              # Variability
        'trzby_cv', 'bloky_cv',     # Coefficients of variation
        'kpi_mean',                 # Quality/efficiency proxy
        'seasonal_peak_factor',     # Seasonality
    ]

    # Drop rows with missing values in key columns
    required_cols = num_features + ['fte', 'fte_F', 'fte_L', 'fte_ZF']
    df_clean = df.dropna(subset=required_cols)

    print(f"Loaded {len(df_clean)} complete records")
    print(f"\nFeatures used ({len(num_features)} numeric + 1 categorical):")
    for f in num_features:
        print(f"  - {f}")
    print(f"  - typ (categorical)")

    return df_clean, cat_features, num_features


def create_preprocessor(cat_features, num_features):
    """Create preprocessing pipeline."""
    return ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), num_features),
            ('cat', OneHotEncoder(drop='first', sparse_output=False), cat_features)
        ],
        remainder='drop'
    )


def validate_features(df, num_features):
    """Validate features for multicollinearity and correlations."""
    print("\n" + "=" * 60)
    print("FEATURE VALIDATION")
    print("=" * 60)

    # Correlation matrix
    corr_cols = num_features + ['fte']
    correlation_matrix = df[corr_cols].corr()
    correlation_matrix.to_csv(RESULTS_PATH / 'correlation_matrix.csv')
    print(f"\nCorrelation matrix saved to: {RESULTS_PATH / 'correlation_matrix.csv'}")

    # Print correlations with target
    print("\nCorrelation with FTE (target):")
    fte_corr = correlation_matrix['fte'].drop('fte').sort_values(key=abs, ascending=False)
    for feat, corr in fte_corr.items():
        print(f"  {feat:30s}: {corr:+.3f}")

    # VIF calculation
    X_numeric = df[num_features].values
    vif_df = calculate_vif(X_numeric, num_features)
    vif_df.to_csv(RESULTS_PATH / 'vif_report.csv', index=False)
    print(f"\nVIF report saved to: {RESULTS_PATH / 'vif_report.csv'}")

    print("\nVariance Inflation Factors:")
    for _, row in vif_df.iterrows():
        vif = row['VIF']
        status = ""
        if vif > 10:
            status = " [SEVERE]"
        elif vif > 5:
            status = " [WARNING]"
        print(f"  {row['feature']:30s}: {vif:8.2f}{status}")

    # Check for high VIF
    high_vif = vif_df[vif_df['VIF'] > 10]
    if len(high_vif) > 0:
        print(f"\n[WARNING] {len(high_vif)} features have VIF > 10 (severe multicollinearity)")
    else:
        print("\n[OK] No severe multicollinearity detected (all VIF < 10)")

    return vif_df, correlation_matrix


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

    # Train/test split
    X_train, X_test, idx_train, idx_test = train_test_split(
        X, df.index, test_size=0.2, random_state=42
    )

    preprocessor = create_preprocessor(cat_features, num_features)

    models = {}
    results = []

    print("\n" + "=" * 60)
    print("MODEL TRAINING")
    print("=" * 60)

    for target_name, y in targets.items():
        print(f"\nTraining {target_name}...")

        y_train = y.loc[idx_train]
        y_test = y.loc[idx_test]

        # Use Ridge for stability
        pipeline = Pipeline([
            ('preprocessor', preprocessor),
            ('model', Ridge(alpha=1.0))
        ])

        pipeline.fit(X_train, y_train)

        # Evaluate
        y_pred = pipeline.predict(X_test)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)

        # Cross-validation
        cv_scores = cross_val_score(pipeline, X, y.loc[X.index], cv=5, scoring='r2')
        cv_mean = cv_scores.mean()
        cv_std = cv_scores.std()

        # Calculate prediction std for tolerance
        residuals = y_test - y_pred
        pred_std = residuals.std()

        print(f"  RMSE: {rmse:.3f}, MAE: {mae:.3f}, R2: {r2:.3f}")
        print(f"  CV R2: {cv_mean:.3f} (+/- {cv_std:.3f})")

        models[target_name] = {
            'pipeline': pipeline,
            'rmse': rmse,
            'mae': mae,
            'r2': r2,
            'cv_r2_mean': cv_mean,
            'cv_r2_std': cv_std,
            'std': pred_std
        }

        results.append({
            'target': target_name,
            'rmse': rmse,
            'mae': mae,
            'r2': r2,
            'cv_r2': f"{cv_mean:.3f} +/- {cv_std:.3f}",
            'tolerance': pred_std * 1.96  # 95% CI
        })

    return models, pd.DataFrame(results)


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


def calculate_segment_productivity(df):
    """Calculate valid segment productivity benchmarks (not used as feature, for reference)."""
    RX_TIME_FACTOR = 0.41

    segment_productivity = df.groupby('typ').apply(
        lambda x: pd.Series({
            'effective_bloky_per_fte': (x['bloky'] * (1 + RX_TIME_FACTOR * x['podiel_rx'])).sum() / x['fte'].sum(),
            'bloky_per_fte': x['bloky'].sum() / x['fte'].sum(),
            'trzby_per_fte': x['trzby'].sum() / x['fte'].sum(),
        })
    ).to_dict('index')
    return segment_productivity


def main():
    print("=" * 60)
    print("FTE PREDICTION MODEL v3 - Fixed Data Leakage")
    print("=" * 60)
    print("\nChanges from v2:")
    print("  - Removed 'produktivita' (trzby/FTE) - contained target variable")
    print("  - Added VIF validation for multicollinearity")
    print("  - Added cross-validation scores")

    # Load data
    df, cat_features, num_features = load_and_prepare_data()

    # Validate features
    vif_df, corr_matrix = validate_features(df, num_features)

    # Train models
    models, results_df = train_models(df, cat_features, num_features)

    # Calculate role proportions by store type
    proportions = calculate_role_proportions(df)

    # Calculate segment productivity benchmarks
    segment_productivity = calculate_segment_productivity(df)

    # Package everything
    RX_TIME_FACTOR = 0.41
    model_package = {
        'models': {k: v['pipeline'] for k, v in models.items()},
        'metrics': {k: {'rmse': v['rmse'], 'std': v['std'], 'r2': v['r2'],
                       'cv_r2_mean': v['cv_r2_mean'], 'cv_r2_std': v['cv_r2_std']}
                   for k, v in models.items()},
        'proportions': proportions,
        'segment_productivity': segment_productivity,
        'feature_cols': cat_features + num_features,
        'cat_features': cat_features,
        'num_features': num_features,
        'rx_time_factor': RX_TIME_FACTOR,
        'version': 'v3',
        'notes': 'Removed produktivita (data leakage), added VIF validation'
    }

    # Save
    model_path = MODELS_PATH / "fte_model_v3.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump(model_package, f)

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(results_df.to_string(index=False))

    print(f"\n\nRole Proportions by Store Type:")
    for typ, props in proportions.items():
        print(f"\n{typ}:")
        print(f"  F: {props['prop_F']*100:.1f}%, L: {props['prop_L']*100:.1f}%, ZF: {props['prop_ZF']*100:.1f}%")
        print(f"  Avg FTE: {props['avg_fte']:.2f} (+/- {props['std_fte']:.2f})")

    print(f"\n\nSegment Productivity Benchmarks (effective_bloky/FTE):")
    for typ, prod in segment_productivity.items():
        print(f"  {typ}: {prod['effective_bloky_per_fte']:,.0f}")

    print(f"\n\nModel saved: {model_path}")
    print(f"VIF report: {RESULTS_PATH / 'vif_report.csv'}")
    print(f"Correlation matrix: {RESULTS_PATH / 'correlation_matrix.csv'}")


if __name__ == "__main__":
    main()
