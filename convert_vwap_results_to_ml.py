"""
Convert VWAP backtest results to ML training format

Usage:
    python convert_vwap_results_to_ml.py data/vwap_backtest/vwap_backtest_BTCUSDT_1763187622.json

This extracts features from your backtest results and creates a training dataset.
"""

import json
import pandas as pd
import argparse
from pathlib import Path


def convert_backtest_to_ml_format(results_file: str, output_file: str = None):
    """Convert VWAP backtest results to ML training CSV"""

    print(f"📂 Loading backtest results from: {results_file}")

    with open(results_file, 'r') as f:
        data = json.load(f)

    # Extract trades
    trades = data.get('trades', [])

    if not trades:
        print("❌ No trades found in results file")
        return

    print(f"✓ Found {len(trades)} trades")

    # Convert to DataFrame
    df = pd.DataFrame(trades)

    # Ensure required columns exist
    required_cols = ['entry_price', 'exit_price', 'pnl', 'signal_type']
    missing = [col for col in required_cols if col not in df.columns]

    if missing:
        print(f"⚠️ Missing required columns: {missing}")
        print(f"Available columns: {list(df.columns)}")
        return

    # Add is_win column (for ML target)
    df['is_win'] = df['pnl'] > 0

    # Calculate pnl_pct if not present
    if 'pnl_pct' not in df.columns:
        df['pnl_pct'] = (df['pnl'] / (df['entry_price'] * df.get('quantity', 0.01))) * 100

    # Select columns for ML training
    # Keep all feature columns that exist
    feature_cols = [
        # Trade basics
        'timestamp', 'entry_price', 'exit_price', 'signal_type',

        # VWAP features
        'vwap_distance', 'vwap_band_position', 'vwap_slope',
        'distance_to_upper_2std', 'distance_to_lower_2std',
        'vwap_band_width', 'vwap_reversion_score',

        # Zone features
        'zone_strength', 'zone_touches', 'zone_bounces',
        'zone_liquidity_grabs', 'zone_age_minutes',
        'zone_width', 'zone_confidence',
        'distance_to_zone', 'is_support_zone', 'is_resistance_zone',

        # Price features
        'volatility_20', 'price_momentum_5',

        # Temporal features
        'hour', 'day_of_week', 'is_london_session', 'is_ny_session',

        # Outcome (target variable)
        'pnl', 'pnl_pct', 'is_win', 'exit_reason'
    ]

    # Only keep columns that exist
    available_cols = [col for col in feature_cols if col in df.columns]

    print(f"\n📊 Features extracted: {len(available_cols)}")
    print(f"   Available: {available_cols}")

    # Create output DataFrame
    ml_df = df[available_cols].copy()

    # Save to CSV
    if output_file is None:
        output_dir = Path('data')
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / 'vwap_ml_training_data.csv'

    ml_df.to_csv(output_file, index=False)

    print(f"\n✅ ML training data saved to: {output_file}")
    print(f"   Total samples: {len(ml_df)}")
    print(f"   Win rate: {ml_df['is_win'].mean()*100:.2f}%")
    print(f"   Features: {len(available_cols)}")

    # Show feature statistics
    print("\n📈 Feature Statistics:")
    if 'zone_strength' in ml_df.columns:
        print(f"   Avg zone strength: {ml_df['zone_strength'].mean():.2f}")
    if 'vwap_distance' in ml_df.columns:
        print(f"   Avg VWAP distance: {ml_df['vwap_distance'].mean()*100:.3f}%")

    return output_file


def main():
    parser = argparse.ArgumentParser(description='Convert VWAP backtest results to ML format')
    parser.add_argument('input', type=str, help='Input JSON file from backtest')
    parser.add_argument('--output', type=str, default=None, help='Output CSV file (default: data/vwap_ml_training_data.csv)')

    args = parser.parse_args()

    convert_backtest_to_ml_format(args.input, args.output)


if __name__ == '__main__':
    main()
