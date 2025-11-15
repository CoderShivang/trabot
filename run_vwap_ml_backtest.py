"""
VWAP Strategy Backtest with ML Filtering and Walk-Forward Analysis

Features:
- Integrates 3 ML models (RF, GB, XGB) for trade filtering
- Walk-forward analysis (train on past data, test on future)
- Configurable parameters for different timeframes
- Comprehensive performance metrics
- Aims for 60%+ win rate with ML filtering

Usage:
    python run_vwap_ml_backtest.py --symbol BTCUSDT --days 30 --timeframe 1m
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.backtesting.vwap_backtest_engine import VWAPBacktestEngine
from src.learning.vwap_ml_optimizer import VWAPMLOptimizer
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class VWAPMLBacktest:
    """
    VWAP backtest with integrated ML filtering using walk-forward analysis
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        timeframe: str = "1m",
        days: int = 30,
        initial_capital: float = 100.0,
        leverage: int = 20,
        risk_per_trade: float = 0.02,
        walk_forward_window_days: int = 7,  # Train on 7 days, test on next period
        retrain_interval_days: int = 3,  # Retrain every 3 days
        min_win_probability: float = 0.60,  # 60% minimum win probability
        relaxed_params: dict = None
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.days = days
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.risk_per_trade = risk_per_trade
        self.walk_forward_window_days = walk_forward_window_days
        self.retrain_interval_days = retrain_interval_days
        self.min_win_probability = min_win_probability
        self.relaxed_params = relaxed_params or {}

        # Initialize ML optimizer
        self.ml_optimizer = VWAPMLOptimizer(min_win_probability=min_win_probability)

        # Initialize backtest engine
        self.engine = VWAPBacktestEngine(
            symbol=symbol,
            timeframe=timeframe,
            initial_capital=initial_capital,
            leverage=leverage,
            risk_per_trade=risk_per_trade
        )

        # Apply relaxed parameters if provided
        if self.relaxed_params:
            self._apply_relaxed_parameters()

        # Storage for walk-forward results
        self.walk_forward_results = []
        self.all_signals = []  # For ML training
        self.all_outcomes = []  # For ML training

    def _apply_relaxed_parameters(self):
        """Apply relaxed parameters for higher timeframes"""
        logger.info(f"[ML-BACKTEST] Applying relaxed parameters: {self.relaxed_params}")

        # Update VWAP strategy parameters through engine
        for key, value in self.relaxed_params.items():
            if hasattr(self.engine, key):
                setattr(self.engine, key, value)
                logger.info(f"  Set {key} = {value}")

    async def run_walk_forward_backtest(self):
        """
        Run backtest with walk-forward analysis to prevent look-ahead bias.

        Process:
        1. Split data into training and testing windows
        2. Train ML models on training window
        3. Test on next period with ML filtering
        4. Retrain periodically
        5. Aggregate results
        """
        logger.info("="*80)
        logger.info(f"VWAP ML BACKTEST - {self.symbol} ({self.timeframe})")
        logger.info("="*80)
        logger.info(f"Period: {self.days} days")
        logger.info(f"Walk-Forward Window: {self.walk_forward_window_days} days")
        logger.info(f"Retrain Interval: {self.retrain_interval_days} days")
        logger.info(f"Min Win Probability: {self.min_win_probability:.1%}")
        logger.info(f"Initial Capital: ${self.initial_capital}")
        logger.info(f"Leverage: {self.leverage}x")
        logger.info("="*80)

        # Calculate date ranges
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.days)

        # Phase 1: Initial training period (collect data without trading)
        logger.info("\n[PHASE 1] Initial training period (no trading)...")
        training_end = start_date + timedelta(days=self.walk_forward_window_days)

        training_results = await self._run_period(
            start_date,
            training_end,
            train_mode=True
        )

        # Train initial ML models
        if len(self.all_signals) >= 30:  # Minimum 30 signals for training
            logger.info(f"\n[ML-TRAIN] Training initial models on {len(self.all_signals)} signals...")
            metrics = self.ml_optimizer.train_models(self.all_signals, self.all_outcomes)
            logger.info(f"[ML-TRAIN] Initial training complete")
        else:
            logger.warning(f"[ML-TRAIN] Insufficient signals ({len(self.all_signals)}/30), skipping ML")

        # Phase 2: Walk-forward testing with ML filtering
        logger.info("\n[PHASE 2] Walk-forward testing with ML filtering...")

        current_date = training_end
        retrain_counter = 0
        test_period_num = 1

        while current_date < end_date:
            # Calculate test period
            test_start = current_date
            test_end = min(current_date + timedelta(days=self.retrain_interval_days), end_date)

            logger.info(f"\n[TEST PERIOD {test_period_num}] {test_start.strftime('%Y-%m-%d')} to {test_end.strftime('%Y-%m-%d')}")

            # Run backtest with ML filtering
            period_results = await self._run_period(
                test_start,
                test_end,
                train_mode=False,
                use_ml=True
            )

            self.walk_forward_results.append({
                'period': test_period_num,
                'start': test_start,
                'end': test_end,
                'results': period_results
            })

            # Retrain ML models if we have enough new data
            if len(self.all_signals) >= 50 and retrain_counter >= self.retrain_interval_days:
                logger.info(f"\n[ML-RETRAIN] Retraining models on {len(self.all_signals)} total signals...")
                metrics = self.ml_optimizer.train_models(self.all_signals, self.all_outcomes)
                retrain_counter = 0

            current_date = test_end
            retrain_counter += self.retrain_interval_days
            test_period_num += 1

        # Aggregate and report results
        final_results = self._aggregate_results()
        self._save_results(final_results)

        return final_results

    async def _run_period(
        self,
        start_date: datetime,
        end_date: datetime,
        train_mode: bool = False,
        use_ml: bool = False
    ):
        """
        Run backtest for a specific period.

        Args:
            start_date: Period start
            end_date: Period end
            train_mode: If True, collect signals for training only (no trading)
            use_ml: If True, filter trades using ML

        Returns:
            Period results dictionary
        """
        # Convert to timestamps
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        # Initialize new engine instance for this period
        period_engine = VWAPBacktestEngine(
            symbol=self.symbol,
            timeframe=self.timeframe,
            initial_capital=self.initial_capital,
            leverage=self.leverage,
            risk_per_trade=self.risk_per_trade
        )

        # Apply relaxed parameters
        if self.relaxed_params:
            for key, value in self.relaxed_params.items():
                if hasattr(period_engine, key):
                    setattr(period_engine, key, value)

        # Run the backtest
        results = await period_engine.run(
            start_time=start_ts,
            end_time=end_ts,
            ml_optimizer=self.ml_optimizer if use_ml else None,
            train_mode=train_mode
        )

        # Collect signals and outcomes for ML training
        if hasattr(period_engine, 'executed_signals'):
            for signal_data in period_engine.executed_signals:
                self.all_signals.append({
                    'signal': signal_data['signal'],
                    'market_data': signal_data['market_data']
                })
                self.all_outcomes.append(1 if signal_data.get('pnl', 0) > 0 else 0)

        return results

    def _aggregate_results(self):
        """Aggregate results from all walk-forward periods"""
        logger.info("\n" + "="*80)
        logger.info("AGGREGATING WALK-FORWARD RESULTS")
        logger.info("="*80)

        total_trades = 0
        total_wins = 0
        total_losses = 0
        total_pnl = 0.0
        total_fees = 0.0
        all_trade_durations = []

        for wf_result in self.walk_forward_results:
            period_res = wf_result['results']
            perf = period_res.get('performance', {})

            total_trades += perf.get('total_trades', 0)
            total_wins += perf.get('winning_trades', 0)
            total_losses += perf.get('losing_trades', 0)
            total_pnl += perf.get('total_pnl', 0)
            total_fees += perf.get('total_fees', 0)

            logger.info(f"Period {wf_result['period']}: "
                       f"{perf.get('total_trades', 0)} trades, "
                       f"WR: {perf.get('win_rate', 0):.1f}%, "
                       f"PnL: ${perf.get('total_pnl', 0):.2f}")

        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        final_balance = self.initial_capital + total_pnl - total_fees
        net_pnl = total_pnl - total_fees
        return_pct = (net_pnl / self.initial_capital * 100)

        aggregated = {
            'backtest_config': {
                'symbol': self.symbol,
                'timeframe': self.timeframe,
                'days': self.days,
                'initial_capital': self.initial_capital,
                'final_capital': final_balance,
                'leverage': self.leverage,
                'ml_enabled': True,
                'min_win_probability': self.min_win_probability,
                'walk_forward_window_days': self.walk_forward_window_days,
                'retrain_interval_days': self.retrain_interval_days,
                'relaxed_params': self.relaxed_params
            },
            'performance': {
                'total_trades': total_trades,
                'winning_trades': total_wins,
                'losing_trades': total_losses,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'total_fees': total_fees,
                'net_pnl': net_pnl,
                'return_pct': return_pct,
                'ml_training_samples': len(self.all_signals)
            },
            'walk_forward_periods': self.walk_forward_results
        }

        # Print summary
        logger.info("\n" + "="*80)
        logger.info("FINAL RESULTS")
        logger.info("="*80)
        logger.info(f"Total Trades: {total_trades}")
        logger.info(f"Win Rate: {win_rate:.2f}% (Target: {self.min_win_probability*100:.0f}%)")
        logger.info(f"Winners: {total_wins} | Losers: {total_losses}")
        logger.info(f"Net PnL: ${net_pnl:.2f} ({return_pct:.2f}%)")
        logger.info(f"Final Balance: ${final_balance:.2f}")
        logger.info(f"Total Fees: ${total_fees:.2f}")
        logger.info(f"ML Training Samples: {len(self.all_signals)}")
        logger.info("="*80)

        if win_rate >= self.min_win_probability * 100:
            logger.info(f"✓ TARGET ACHIEVED: Win rate {win_rate:.2f}% >= {self.min_win_probability*100:.0f}%")
        else:
            logger.warning(f"✗ TARGET MISSED: Win rate {win_rate:.2f}% < {self.min_win_probability*100:.0f}%")

        return aggregated

    def _save_results(self, results):
        """Save results to file"""
        os.makedirs('data/vwap_ml_backtest', exist_ok=True)

        timestamp = int(datetime.now().timestamp())
        filename = f"data/vwap_ml_backtest/vwap_ml_{self.symbol}_{self.timeframe}_{timestamp}.json"

        with open(filename, 'w') as f:
            # Convert datetime objects to strings for JSON serialization
            def default_serializer(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            json.dump(results, f, indent=2, default=default_serializer)

        logger.info(f"\n[SAVE] Results saved to: {filename}")


async def main():
    parser = argparse.ArgumentParser(description='VWAP ML Backtest with Walk-Forward Analysis')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading symbol')
    parser.add_argument('--timeframe', type=str, default='1m', help='Timeframe (1m, 5m, 15m)')
    parser.add_argument('--days', type=int, default=30, help='Number of days to backtest')
    parser.add_argument('--capital', type=float, default=100.0, help='Initial capital')
    parser.add_argument('--leverage', type=int, default=20, help='Leverage')
    parser.add_argument('--min-win-prob', type=float, default=0.60, help='Minimum win probability (0.60 = 60%)')
    parser.add_argument('--walk-window', type=int, default=7, help='Walk-forward training window (days)')
    parser.add_argument('--retrain-interval', type=int, default=3, help='Retrain interval (days)')

    args = parser.parse_args()

    # Relaxed parameters for different timeframes
    relaxed_params = {}

    if args.timeframe == '5m':
        relaxed_params = {
            'min_zone_strength': 60,  # Lower from 70
            'band_proximity_dollars': 400,  # Increase from 300
            'zone_proximity_dollars': 600,  # Increase from 500
        }
    elif args.timeframe == '15m':
        relaxed_params = {
            'min_zone_strength': 50,  # Lower from 70
            'band_proximity_dollars': 500,  # Increase from 300
            'zone_proximity_dollars': 700,  # Increase from 500
        }

    # Create and run backtest
    backtest = VWAPMLBacktest(
        symbol=args.symbol,
        timeframe=args.timeframe,
        days=args.days,
        initial_capital=args.capital,
        leverage=args.leverage,
        min_win_probability=args.min_win_prob,
        walk_forward_window_days=args.walk_window,
        retrain_interval_days=args.retrain_interval,
        relaxed_params=relaxed_params
    )

    results = await backtest.run_walk_forward_backtest()

    # Print feature importance
    if backtest.ml_optimizer.is_trained:
        importance = backtest.ml_optimizer.get_feature_importance()
        logger.info("\n" + "="*80)
        logger.info("FEATURE IMPORTANCE (XGBoost)")
        logger.info("="*80)
        xgb_importance = importance.get('xgb', {})
        sorted_features = sorted(xgb_importance.items(), key=lambda x: x[1], reverse=True)
        for feature, score in sorted_features[:10]:
            logger.info(f"  {feature:<30} {score:.4f}")
        logger.info("="*80)


if __name__ == "__main__":
    asyncio.run(main())
