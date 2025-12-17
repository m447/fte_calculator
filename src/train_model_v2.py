"""
FTE Prediction Model v2 - Predicts FTE by Role
===============================================
Predicts optimal FTE for each role: F (Pharmacist), L (Sales), ZF (Additional Pharmacist)

Output:
    - models/fte_model_v2.pkl - Model for total FTE with role breakdown
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
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "ml_ready_v3.csv"
MODELS_PATH = PROJECT_ROOT / "models"


def load_and_prepare_data():
    """Load data and prepare for multi-target prediction."""
    df = pd.read_csv(DATA_PATH)

    # RX transactions take ~41% more time than OTC (empirically measured)
    # Create effective workload: bloky adjusted for RX complexity
    RX_TIME_FACTOR = 0.41  # 41% more time for RX vs OTC
    df['effective_bloky'] = df['bloky'] * (1 + RX_TIME_FACTOR * df['podiel_rx'])

    # Feature columns (excluding leakage)
    cat_features = ['typ']
    num_features = [
        'bloky', 'trzby', 'effective_bloky', 'revenue_per_transaction',
        'produktivita', 'bloky_range', 'trzby_cv', 'bloky_cv',
        'avg_base_salary', 'hourly_rate'
    ]

    # Drop rows with missing values in key columns
    base_num_features = [f for f in num_features if f != 'effective_bloky']
    required_cols = base_num_features + ['fte', 'fte_F', 'fte_L', 'fte_ZF']
    df_clean = df.dropna(subset=required_cols)

    print(f"Loaded {len(df_clean)} complete records")

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

        # Calculate prediction std for tolerance
        residuals = y_test - y_pred
        pred_std = residuals.std()

        print(f"  RMSE: {rmse:.3f}, MAE: {mae:.3f}, R2: {r2:.3f}")

        models[target_name] = {
            'pipeline': pipeline,
            'rmse': rmse,
            'mae': mae,
            'r2': r2,
            'std': pred_std
        }

        results.append({
            'target': target_name,
            'rmse': rmse,
            'mae': mae,
            'r2': r2,
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


def main():
    print("=" * 60)
    print("FTE PREDICTION MODEL v2 - Role Breakdown")
    print("=" * 60)

    # Load data
    df, cat_features, num_features = load_and_prepare_data()

    # Train models
    models, results_df = train_models(df, cat_features, num_features)

    # Calculate role proportions by store type
    proportions = calculate_role_proportions(df)

    # Package everything
    RX_TIME_FACTOR = 0.41  # Must match the value used in load_and_prepare_data
    model_package = {
        'models': {k: v['pipeline'] for k, v in models.items()},
        'metrics': {k: {'rmse': v['rmse'], 'std': v['std']} for k, v in models.items()},
        'proportions': proportions,
        'feature_cols': cat_features + num_features,
        'cat_features': cat_features,
        'num_features': num_features,
        'rx_time_factor': RX_TIME_FACTOR
    }

    # Save
    model_path = MODELS_PATH / "fte_model_v2.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump(model_package, f)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(results_df.to_string(index=False))

    print(f"\n\nRole Proportions by Store Type:")
    for typ, props in proportions.items():
        print(f"\n{typ}:")
        print(f"  F: {props['prop_F']*100:.1f}%, L: {props['prop_L']*100:.1f}%, ZF: {props['prop_ZF']*100:.1f}%")
        print(f"  Avg FTE: {props['avg_fte']:.2f} (±{props['std_fte']:.2f})")

    print(f"\n\nModel saved: {model_path}")


if __name__ == "__main__":
    main()
