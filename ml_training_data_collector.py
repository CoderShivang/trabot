"""
ML Training Data Collector for VWAP Strategy

This module runs backtests and collects comprehensive feature data
for each trade to train ML models.

Usage:
    python ml_training_data_collector.py --days 30 --symbol BTCUSDT

Output:
    - trades_with_features.csv (training data)
    - feature_statistics.json (feature analysis)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import asyncio
from dataclasses import dataclass, asdict

# Import VWAP strategy components
import sys
sys.path.append('src')
from strategy.vwap_strategy import VWAPStrategy, VWAPBands, TradeSignal
from strategy.enhanced_sr_detector import EnhancedSRDetector, EnhancedSRZone
from data.binance_client import BinanceClient


@dataclass
class TradeWithFeatures:
    """Complete trade record with all features for ML training"""

    # === TRADE METADATA ===
    trade_id: int
    timestamp: int
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    signal_type: str  # 'mean_reversion' or 'trend_continuation'

    # === ENTRY/EXIT DATA ===
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    exit_reason: str  # 'tp', 'sl', 'time_exit'

    # === TRADE OUTCOME (TARGET VARIABLE) ===
    pnl: float
    pnl_percent: float
    win: int  # 1 = win, 0 = loss
    duration_minutes: int

    # === VWAP FEATURES ===
    vwap_value: float
    vwap_std: float
    vwap_upper_1std: float
    vwap_lower_1std: float
    vwap_upper_2std: float
    vwap_lower_2std: float

    # VWAP position features
    vwap_distance: float  # (price - vwap) / vwap
    vwap_distance_abs: float
    vwap_band_position: float  # 0-1 scale
    near_vwap: int
    near_upper_1std: int
    near_lower_1std: int
    near_upper_2std: int
    near_lower_2std: int
    beyond_upper_2std: int
    beyond_lower_2std: int

    # VWAP dynamics
    vwap_slope: float
    vwap_band_width: float

    # === S/R ZONE FEATURES ===
    has_sr_zone: int  # Boolean
    zone_level: float
    zone_type: str  # 'support', 'resistance', 'both'
    zone_strength: float  # 0-100
    zone_touches: int
    zone_bounces: int
    zone_breakouts: int
    zone_liquidity_grabs: int
    zone_invalidated: int
    zone_age_minutes: float
    distance_to_zone: float
    zone_last_interaction: str  # 'bounce', 'breakout', 'liquidity_grab', 'none'

    # === HTF CONFLUENCE ===
    htf_confluence: int  # Boolean
    has_5m_zone: int
    has_15m_zone: int
    has_daily_zone: int

    # === MARKET REGIME ===
    market_regime: str  # 'ranging', 'trending_up', 'trending_down'
    regime_100_sma: str  # 'bullish_regime', 'bearish_regime', 'neutral_regime'

    # === PRICE ACTION ===
    price_structure: str  # 'bullish', 'bearish', 'neutral'
    rapid_momentum: int  # Boolean
    momentum_direction: str  # 'bullish', 'bearish', 'neutral'
    overhead_resistance: int  # Boolean
    support_below: int  # Boolean

    # === VWAP REJECTION PATTERNS ===
    vwap_resistance_rejections: int
    vwap_support_bounces: int
    vwap_is_support: int
    vwap_is_resistance: int

    # === TEMPORAL FEATURES ===
    hour: int
    day_of_week: int
    is_asian_session: int
    is_london_session: int
    is_ny_session: int
    is_weekend: int

    # === STRATEGY CONFIDENCE ===
    confidence_score: float  # Original strategy confidence (0-100)

    # === FEATURE INTERACTIONS (calculated) ===
    vwap_zone_confluence: float  # vwap_distance * zone_strength
    regime_band_interaction: float  # regime score * band_position


class MLDataCollector:
    """Collects training data from VWAP strategy backtests"""

    def __init__(self, symbol: str = 'BTCUSDT'):
        self.symbol = symbol
        self.strategy = VWAPStrategy()
        self.client = BinanceClient()
        self.trades_with_features = []
        self.trade_counter = 0

    async def collect_training_data(self,
                                   start_date: str,
                                   end_date: str,
                                   timeframe: str = '1m') -> pd.DataFrame:
        """
        Run backtest and collect all trade features

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            timeframe: Candle timeframe (1m, 5m, etc.)

        Returns:
            DataFrame with all trades and their features
        """
        print(f"\n{'='*80}")
        print(f"ML TRAINING DATA COLLECTION")
        print(f"{'='*80}")
        print(f"Symbol: {self.symbol}")
        print(f"Period: {start_date} to {end_date}")
        print(f"Timeframe: {timeframe}")
        print(f"{'='*80}\n")

        # Fetch historical data
        print("[1/5] Fetching historical data...")
        df_1m = await self._fetch_klines(timeframe, start_date, end_date)
        df_5m = await self._fetch_klines('5m', start_date, end_date)
        df_15m = await self._fetch_klines('15m', start_date, end_date)
        df_1d = await self._fetch_klines('1d', start_date, end_date)

        print(f"      Loaded {len(df_1m)} 1m candles")
        print(f"      Loaded {len(df_5m)} 5m candles")
        print(f"      Loaded {len(df_15m)} 15m candles")
        print(f"      Loaded {len(df_1d)} 1d candles")

        # Run backtest with feature logging
        print("\n[2/5] Running backtest with feature logging...")
        await self._run_backtest_with_logging(df_1m, df_5m, df_15m, df_1d)

        print(f"\n[3/5] Collected {len(self.trades_with_features)} trades")

        # Convert to DataFrame
        print("\n[4/5] Converting to DataFrame...")
        df_trades = pd.DataFrame([asdict(t) for t in self.trades_with_features])

        # Calculate additional features
        print("\n[5/5] Calculating feature interactions...")
        df_trades = self._calculate_feature_interactions(df_trades)

        # Print statistics
        self._print_statistics(df_trades)

        return df_trades

    async def _fetch_klines(self, interval: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch historical klines from Binance"""
        # Convert dates to timestamps
        start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
        end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)

        # Fetch klines
        klines = await self.client.get_klines(
            symbol=self.symbol,
            interval=interval,
            limit=1500,  # Max per request
            start_time=start_ts,
            end_time=end_ts
        )

        # Convert to DataFrame
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'tb_base', 'tb_quote', 'ignore'
        ])

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('timestamp', inplace=True)

        return df

    async def _run_backtest_with_logging(self,
                                        df_1m: pd.DataFrame,
                                        df_5m: pd.DataFrame,
                                        df_15m: pd.DataFrame,
                                        df_1d: pd.DataFrame):
        """
        Run backtest and log features for each trade

        This is the core of the data collection process
        """
        # Simulate walking through time
        for i in range(100, len(df_1m) - 100):  # Leave buffer for indicators
            current_time = df_1m.index[i]
            current_price = df_1m.iloc[i]['close']

            # Get data up to current point (simulate real-time)
            df_1m_window = df_1m.iloc[:i+1].copy()
            df_5m_window = df_5m[df_5m.index <= current_time].copy()
            df_15m_window = df_15m[df_15m.index <= current_time].copy()
            df_1d_window = df_1d[df_1d.index <= current_time].copy()

            # Check for signals
            signals = self.strategy.analyze(
                df=df_1m_window,
                current_price=current_price,
                df_5m=df_5m_window,
                df_15m=df_15m_window,
                df_1d=df_1d_window
            )

            # Process signals
            for signal in signals:
                # Extract features at entry
                features = self._extract_features_at_entry(
                    signal=signal,
                    df_1m=df_1m_window,
                    current_time=current_time,
                    current_price=current_price
                )

                # Simulate trade execution to get outcome
                outcome = self._simulate_trade_outcome(
                    signal=signal,
                    df_future=df_1m.iloc[i:],  # Future data for outcome
                    entry_idx=i
                )

                # Combine features + outcome
                trade_record = self._create_trade_record(
                    signal=signal,
                    features=features,
                    outcome=outcome
                )

                self.trades_with_features.append(trade_record)
                self.trade_counter += 1

                # Progress indicator
                if self.trade_counter % 10 == 0:
                    print(f"      Collected {self.trade_counter} trades...")

    def _extract_features_at_entry(self,
                                   signal: TradeSignal,
                                   df_1m: pd.DataFrame,
                                   current_time,
                                   current_price: float) -> Dict:
        """
        Extract ALL features at the moment of trade entry

        This is CRITICAL - we capture the exact market state when signal fired
        """
        features = {}

        # === VWAP FEATURES ===
        # (VWAP bands are stored in signal.vwap_band)
        vwap_value = signal.vwap_band  # This is the VWAP level

        # Calculate VWAP stats from recent data
        recent_df = df_1m.tail(200)
        tp = (recent_df['high'] + recent_df['low'] + recent_df['close']) / 3
        vwap_calc = (tp * recent_df['volume']).sum() / recent_df['volume'].sum()

        # Volume-weighted std dev (correct calculation)
        squared_diff = (tp - vwap_calc) ** 2
        vwap_variance = (squared_diff * recent_df['volume']).sum() / recent_df['volume'].sum()
        vwap_std = float(np.sqrt(vwap_variance))

        features['vwap_value'] = vwap_calc
        features['vwap_std'] = vwap_std
        features['vwap_upper_1std'] = vwap_calc + vwap_std
        features['vwap_lower_1std'] = vwap_calc - vwap_std
        features['vwap_upper_2std'] = vwap_calc + (vwap_std * 2)
        features['vwap_lower_2std'] = vwap_calc - (vwap_std * 2)

        # VWAP position features
        features['vwap_distance'] = (current_price - vwap_calc) / vwap_calc
        features['vwap_distance_abs'] = abs(features['vwap_distance'])

        band_range = features['vwap_upper_2std'] - features['vwap_lower_2std']
        features['vwap_band_position'] = (current_price - features['vwap_lower_2std']) / band_range

        # Near which band?
        features['near_vwap'] = int(abs(current_price - vwap_calc) / vwap_calc < 0.002)
        features['near_upper_1std'] = int(abs(current_price - features['vwap_upper_1std']) / vwap_calc < 0.003)
        features['near_lower_1std'] = int(abs(current_price - features['vwap_lower_1std']) / vwap_calc < 0.003)
        features['near_upper_2std'] = int(abs(current_price - features['vwap_upper_2std']) / vwap_calc < 0.005)
        features['near_lower_2std'] = int(abs(current_price - features['vwap_lower_2std']) / vwap_calc < 0.005)

        features['beyond_upper_2std'] = int(current_price > features['vwap_upper_2std'])
        features['beyond_lower_2std'] = int(current_price < features['vwap_lower_2std'])

        # VWAP slope
        vwap_series = recent_df['close'].rolling(20).mean()  # Proxy for VWAP
        features['vwap_slope'] = float(vwap_series.iloc[-1] - vwap_series.iloc[-20]) / vwap_series.iloc[-20]

        features['vwap_band_width'] = (features['vwap_upper_1std'] - features['vwap_lower_1std']) / vwap_calc

        # === S/R ZONE FEATURES ===
        if signal.sr_zone:
            zone = signal.sr_zone
            features['has_sr_zone'] = 1
            features['zone_level'] = zone.level
            features['zone_type'] = zone.zone_type
            features['zone_strength'] = zone.strength
            features['zone_touches'] = zone.touches
            features['zone_bounces'] = zone.bounces
            features['zone_breakouts'] = zone.breakouts
            features['zone_liquidity_grabs'] = zone.liquidity_grabs
            features['zone_invalidated'] = int(zone.invalidated)

            # Zone age
            current_time_ms = int(current_time.timestamp() * 1000)
            features['zone_age_minutes'] = (current_time_ms - zone.created_at) / (1000 * 60)

            features['distance_to_zone'] = abs(current_price - zone.level) / current_price
            features['zone_last_interaction'] = zone.last_interaction
        else:
            features['has_sr_zone'] = 0
            features['zone_level'] = 0.0
            features['zone_type'] = 'none'
            features['zone_strength'] = 0.0
            features['zone_touches'] = 0
            features['zone_bounces'] = 0
            features['zone_breakouts'] = 0
            features['zone_liquidity_grabs'] = 0
            features['zone_invalidated'] = 0
            features['zone_age_minutes'] = 0.0
            features['distance_to_zone'] = 1.0
            features['zone_last_interaction'] = 'none'

        # HTF confluence
        features['htf_confluence'] = int(signal.htf_confluence)
        features['has_5m_zone'] = 0  # Would need to check 5m zones
        features['has_15m_zone'] = 0  # Would need to check 15m zones
        features['has_daily_zone'] = 0  # Would need to check daily zones

        # === MARKET REGIME (simplified - would use actual regime detection) ===
        features['market_regime'] = 'ranging'  # Placeholder
        features['regime_100_sma'] = 'neutral_regime'  # Placeholder

        # === PRICE ACTION (simplified) ===
        features['price_structure'] = 'neutral'
        features['rapid_momentum'] = 0
        features['momentum_direction'] = 'neutral'
        features['overhead_resistance'] = 0
        features['support_below'] = 0

        # === VWAP REJECTIONS (simplified - would calculate from recent candles) ===
        features['vwap_resistance_rejections'] = 0
        features['vwap_support_bounces'] = 0
        features['vwap_is_support'] = 0
        features['vwap_is_resistance'] = 0

        # === TEMPORAL FEATURES ===
        features['hour'] = current_time.hour
        features['day_of_week'] = current_time.dayofweek
        features['is_asian_session'] = int(0 <= current_time.hour < 8)
        features['is_london_session'] = int(8 <= current_time.hour < 16)
        features['is_ny_session'] = int(13 <= current_time.hour < 21)
        features['is_weekend'] = int(current_time.dayofweek >= 5)

        # === CONFIDENCE ===
        features['confidence_score'] = signal.confidence

        return features

    def _simulate_trade_outcome(self,
                                signal: TradeSignal,
                                df_future: pd.DataFrame,
                                entry_idx: int) -> Dict:
        """
        Simulate trade execution and determine outcome

        Args:
            signal: Trade signal with entry/stop/tp
            df_future: Future price data (from entry onwards)
            entry_idx: Index of entry in main dataframe

        Returns:
            Dictionary with trade outcome
        """
        entry_price = signal.entry_price
        stop_loss = signal.stop_loss
        take_profit = signal.take_profit
        direction = signal.direction

        # Simulate trade execution
        for i, (timestamp, row) in enumerate(df_future.iterrows()):
            # Check stop loss
            if direction == 'LONG':
                if row['low'] <= stop_loss:
                    return {
                        'exit_price': stop_loss,
                        'exit_reason': 'sl',
                        'pnl': stop_loss - entry_price,
                        'pnl_percent': (stop_loss - entry_price) / entry_price,
                        'win': 0,
                        'duration_minutes': i
                    }
                # Check take profit
                elif row['high'] >= take_profit:
                    return {
                        'exit_price': take_profit,
                        'exit_reason': 'tp',
                        'pnl': take_profit - entry_price,
                        'pnl_percent': (take_profit - entry_price) / entry_price,
                        'win': 1,
                        'duration_minutes': i
                    }

            else:  # SHORT
                if row['high'] >= stop_loss:
                    return {
                        'exit_price': stop_loss,
                        'exit_reason': 'sl',
                        'pnl': entry_price - stop_loss,
                        'pnl_percent': (entry_price - stop_loss) / entry_price,
                        'win': 0,
                        'duration_minutes': i
                    }
                elif row['low'] <= take_profit:
                    return {
                        'exit_price': take_profit,
                        'exit_reason': 'tp',
                        'pnl': entry_price - take_profit,
                        'pnl_percent': (entry_price - take_profit) / entry_price,
                        'win': 1,
                        'duration_minutes': i
                    }

            # Time exit after 4 hours (240 minutes)
            if i >= 240:
                exit_price = row['close']
                if direction == 'LONG':
                    pnl = exit_price - entry_price
                else:
                    pnl = entry_price - exit_price

                return {
                    'exit_price': exit_price,
                    'exit_reason': 'time_exit',
                    'pnl': pnl,
                    'pnl_percent': pnl / entry_price,
                    'win': int(pnl > 0),
                    'duration_minutes': 240
                }

        # Fallback: exit at last available price
        exit_price = df_future.iloc[-1]['close']
        if direction == 'LONG':
            pnl = exit_price - entry_price
        else:
            pnl = entry_price - exit_price

        return {
            'exit_price': exit_price,
            'exit_reason': 'end_of_data',
            'pnl': pnl,
            'pnl_percent': pnl / entry_price,
            'win': int(pnl > 0),
            'duration_minutes': len(df_future)
        }

    def _create_trade_record(self,
                            signal: TradeSignal,
                            features: Dict,
                            outcome: Dict) -> TradeWithFeatures:
        """Combine signal, features, and outcome into complete trade record"""

        return TradeWithFeatures(
            # Metadata
            trade_id=self.trade_counter,
            timestamp=int(datetime.now().timestamp() * 1000),  # Placeholder
            symbol=self.symbol,
            direction=signal.direction,
            signal_type=signal.signal_type,

            # Entry/Exit
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            exit_price=outcome['exit_price'],
            exit_reason=outcome['exit_reason'],

            # Outcome
            pnl=outcome['pnl'],
            pnl_percent=outcome['pnl_percent'],
            win=outcome['win'],
            duration_minutes=outcome['duration_minutes'],

            # VWAP features
            vwap_value=features['vwap_value'],
            vwap_std=features['vwap_std'],
            vwap_upper_1std=features['vwap_upper_1std'],
            vwap_lower_1std=features['vwap_lower_1std'],
            vwap_upper_2std=features['vwap_upper_2std'],
            vwap_lower_2std=features['vwap_lower_2std'],
            vwap_distance=features['vwap_distance'],
            vwap_distance_abs=features['vwap_distance_abs'],
            vwap_band_position=features['vwap_band_position'],
            near_vwap=features['near_vwap'],
            near_upper_1std=features['near_upper_1std'],
            near_lower_1std=features['near_lower_1std'],
            near_upper_2std=features['near_upper_2std'],
            near_lower_2std=features['near_lower_2std'],
            beyond_upper_2std=features['beyond_upper_2std'],
            beyond_lower_2std=features['beyond_lower_2std'],
            vwap_slope=features['vwap_slope'],
            vwap_band_width=features['vwap_band_width'],

            # S/R zone features
            has_sr_zone=features['has_sr_zone'],
            zone_level=features['zone_level'],
            zone_type=features['zone_type'],
            zone_strength=features['zone_strength'],
            zone_touches=features['zone_touches'],
            zone_bounces=features['zone_bounces'],
            zone_breakouts=features['zone_breakouts'],
            zone_liquidity_grabs=features['zone_liquidity_grabs'],
            zone_invalidated=features['zone_invalidated'],
            zone_age_minutes=features['zone_age_minutes'],
            distance_to_zone=features['distance_to_zone'],
            zone_last_interaction=features['zone_last_interaction'],

            # HTF confluence
            htf_confluence=features['htf_confluence'],
            has_5m_zone=features['has_5m_zone'],
            has_15m_zone=features['has_15m_zone'],
            has_daily_zone=features['has_daily_zone'],

            # Market regime
            market_regime=features['market_regime'],
            regime_100_sma=features['regime_100_sma'],

            # Price action
            price_structure=features['price_structure'],
            rapid_momentum=features['rapid_momentum'],
            momentum_direction=features['momentum_direction'],
            overhead_resistance=features['overhead_resistance'],
            support_below=features['support_below'],

            # VWAP rejections
            vwap_resistance_rejections=features['vwap_resistance_rejections'],
            vwap_support_bounces=features['vwap_support_bounces'],
            vwap_is_support=features['vwap_is_support'],
            vwap_is_resistance=features['vwap_is_resistance'],

            # Temporal
            hour=features['hour'],
            day_of_week=features['day_of_week'],
            is_asian_session=features['is_asian_session'],
            is_london_session=features['is_london_session'],
            is_ny_session=features['is_ny_session'],
            is_weekend=features['is_weekend'],

            # Confidence
            confidence_score=features['confidence_score'],

            # Feature interactions (will be calculated)
            vwap_zone_confluence=0.0,
            regime_band_interaction=0.0
        )

    def _calculate_feature_interactions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate feature interaction terms"""

        df['vwap_zone_confluence'] = df['vwap_distance_abs'] * df['zone_strength']
        df['regime_band_interaction'] = df['vwap_band_position']  # Placeholder

        return df

    def _print_statistics(self, df: pd.DataFrame):
        """Print statistics about collected data"""

        print(f"\n{'='*80}")
        print(f"TRAINING DATA STATISTICS")
        print(f"{'='*80}")

        print(f"\nTrade Distribution:")
        print(f"  Total trades: {len(df)}")
        print(f"  Wins: {df['win'].sum()} ({df['win'].mean():.1%})")
        print(f"  Losses: {(~df['win'].astype(bool)).sum()} ({(1 - df['win'].mean()):.1%})")

        print(f"\nDirection:")
        print(f"  LONG: {(df['direction'] == 'LONG').sum()}")
        print(f"  SHORT: {(df['direction'] == 'SHORT').sum()}")

        print(f"\nSignal Type:")
        print(f"  Mean Reversion: {(df['signal_type'] == 'mean_reversion').sum()}")
        print(f"  Trend Continuation: {(df['signal_type'] == 'trend_continuation').sum()}")

        print(f"\nP&L Statistics:")
        print(f"  Avg P&L: ${df['pnl'].mean():.2f}")
        print(f"  Avg Win: ${df[df['win'] == 1]['pnl'].mean():.2f}")
        print(f"  Avg Loss: ${df[df['win'] == 0]['pnl'].mean():.2f}")
        print(f"  Max Win: ${df['pnl'].max():.2f}")
        print(f"  Max Loss: ${df['pnl'].min():.2f}")

        print(f"\nFeature Statistics:")
        print(f"  Trades with S/R zone: {df['has_sr_zone'].sum()} ({df['has_sr_zone'].mean():.1%})")
        print(f"  Trades with HTF confluence: {df['htf_confluence'].sum()} ({df['htf_confluence'].mean():.1%})")
        print(f"  Avg zone strength: {df[df['has_sr_zone'] == 1]['zone_strength'].mean():.1f}")
        print(f"  Avg confidence score: {df['confidence_score'].mean():.1f}")

        print(f"\n{'='*80}\n")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Collect ML training data from VWAP backtest')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading symbol')
    parser.add_argument('--days', type=int, default=30, help='Number of days to backtest')
    parser.add_argument('--output', type=str, default='trades_with_features.csv', help='Output CSV file')

    args = parser.parse_args()

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)

    # Collect data
    collector = MLDataCollector(symbol=args.symbol)
    df_trades = await collector.collect_training_data(
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d')
    )

    # Save to CSV
    print(f"Saving training data to {args.output}...")
    df_trades.to_csv(args.output, index=False)
    print(f"✓ Saved {len(df_trades)} trades")

    # Save feature statistics
    stats_file = args.output.replace('.csv', '_stats.json')
    stats = {
        'total_trades': len(df_trades),
        'win_rate': float(df_trades['win'].mean()),
        'avg_pnl': float(df_trades['pnl'].mean()),
        'avg_confidence': float(df_trades['confidence_score'].mean()),
        'feature_count': len(df_trades.columns),
        'date_range': {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d'),
            'days': args.days
        }
    }

    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)

    print(f"✓ Saved statistics to {stats_file}")
    print(f"\n✓ Training data collection complete!")
    print(f"\nNext steps:")
    print(f"  1. Review {args.output} to verify features")
    print(f"  2. Train ML model using train_ml_model.py")
    print(f"  3. Run backtest with ML filtering")


if __name__ == '__main__':
    asyncio.run(main())
