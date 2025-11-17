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
        start_date: datetime = None,
        end_date: datetime = None,
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
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.leverage = leverage
        self.risk_per_trade = risk_per_trade
        self.walk_forward_window_days = walk_forward_window_days
        self.retrain_interval_days = retrain_interval_days
        self.min_win_probability = min_win_probability
        self.relaxed_params = relaxed_params or {}

        # Initialize ML optimizer
        self.ml_optimizer = VWAPMLOptimizer(min_win_probability=min_win_probability)

        # Initialize backtest engine with config dict
        config = {
            'symbol': symbol,
            'timeframe': timeframe,
            'initial_capital': initial_capital,
            'leverage': leverage,
            'risk_per_trade': risk_per_trade
        }
        self.engine = VWAPBacktestEngine(config)

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

        # Calculate date ranges
        if self.start_date and self.end_date:
            start_date = self.start_date
            end_date = self.end_date
            total_days = (end_date - start_date).days
            logger.info(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} ({total_days} days)")
        else:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.days)
            logger.info(f"Period: {self.days} days")

        logger.info(f"Walk-Forward Window: {self.walk_forward_window_days} days")
        logger.info(f"Retrain Interval: {self.retrain_interval_days} days")
        logger.info(f"Min Win Probability: {self.min_win_probability:.1%}")
        logger.info(f"Initial Capital: ${self.initial_capital}")
        logger.info(f"Leverage: {self.leverage}x")
        logger.info("="*80)

        # Phase 1: Initial training period (collect data without trading)
        training_end = start_date + timedelta(days=self.walk_forward_window_days)

        logger.info("\n" + "="*80)
        logger.info(f"📚 TRAINING WINDOW: {start_date.strftime('%d/%m/%y')} - {training_end.strftime('%d/%m/%y')}")
        logger.info(f"   Collecting signals for initial ML training (no trading)")
        logger.info("="*80)

        training_results = await self._run_period(
            start_date,
            training_end,
            train_mode=True
        )

        # Train initial ML models
        if len(self.all_signals) >= 30:  # Minimum 30 signals for training
            logger.info(f"\n✓ Training ML models on {len(self.all_signals)} signals...")
            metrics = self.ml_optimizer.train_models(self.all_signals, self.all_outcomes)
            logger.info(f"✓ Initial training complete\n")
        else:
            logger.warning(f"⚠ Insufficient signals ({len(self.all_signals)}/30), skipping ML\n")

        # Phase 2: Walk-forward testing with ML filtering
        logger.info("="*80)
        logger.info("🔄 WALK-FORWARD TESTING PHASE")
        logger.info("="*80 + "\n")

        current_date = training_end
        retrain_counter = 0
        test_period_num = 1

        while current_date < end_date:
            # Calculate test period
            test_start = current_date
            test_end = min(current_date + timedelta(days=self.retrain_interval_days), end_date)

            logger.info("="*80)
            logger.info(f"📊 TEST WINDOW #{test_period_num}: {test_start.strftime('%d/%m/%y')} - {test_end.strftime('%d/%m/%y')}")
            logger.info(f"   Status: Testing with ML filtering")
            logger.info("="*80)

            # Run backtest with ML filtering
            period_results = await self._run_period(
                test_start,
                test_end,
                train_mode=False,
                use_ml=True,
                window_num=test_period_num
            )

            self.walk_forward_results.append({
                'period': test_period_num,
                'start': test_start,
                'end': test_end,
                'results': period_results
            })

            # Display window results
            if period_results:
                perf = period_results.get('performance', {})
                config = period_results.get('backtest_config', {})
                logger.info(f"\n   💰 Window PnL: ${perf.get('net_pnl', 0):.2f}")
                logger.info(f"   📈 Ending Capital: ${config.get('final_capital', 0):.2f}")
                logger.info(f"   ✅ Win Rate: {perf.get('win_rate', 0):.1f}%")
                logger.info("")

            # Retrain ML models if we have enough new data
            if len(self.all_signals) >= 50 and retrain_counter >= self.retrain_interval_days:
                train_start_retrain = start_date
                train_end_retrain = test_end
                logger.info(f"🔄 Retraining ML models...")
                logger.info(f"   Training period: {train_start_retrain.strftime('%d/%m/%y')} - {train_end_retrain.strftime('%d/%m/%y')}")
                logger.info(f"   Total signals: {len(self.all_signals)}")
                metrics = self.ml_optimizer.train_models(self.all_signals, self.all_outcomes)
                logger.info(f"   ✓ Retrain complete\n")
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
        use_ml: bool = False,
        window_num: int = 0
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
        # Initialize new engine instance for this period
        period_config = {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'initial_capital': self.initial_capital,
            'leverage': self.leverage,
            'risk_per_trade': self.risk_per_trade
        }
        period_engine = VWAPBacktestEngine(period_config)

        # Apply relaxed parameters
        if self.relaxed_params:
            for key, value in self.relaxed_params.items():
                if hasattr(period_engine, key):
                    setattr(period_engine, key, value)

        # Run the backtest (VWAPBacktestEngine expects datetime objects)
        results = await period_engine.run(start_date, end_date)

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
        logger.info("\n" + "="*100)
        logger.info("📋 INDIVIDUAL WINDOW RESULTS")
        logger.info("="*100)

        # Track aggregate metrics
        total_trades = 0
        total_wins = 0
        total_losses = 0
        total_pnl = 0.0
        total_fees = 0.0

        # For averaging
        window_win_rates = []
        window_ending_capitals = []
        window_max_drawdowns = []
        window_max_profits = []

        # Display individual window results
        for wf_result in self.walk_forward_results:
            period_num = wf_result['period']
            start_date = wf_result['start']
            end_date = wf_result['end']
            period_res = wf_result['results']
            perf = period_res.get('performance', {})
            config = period_res.get('backtest_config', {})

            # Extract metrics
            starting_capital = config.get('initial_capital', self.initial_capital)
            ending_capital = config.get('final_capital', starting_capital)
            win_rate = perf.get('win_rate', 0)
            max_drawdown = perf.get('max_drawdown', 0)
            largest_win = perf.get('largest_win', 0)
            net_pnl = perf.get('net_pnl', 0)
            trades = perf.get('total_trades', 0)

            # Accumulate for totals
            total_trades += trades
            total_wins += perf.get('winning_trades', 0)
            total_losses += perf.get('losing_trades', 0)
            total_pnl += perf.get('total_pnl', 0)
            total_fees += perf.get('total_fees', 0)

            # Track for averages
            if trades > 0:  # Only include windows with trades
                window_win_rates.append(win_rate)
                window_ending_capitals.append(ending_capital)
                window_max_drawdowns.append(abs(max_drawdown))
                window_max_profits.append(largest_win)

            # Display window summary
            logger.info(f"\n🪟 Window #{period_num}: {start_date.strftime('%d/%m/%y')} - {end_date.strftime('%d/%m/%y')}")
            logger.info(f"   {'Starting Capital:':<25} ${starting_capital:.2f}")
            logger.info(f"   {'Ending Capital:':<25} ${ending_capital:.2f}")
            logger.info(f"   {'PnL:':<25} ${net_pnl:+.2f}")
            logger.info(f"   {'Win Rate:':<25} {win_rate:.1f}%")
            logger.info(f"   {'Trades:':<25} {trades}")
            logger.info(f"   {'Max Drawdown:':<25} ${max_drawdown:.2f}")
            logger.info(f"   {'Max Profit (Single):':<25} ${largest_win:.2f}")

        # Calculate aggregate statistics
        win_rate_overall = (total_wins / total_trades * 100) if total_trades > 0 else 0
        final_balance = self.initial_capital + total_pnl - total_fees
        net_pnl = total_pnl - total_fees
        return_pct = (net_pnl / self.initial_capital * 100)

        # Calculate averages
        avg_win_rate = sum(window_win_rates) / len(window_win_rates) if window_win_rates else 0
        avg_ending_capital = sum(window_ending_capitals) / len(window_ending_capitals) if window_ending_capitals else self.initial_capital
        avg_max_drawdown = sum(window_max_drawdowns) / len(window_max_drawdowns) if window_max_drawdowns else 0
        avg_max_profit = sum(window_max_profits) / len(window_max_profits) if window_max_profits else 0

        # Print aggregate summary
        logger.info("\n" + "="*100)
        logger.info("📊 AGGREGATE RESULTS (ALL WINDOWS)")
        logger.info("="*100)
        logger.info(f"\n{'METRIC':<30} {'VALUE':<30}")
        logger.info("-"*100)
        logger.info(f"{'Starting Capital:':<30} ${self.initial_capital:.2f}")
        logger.info(f"{'Final Balance:':<30} ${final_balance:.2f}")
        logger.info(f"{'Net PnL:':<30} ${net_pnl:+.2f}")
        logger.info(f"{'Return:':<30} {return_pct:+.2f}%")
        logger.info("")
        logger.info(f"{'Total Trades:':<30} {total_trades}")
        logger.info(f"{'Winning Trades:':<30} {total_wins}")
        logger.info(f"{'Losing Trades:':<30} {total_losses}")
        logger.info(f"{'Overall Win Rate:':<30} {win_rate_overall:.2f}%")
        logger.info("")
        logger.info(f"{'Average Win Rate:':<30} {avg_win_rate:.2f}%")
        logger.info(f"{'Average Ending Capital:':<30} ${avg_ending_capital:.2f}")
        logger.info(f"{'Avg Max Drawdown:':<30} ${avg_max_drawdown:.2f}")
        logger.info(f"{'Avg Max Profit (Single):':<30} ${avg_max_profit:.2f}")
        logger.info("")
        logger.info(f"{'Total Fees Paid:':<30} ${total_fees:.2f}")
        logger.info(f"{'ML Training Samples:':<30} {len(self.all_signals)}")
        logger.info(f"{'Test Windows:':<30} {len(self.walk_forward_results)}")

        # Performance assessment
        logger.info("\n" + "="*100)
        logger.info("📈 PERFORMANCE ASSESSMENT")
        logger.info("="*100)
        if win_rate_overall >= self.min_win_probability * 100:
            logger.info(f"✅ TARGET ACHIEVED: {win_rate_overall:.2f}% >= {self.min_win_probability*100:.0f}%")
        else:
            logger.info(f"❌ TARGET MISSED: {win_rate_overall:.2f}% < {self.min_win_probability*100:.0f}%")

        if return_pct > 0:
            logger.info(f"✅ PROFITABLE: {return_pct:+.2f}% return")
        else:
            logger.info(f"❌ UNPROFITABLE: {return_pct:+.2f}% return")

        logger.info("="*100)

        # Build aggregated results dictionary
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
                'win_rate': win_rate_overall,
                'total_pnl': total_pnl,
                'total_fees': total_fees,
                'net_pnl': net_pnl,
                'return_pct': return_pct,
                'ml_training_samples': len(self.all_signals),
                'avg_win_rate': avg_win_rate,
                'avg_ending_capital': avg_ending_capital,
                'avg_max_drawdown': avg_max_drawdown,
                'avg_max_profit': avg_max_profit
            },
            'walk_forward_periods': self.walk_forward_results
        }

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
    parser.add_argument('--days', type=int, default=30, help='Number of days to backtest (from now backwards)')
    parser.add_argument('--start', type=str, default=None, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None, help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=100.0, help='Initial capital')
    parser.add_argument('--leverage', type=int, default=20, help='Leverage')
    parser.add_argument('--min-win-prob', type=float, default=0.60, help='Minimum win probability (default: 0.60)')
    parser.add_argument('--walk-window', type=int, default=7, help='Walk-forward training window (days)')
    parser.add_argument('--retrain-interval', type=int, default=3, help='Retrain interval (days)')

    args = parser.parse_args()

    # Parse dates if provided
    start_date = None
    end_date = None
    if args.start and args.end:
        from datetime import timezone
        start_date = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc)

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
        start_date=start_date,
        end_date=end_date,
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
