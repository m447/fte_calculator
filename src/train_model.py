"""
FTE Prediction Model for Dr.Max Pharmacies
==========================================
Predicts optimal FTE (Full-Time Equivalent) staffing based on pharmacy characteristics.

Usage:
    python src/train_model.py

Output:
    - models/fte_model.pkl - Best trained model
    - results/model_evaluation.csv - Performance metrics
    - results/feature_importance.csv - Feature rankings
"""

import pandas as pd
import numpy as np
import pickle
import warnings
from pathlib import Path
from datetime import datetime

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

warnings.filterwarnings('ignore')

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "ml_ready_v3.csv"
MODELS_PATH = PROJECT_ROOT / "models"
RESULTS_PATH = PROJECT_ROOT / "results"


def load_data():
    """Load and prepare the ML dataset."""
    print("Loading data...")
    df = pd.read_csv(DATA_PATH)
    print(f"  Loaded {len(df)} records")
    return df


def prepare_features(df):
    """
    Prepare features and target for ML.

    Excludes:
    - naklady (data leakage - it's wages)
    - bloky_per_day (redundant with bloky)
    - Identifier columns
    - Target columns when predicting fte
    """
    # Define column groups
    id_cols = ['id', 'mesto', 'regional', 'region_code']
    target_cols = ['fte', 'fte_F', 'fte_L', 'fte_ZF']

    # Features to exclude (data leakage or redundant)
    exclude_cols = [
        'naklady',           # Data leakage (wages = f(FTE))
        'bloky_per_day',     # Redundant with bloky
        'pharmacist_ratio',  # Derived from targets
        'produktivita',      # Replaced by prod_residual (lower VIF, same predictive power)
    ]

    # Categorical features
    cat_features = ['typ']

    # Numeric features (everything else)
    all_cols = set(df.columns)
    num_features = list(all_cols - set(id_cols) - set(target_cols) -
                        set(exclude_cols) - set(cat_features))

    # Sort for consistency
    num_features = sorted(num_features)

    print(f"\nFeature groups:")
    print(f"  Categorical: {cat_features}")
    print(f"  Numeric: {num_features}")
    print(f"  Excluded: {exclude_cols}")

    return cat_features, num_features


def create_preprocessor(cat_features, num_features):
    """Create sklearn preprocessor for features."""
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), num_features),
            ('cat', OneHotEncoder(drop='first', sparse_output=False), cat_features)
        ],
        remainder='drop'
    )
    return preprocessor


def get_models():
    """Define models to evaluate."""
    models = {
        'Linear Regression': LinearRegression(),
        'Ridge': Ridge(alpha=1.0),
        'Lasso': Lasso(alpha=0.1),
        'Random Forest': RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1
        ),
        'Gradient Boosting': GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
    }
    return models


def evaluate_model(model, X_train, X_test, y_train, y_test):
    """Evaluate a single model."""
    # Train
    model.fit(X_train, y_train)

    # Predict
    y_train_pred = model.predict(X_train)
    y_test_pred = model.predict(X_test)

    # Metrics
    metrics = {
        'train_rmse': np.sqrt(mean_squared_error(y_train, y_train_pred)),
        'test_rmse': np.sqrt(mean_squared_error(y_test, y_test_pred)),
        'train_mae': mean_absolute_error(y_train, y_train_pred),
        'test_mae': mean_absolute_error(y_test, y_test_pred),
        'train_r2': r2_score(y_train, y_train_pred),
        'test_r2': r2_score(y_test, y_test_pred),
    }

    # Cross-validation
    cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring='r2')
    metrics['cv_r2_mean'] = cv_scores.mean()
    metrics['cv_r2_std'] = cv_scores.std()

    return metrics, y_test_pred


def get_feature_importance(model, feature_names):
    """Extract feature importance from model."""
    if hasattr(model, 'feature_importances_'):
        importance = model.feature_importances_
    elif hasattr(model, 'coef_'):
        importance = np.abs(model.coef_)
    else:
        return None

    importance_df = pd.DataFrame({
        'feature': feature_names,
        'importance': importance
    }).sort_values('importance', ascending=False)

    return importance_df


def main():
    """Main training pipeline."""
    print("=" * 60)
    print("FTE PREDICTION MODEL TRAINING")
    print("=" * 60)

    # Load data
    df = load_data()

    # Prepare features
    cat_features, num_features = prepare_features(df)
    feature_cols = cat_features + num_features

    # Handle missing values
    print("\nHandling missing values...")
    df_clean = df.dropna(subset=['fte'] + num_features)
    print(f"  Records after dropping NaN: {len(df_clean)}")

    # Split features and target
    X = df_clean[feature_cols]
    y = df_clean['fte']

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    print(f"\nData split:")
    print(f"  Train: {len(X_train)} samples")
    print(f"  Test: {len(X_test)} samples")

    # Create preprocessor
    preprocessor = create_preprocessor(cat_features, num_features)

    # Get models
    models = get_models()

    # Evaluate each model
    print("\n" + "=" * 60)
    print("MODEL EVALUATION")
    print("=" * 60)

    results = []
    best_model = None
    best_score = -np.inf
    best_name = None

    for name, model in models.items():
        print(f"\n--- {name} ---")

        # Create pipeline
        pipeline = Pipeline([
            ('preprocessor', preprocessor),
            ('model', model)
        ])

        # Evaluate
        metrics, y_pred = evaluate_model(pipeline, X_train, X_test, y_train, y_test)

        # Print results
        print(f"  Train RMSE: {metrics['train_rmse']:.3f}")
        print(f"  Test RMSE:  {metrics['test_rmse']:.3f}")
        print(f"  Test MAE:   {metrics['test_mae']:.3f}")
        print(f"  Test R2:    {metrics['test_r2']:.3f}")
        print(f"  CV R2:      {metrics['cv_r2_mean']:.3f} (+/- {metrics['cv_r2_std']:.3f})")

        # Store results
        metrics['model'] = name
        results.append(metrics)

        # Track best model
        if metrics['test_r2'] > best_score:
            best_score = metrics['test_r2']
            best_model = pipeline
            best_name = name

    # Results summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('test_r2', ascending=False)
    print("\nModel Rankings (by Test R2):")
    print(results_df[['model', 'test_rmse', 'test_mae', 'test_r2', 'cv_r2_mean']].to_string(index=False))

    print(f"\n*** Best Model: {best_name} (R2 = {best_score:.3f}) ***")

    # Feature importance
    print("\n" + "=" * 60)
    print("FEATURE IMPORTANCE")
    print("=" * 60)

    # Get feature names after preprocessing
    best_model.fit(X_train, y_train)
    feature_names = (num_features +
                     list(best_model.named_steps['preprocessor']
                          .named_transformers_['cat']
                          .get_feature_names_out(cat_features)))

    importance_df = get_feature_importance(
        best_model.named_steps['model'],
        feature_names
    )

    if importance_df is not None:
        print("\nTop 10 Features:")
        print(importance_df.head(10).to_string(index=False))

    # Save results
    print("\n" + "=" * 60)
    print("SAVING RESULTS")
    print("=" * 60)

    # Save model
    model_path = MODELS_PATH / "fte_model.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump(best_model, f)
    print(f"  Model saved: {model_path}")

    # Save evaluation results
    results_path = RESULTS_PATH / "model_evaluation.csv"
    results_df.to_csv(results_path, index=False)
    print(f"  Evaluation saved: {results_path}")

    # Save feature importance
    if importance_df is not None:
        importance_path = RESULTS_PATH / "feature_importance.csv"
        importance_df.to_csv(importance_path, index=False)
        print(f"  Feature importance saved: {importance_path}")

    # Save predictions for analysis
    predictions_df = pd.DataFrame({
        'actual': y_test,
        'predicted': best_model.predict(X_test),
        'error': y_test - best_model.predict(X_test)
    })
    predictions_path = RESULTS_PATH / "predictions.csv"
    predictions_df.to_csv(predictions_path, index=False)
    print(f"  Predictions saved: {predictions_path}")

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)

    return best_model, results_df


if __name__ == "__main__":
    main()
