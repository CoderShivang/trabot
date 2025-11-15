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

    # Ensure minimum required columns exist
    required_cols = ['entry_price', 'exit_price', 'pnl']
    missing = [col for col in required_cols if col not in df.columns]

    if missing:
        print(f"❌ Missing required columns: {missing}")
        print(f"Available columns: {list(df.columns)}")
        return

    print(f"✓ Columns available: {list(df.columns)}")

    # Use 'direction' as signal_type if 'signal_type' doesn't exist
    if 'signal_type' not in df.columns and 'direction' in df.columns:
        df['signal_type'] = df['direction']
        print("✓ Using 'direction' as 'signal_type'")

    # Add is_win column (for ML target)
    df['is_win'] = df['pnl'] > 0

    # Use existing pnl_pct if available, otherwise keep it
    if 'pnl_pct' in df.columns:
        # Already exists, just ensure it's numeric
        df['pnl_pct'] = pd.to_numeric(df['pnl_pct'], errors='coerce')
    else:
        # Calculate from pnl and quantity
        print("⚠️ pnl_pct not found, skipping calculation")

    # Extract features from 'signal' dict if it exists
    if 'signal' in df.columns:
        print("✓ Extracting features from 'signal' field...")
        # Expand signal dict into separate columns
        signal_df = pd.json_normalize(df['signal'])
        # Add signal features to main dataframe
        for col in signal_df.columns:
            if col not in df.columns:
                df[col] = signal_df[col]
        print(f"   Added {len(signal_df.columns)} features from signal")

        # Calculate derived VWAP features from available data
        if 'vwap_band' in df.columns and 'entry_price' in df.columns:
            # VWAP distance (% away from band)
            df['vwap_distance'] = (df['entry_price'] - df['vwap_band']) / df['entry_price']
            # Absolute distance in dollars
            df['vwap_distance_abs'] = abs(df['entry_price'] - df['vwap_band'])
            print("   ✓ Calculated vwap_distance features")

        # Calculate zone features from sr_zone object
        if 'sr_zone.strength' in df.columns:
            df['zone_strength'] = df['sr_zone.strength']
            df['zone_level'] = df['sr_zone.level']
            df['zone_width'] = df['sr_zone.upper'] - df['sr_zone.lower']
            df['distance_to_zone'] = abs(df['entry_price'] - df['sr_zone.level'])
            # Relative position within zone (0 = lower boundary, 1 = upper boundary)
            df['zone_position'] = (df['entry_price'] - df['sr_zone.lower']) / (df['sr_zone.upper'] - df['sr_zone.lower'])
            # Zone type encoding
            df['is_support_zone'] = (df['sr_zone.zone_type'] == 'support').astype(int)
            df['is_resistance_zone'] = (df['sr_zone.zone_type'] == 'resistance').astype(int)
            df['is_both_zone'] = (df['sr_zone.zone_type'] == 'both').astype(int)
            print("   ✓ Calculated zone-based features")

        # Encode boolean htf_confluence
        if 'htf_confluence' in df.columns:
            df['htf_confluence'] = df['htf_confluence'].astype(int)

        # Encode signal_type as categorical features
        if 'signal_type' in df.columns:
            df['is_mean_reversion'] = (df['signal_type'] == 'mean_reversion').astype(int)
            df['is_trend_continuation'] = (df['signal_type'] == 'trend_continuation').astype(int)

        # Encode market_regime as categorical features
        if 'market_regime' in df.columns:
            df['is_bullish_regime'] = (df['market_regime'] == 'bullish_regime').astype(int)
            df['is_bearish_regime'] = (df['market_regime'] == 'bearish_regime').astype(int)
            df['is_neutral_regime'] = (df['market_regime'] == 'neutral_regime').astype(int)

        # Encode short_term_regime as categorical features
        if 'short_term_regime' in df.columns:
            df['is_ranging'] = (df['short_term_regime'] == 'ranging').astype(int)
            df['is_trending_up'] = (df['short_term_regime'] == 'trending_up').astype(int)
            df['is_trending_down'] = (df['short_term_regime'] == 'trending_down').astype(int)

        # Encode price_structure as categorical features
        if 'price_structure' in df.columns:
            df['is_bullish_structure'] = (df['price_structure'] == 'bullish').astype(int)
            df['is_bearish_structure'] = (df['price_structure'] == 'bearish').astype(int)
            df['is_neutral_structure'] = (df['price_structure'] == 'neutral').astype(int)

        # Encode momentum_direction as categorical features
        if 'momentum_direction' in df.columns:
            df['is_bullish_momentum'] = (df['momentum_direction'] == 'bullish').astype(int)
            df['is_bearish_momentum'] = (df['momentum_direction'] == 'bearish').astype(int)
            df['is_neutral_momentum'] = (df['momentum_direction'] == 'neutral').astype(int)

    # Add temporal features from timestamp/entry_time
    timestamp_col = 'entry_time' if 'entry_time' in df.columns else 'timestamp'
    if timestamp_col in df.columns:
        print(f"✓ Extracting temporal features from '{timestamp_col}'...")
        df['datetime'] = pd.to_datetime(df[timestamp_col])
        df['hour'] = df['datetime'].dt.hour
        df['day_of_week'] = df['datetime'].dt.dayofweek
        df['is_london_session'] = ((df['hour'] >= 8) & (df['hour'] < 16)).astype(int)
        df['is_ny_session'] = ((df['hour'] >= 13) & (df['hour'] < 21)).astype(int)
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        print(f"   Added temporal features: hour, day_of_week, session flags")

    # Select columns for ML training
    # Keep all feature columns that exist
    feature_cols = [
        # Trade basics
        'entry_time', 'entry_price', 'exit_price', 'signal_type', 'direction',

        # VWAP features (calculated + from signal field)
        'vwap_value', 'vwap_std', 'vwap_upper_1std', 'vwap_lower_1std',
        'vwap_upper_2std', 'vwap_lower_2std', 'vwap_distance_pct',
        'distance_to_band_dollars', 'vwap_distance', 'vwap_distance_abs', 'vwap_band',
        'vwap_band_position', 'vwap_slope',
        'distance_to_upper_2std', 'distance_to_lower_2std',
        'vwap_band_width', 'vwap_reversion_score',
        'band_position', 'price_vs_vwap',

        # Market pattern features (from signal field)
        'vwap_resistance_rejections', 'vwap_support_bounces',
        'is_bullish_regime', 'is_bearish_regime', 'is_neutral_regime',
        'is_ranging', 'is_trending_up', 'is_trending_down',
        'is_bullish_structure', 'is_bearish_structure', 'is_neutral_structure',

        # Momentum features (from signal field)
        'is_rapid_move', 'momentum_strength',
        'is_bullish_momentum', 'is_bearish_momentum', 'is_neutral_momentum',

        # Local S/R features (from signal field)
        'has_overhead_resistance', 'overhead_resistance_level', 'distance_to_overhead_resistance',
        'has_support_below', 'support_below_level', 'distance_to_support_below',

        # Volatility features (from signal field)
        'volatility_60', 'avg_candle_range_pct',

        # Zone features (calculated + from signal field)
        'zone_strength', 'zone_level', 'zone_width', 'distance_to_zone', 'zone_position',
        'is_support_zone', 'is_resistance_zone', 'is_both_zone',
        'zone_touches', 'zone_bounces',
        'zone_liquidity_grabs', 'zone_age_minutes',
        'zone_confidence', 'closest_zone_strength',

        # Signal features
        'confidence', 'htf_confluence',
        'is_mean_reversion', 'is_trend_continuation',

        # Price features
        'volatility_20', 'price_momentum_5',

        # Temporal features
        'hour', 'day_of_week', 'is_london_session', 'is_ny_session', 'is_weekend',

        # Trade metadata
        'duration_minutes', 'quantity',

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
    print(f"   Wins: {ml_df['is_win'].sum()} | Losses: {(~ml_df['is_win']).sum()}")
    print(f"   Win rate: {ml_df['is_win'].mean()*100:.2f}%")
    print(f"   Features: {len(available_cols)}")

    # Show feature statistics
    print("\n📈 Feature Statistics:")
    feature_count = 0
    if 'zone_strength' in ml_df.columns:
        print(f"   Avg zone strength: {ml_df['zone_strength'].mean():.2f}")
        feature_count += 1
    if 'vwap_distance' in ml_df.columns:
        print(f"   Avg VWAP distance: {ml_df['vwap_distance'].mean()*100:.3f}%")
        feature_count += 1
    if 'pnl_pct' in ml_df.columns:
        print(f"   Avg P&L: {ml_df['pnl_pct'].mean():.3f}%")
        feature_count += 1
    if 'duration_minutes' in ml_df.columns:
        print(f"   Avg trade duration: {ml_df['duration_minutes'].mean():.1f} minutes")
        feature_count += 1

    if feature_count == 0:
        print("   No detailed features found in signal data")
        print("   Basic columns only: entry_price, exit_price, pnl, direction, is_win")

    print("\n💡 Next step: Train the ML model:")
    print(f"   python train_ml_model.py --input {output_file} --output models/vwap_ml_model.pkl")

    return output_file


def main():
    parser = argparse.ArgumentParser(description='Convert VWAP backtest results to ML format')
    parser.add_argument('input', type=str, help='Input JSON file from backtest')
    parser.add_argument('--output', type=str, default=None, help='Output CSV file (default: data/vwap_ml_training_data.csv)')

    args = parser.parse_args()

    convert_backtest_to_ml_format(args.input, args.output)


if __name__ == '__main__':
    main()
