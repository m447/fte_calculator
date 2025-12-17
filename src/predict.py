"""
FTE Prediction Script
=====================
Predict optimal FTE for pharmacies using the trained model.

Usage:
    # Predict for a single pharmacy
    python src/predict.py --bloky 50000 --trzby 1000000 --typ "B - shopping" --podiel_rx 0.5

    # Predict for all pharmacies in dataset
    python src/predict.py --all
"""

import argparse
import pickle
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "fte_model.pkl"
DATA_PATH = PROJECT_ROOT / "data" / "ml_ready_v3.csv"


def load_model():
    """Load the trained model."""
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    return model


def get_default_values():
    """Get median values from training data for missing features."""
    df = pd.read_csv(DATA_PATH)
    defaults = df.median(numeric_only=True).to_dict()
    defaults['typ'] = 'B - shopping'  # Most common type
    return defaults


def predict_single(model, **kwargs):
    """
    Predict FTE for a single pharmacy.

    Required arguments:
        bloky: Annual transaction count
        trzby: Annual revenue (EUR)
        typ: Store type (A - shopping premium, B - shopping, C - street +, D - street, E - poliklinika)
        podiel_rx: Prescription ratio (0-1)

    Optional arguments (defaults to median):
        produktivita, bloky_range, revenue_per_transaction, etc.
    """
    defaults = get_default_values()

    # Build feature dict with defaults
    features = defaults.copy()
    features.update(kwargs)

    # Calculate derived features if not provided
    if 'revenue_per_transaction' not in kwargs and 'trzby' in kwargs and 'bloky' in kwargs:
        features['revenue_per_transaction'] = kwargs['trzby'] / kwargs['bloky']

    if 'bloky_range' not in kwargs and 'bloky' in kwargs:
        features['bloky_range'] = kwargs['bloky'] * 0.3  # Estimate 30% seasonal range

    # Binary flags from typ
    features['is_shopping'] = 1 if features['typ'] in ['A - shopping premium', 'B - shopping'] else 0
    features['is_poliklinika'] = 1 if features['typ'] == 'E - poliklinika' else 0
    features['is_street'] = 1 if features['typ'] in ['C - street +', 'D - street'] else 0
    features['high_rx_complexity'] = 1 if features.get('podiel_rx', 0.5) > 0.7 else 0

    # Create DataFrame
    feature_cols = [
        'typ', 'avg_base_salary', 'bloky', 'bloky_cv', 'bloky_range', 'bloky_trend',
        'fte_zastup', 'high_rx_complexity', 'hourly_rate', 'is_poliklinika',
        'is_shopping', 'is_street', 'kpi_mean', 'kpi_std', 'pharmacist_wage_premium',
        'podiel_rx', 'produktivita', 'revenue_per_transaction', 'seasonal_peak_factor',
        'trzby', 'trzby_cv'
    ]

    X = pd.DataFrame([{col: features.get(col, defaults.get(col, 0)) for col in feature_cols}])

    # Predict
    prediction = model.predict(X)[0]

    return prediction


def predict_all(model):
    """Predict FTE for all pharmacies in dataset and compare with actual."""
    df = pd.read_csv(DATA_PATH)

    # Get feature columns
    feature_cols = [
        'typ', 'avg_base_salary', 'bloky', 'bloky_cv', 'bloky_range', 'bloky_trend',
        'fte_zastup', 'high_rx_complexity', 'hourly_rate', 'is_poliklinika',
        'is_shopping', 'is_street', 'kpi_mean', 'kpi_std', 'pharmacist_wage_premium',
        'podiel_rx', 'produktivita', 'revenue_per_transaction', 'seasonal_peak_factor',
        'trzby', 'trzby_cv'
    ]

    # Drop rows with missing values
    df_clean = df.dropna(subset=feature_cols + ['fte'])

    X = df_clean[feature_cols]
    y_actual = df_clean['fte']

    # Predict
    y_pred = model.predict(X)

    # Results
    results = df_clean[['id', 'mesto', 'typ', 'fte']].copy()
    results['predicted_fte'] = y_pred
    results['difference'] = results['fte'] - results['predicted_fte']
    results['abs_error'] = np.abs(results['difference'])

    return results


def main():
    parser = argparse.ArgumentParser(description='Predict FTE for pharmacies')
    parser.add_argument('--all', action='store_true', help='Predict for all pharmacies')
    parser.add_argument('--bloky', type=float, help='Annual transactions')
    parser.add_argument('--trzby', type=float, help='Annual revenue (EUR)')
    parser.add_argument('--typ', type=str, default='B - shopping',
                        choices=['A - shopping premium', 'B - shopping', 'C - street +',
                                 'D - street', 'E - poliklinika'],
                        help='Store type')
    parser.add_argument('--podiel_rx', type=float, default=0.5, help='Prescription ratio (0-1)')

    args = parser.parse_args()

    # Load model
    print("Loading model...")
    model = load_model()

    if args.all:
        # Predict for all
        print("\nPredicting for all pharmacies...\n")
        results = predict_all(model)

        print(f"{'ID':<6} {'City':<30} {'Type':<20} {'Actual':<8} {'Predicted':<10} {'Diff':<8}")
        print("-" * 90)
        for _, row in results.head(20).iterrows():
            print(f"{row['id']:<6} {row['mesto'][:28]:<30} {row['typ']:<20} "
                  f"{row['fte']:<8.2f} {row['predicted_fte']:<10.2f} {row['difference']:<8.2f}")

        print(f"\n... showing 20 of {len(results)} pharmacies")
        print(f"\nOverall Statistics:")
        print(f"  MAE:  {results['abs_error'].mean():.3f} FTE")
        print(f"  RMSE: {np.sqrt((results['difference']**2).mean()):.3f} FTE")

        # Save full results
        output_path = PROJECT_ROOT / "results" / "all_predictions.csv"
        results.to_csv(output_path, index=False)
        print(f"\nFull results saved to: {output_path}")

    else:
        # Single prediction
        if args.bloky is None or args.trzby is None:
            print("Error: --bloky and --trzby are required for single prediction")
            print("Example: python src/predict.py --bloky 50000 --trzby 1000000 --typ 'B - shopping'")
            return

        prediction = predict_single(
            model,
            bloky=args.bloky,
            trzby=args.trzby,
            typ=args.typ,
            podiel_rx=args.podiel_rx
        )

        print(f"\n{'='*50}")
        print("FTE PREDICTION")
        print(f"{'='*50}")
        print(f"\nInput:")
        print(f"  Transactions (bloky): {args.bloky:,.0f}")
        print(f"  Revenue (trzby):      EUR {args.trzby:,.0f}")
        print(f"  Store type:           {args.typ}")
        print(f"  RX ratio:             {args.podiel_rx:.1%}")
        print(f"\nPredicted FTE: {prediction:.2f}")
        print(f"{'='*50}")


if __name__ == "__main__":
    main()
