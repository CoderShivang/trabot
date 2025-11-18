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
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.backtesting.vwap_backtest_engine import VWAPBacktestEngine
from src.learning.vwap_ml_optimizer import VWAPMLOptimizer
from src.learning.adaptive_ml_filter import AdaptiveMLFilter
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
        use_adaptive_filter: bool = True,  # Enable adaptive threshold adjustment
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
        self.use_adaptive_filter = use_adaptive_filter
        self.relaxed_params = relaxed_params or {}

        # Initialize ML optimizer
        self.ml_optimizer = VWAPMLOptimizer(min_win_probability=min_win_probability)

        # Initialize Adaptive ML Filter (learns from rejected signals)
        if self.use_adaptive_filter:
            self.adaptive_filter = AdaptiveMLFilter(
                initial_min_win_prob=min_win_probability,
                min_threshold=max(0.48, min_win_probability - 0.12),  # Allow 12% reduction
                max_threshold=min(0.70, min_win_probability + 0.10),  # Allow 10% increase
                adjustment_step=0.02,  # Adjust by 2% at a time
                false_negative_tolerance=0.25,  # Tolerate 25% false negatives
                min_opportunity_cost=2.0  # Only adjust if missing >$2 in profits
            )
            logger.info(f"[ADAPTIVE] Adaptive ML filter enabled")
            logger.info(f"[ADAPTIVE] Threshold range: {self.adaptive_filter.min_threshold:.1%} - {self.adaptive_filter.max_threshold:.1%}")
        else:
            self.adaptive_filter = None

        # Prepare strategy parameters (with relaxed params if provided)
        strategy_params = {}
        if self.relaxed_params:
            strategy_params.update(self.relaxed_params)

        # Initialize backtest engine with config dict
        config = {
            'symbol': symbol,
            'timeframe': timeframe,
            'initial_capital': initial_capital,
            'leverage': leverage,
            'risk_per_trade': risk_per_trade,
            'strategy_params': strategy_params
        }
        self.engine = VWAPBacktestEngine(config)

        # Storage for walk-forward results
        self.walk_forward_results = []
        self.all_signals = []  # For ML training
        self.all_outcomes = []  # For ML training

        # Log applied parameters
        if strategy_params:
            logger.info(f"[ML-BACKTEST] Strategy parameters: {strategy_params}")

    async def _fetch_all_data_once(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Fetch all historical data once for the entire backtest period.
        This avoids redundant API calls for each window.
        """
        from src.data.binance_client import BinanceClient

        # Create minimal config for BinanceClient (same approach as VWAPBacktestEngine)
        class TradingConfig:
            def __init__(self, symbols):
                self.symbols = symbols
                self.paper_trading = False

        class MinimalConfig:
            def __init__(self, symbol):
                self.trading = TradingConfig([symbol])
                self.api_key = ""
                self.api_secret = ""

        config = MinimalConfig(self.symbol)
        client = BinanceClient(config)
        await client.connect(skip_ping=True)

        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)

        all_klines = []
        timeframe_ms = self._timeframe_to_ms(self.timeframe)
        current_start = start_ms

        while current_start < end_ms:
            chunk_end = min(current_start + (1000 * timeframe_ms), end_ms)

            klines = await client.get_klines(
                self.symbol,
                self.timeframe,
                start_time=current_start,
                end_time=chunk_end
            )

            if not klines:
                break

            all_klines.extend(klines)

            if klines:
                current_start = klines[-1][0] + timeframe_ms
            else:
                break

        # Convert to DataFrame
        df = pd.DataFrame(all_klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        # Convert types (make timestamps timezone-aware in UTC)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        return df

    def _timeframe_to_ms(self, timeframe: str) -> int:
        """Convert timeframe string to milliseconds"""
        unit = timeframe[-1]
        value = int(timeframe[:-1])

        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        elif unit == 'd':
            return value * 24 * 60 * 60 * 1000
        else:
            return 60 * 1000  # default to 1m

    def _detect_regime_from_data(self, df: pd.DataFrame) -> str:
        """
        Detect market regime from DataFrame (avoiding redundant data fetch).

        Args:
            df: DataFrame with OHLCV data for the period
        """
        if df is None or len(df) < 10:
            return "UNKNOWN"

        try:
            # Calculate metrics
            first_price = df['close'].iloc[0]
            last_price = df['close'].iloc[-1]
            price_change_pct = ((last_price - first_price) / first_price) * 100

            # Calculate trend strength (how directional vs choppy)
            df_copy = df.copy()
            df_copy['returns'] = df_copy['close'].pct_change()
            trend_consistency = df_copy['returns'].mean() / (df_copy['returns'].std() + 1e-10)

            # Regime classification
            if abs(price_change_pct) < 5 and abs(trend_consistency) < 0.5:
                regime = "SIDEWAYS"
            elif price_change_pct > 5 and trend_consistency > 0.3:
                regime = "BULLISH"
            elif price_change_pct < -5 and trend_consistency < -0.3:
                regime = "BEARISH"
            elif price_change_pct > 0:
                regime = "WEAK BULL"
            elif price_change_pct < 0:
                regime = "WEAK BEAR"
            else:
                regime = "NEUTRAL"

            return f"{regime} ({price_change_pct:+.1f}%)"

        except Exception as e:
            logger.warning(f"[REGIME] Failed to detect regime: {e}")
            return "UNKNOWN"

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

        # Fetch ALL data once to avoid redundant API calls
        logger.info("\n[OPTIMIZATION] Fetching all data once for entire period...")
        all_data_df = await self._fetch_all_data_once(start_date, end_date)
        logger.info(f"[OK] Fetched {len(all_data_df):,} candles total\n")

        # Store for dashboard
        self.ohlcv_data = all_data_df

        # Phase 1: Initial training period (collect data without trading)
        training_end = start_date + timedelta(days=self.walk_forward_window_days)

        logger.info("\n" + "="*80)
        logger.info(f"[TRAINING WINDOW]: {start_date.strftime('%d/%m/%y')} - {training_end.strftime('%d/%m/%y')}")
        logger.info(f"   Collecting signals for initial ML training (no trading)")
        logger.info("="*80)

        training_results = await self._run_period(
            start_date,
            training_end,
            train_mode=True,
            pre_fetched_data=all_data_df
        )

        # Train initial ML models
        if len(self.all_signals) >= 30:  # Minimum 30 signals for training
            logger.info(f"\n[OK] Training ML models on {len(self.all_signals)} signals...")
            metrics = self.ml_optimizer.train_models(self.all_signals, self.all_outcomes)
            logger.info(f"[OK] Initial training complete\n")
        else:
            logger.warning(f"[WARN] Insufficient signals ({len(self.all_signals)}/30), skipping ML\n")

        # Phase 2: Walk-forward testing with ML filtering
        logger.info("="*80)
        logger.info("[WALK-FORWARD TESTING PHASE]")
        logger.info("="*80 + "\n")

        current_date = training_end
        test_period_num = 1

        while current_date < end_date:
            # Retrain ML models BEFORE each test window (using all accumulated data)
            # Skip for first window (already trained on initial period)
            if test_period_num > 1 and len(self.all_signals) >= 50:
                logger.info(f"[RETRAIN] Retraining ML models before test window #{test_period_num}...")
                logger.info(f"   Training period: {start_date.strftime('%d/%m/%y')} - {current_date.strftime('%d/%m/%y')}")
                logger.info(f"   Total signals: {len(self.all_signals)}")
                metrics = self.ml_optimizer.train_models(self.all_signals, self.all_outcomes)
                logger.info(f"   [OK] Retrain complete - models updated with latest data\n")

            # Update ML threshold with adaptive filter (if enabled)
            current_threshold = self.min_win_probability
            if self.adaptive_filter:
                current_threshold = self.adaptive_filter.get_current_threshold()
                self.ml_optimizer.min_win_probability = current_threshold
                logger.info(f"[ADAPTIVE] Using adaptive threshold: {current_threshold:.1%}")

            # Calculate test period
            test_start = current_date
            test_end = min(current_date + timedelta(days=self.retrain_interval_days), end_date)

            # Detect regime for this window using pre-fetched data
            test_window_mask = (all_data_df['timestamp'] >= test_start) & (all_data_df['timestamp'] <= test_end)
            test_window_df = all_data_df[test_window_mask]
            regime = self._detect_regime_from_data(test_window_df)

            logger.info("="*80)
            logger.info(f"[TEST WINDOW #{test_period_num}]: {test_start.strftime('%d/%m/%y')} - {test_end.strftime('%d/%m/%y')}")
            logger.info(f"   Market Regime: {regime}")
            logger.info(f"   Status: Testing with ML filtering")
            logger.info("="*80)

            # Run backtest with ML filtering using pre-fetched data
            period_results = await self._run_period(
                test_start,
                test_end,
                train_mode=False,
                use_ml=True,
                window_num=test_period_num,
                pre_fetched_data=all_data_df
            )

            self.walk_forward_results.append({
                'period': test_period_num,
                'start': test_start,
                'end': test_end,
                'regime': regime,
                'results': period_results
            })

            # Display window results
            if period_results:
                perf = period_results.get('performance', {})
                config = period_results.get('backtest_config', {})
                logger.info(f"\n   Window PnL: ${perf.get('net_pnl', 0):.2f}")
                logger.info(f"   Ending Capital: ${config.get('final_capital', 0):.2f}")
                logger.info(f"   Win Rate: {perf.get('win_rate', 0):.1f}%")
                logger.info("")

                # Adaptive ML Filter: Analyze rejected signals and adjust threshold
                if self.adaptive_filter and test_period_num > 1:
                    # Get actual trades from this window
                    actual_trades = period_results.get('trades', [])

                    # Simulate outcomes for rejected signals
                    analysis = self.adaptive_filter.simulate_rejected_outcomes(
                        window_num=test_period_num,
                        actual_trades=actual_trades
                    )

                    # Adjust threshold if needed
                    adjusted = self.adaptive_filter.adjust_threshold(
                        window_num=test_period_num,
                        analysis=analysis
                    )

                    if adjusted:
                        logger.info(f"[ADAPTIVE] ✅ Threshold adjusted for next window")
                    else:
                        logger.info(f"[ADAPTIVE] No threshold adjustment needed")

            # Move to next window
            current_date = test_end
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
        window_num: int = 0,
        pre_fetched_data: pd.DataFrame = None
    ):
        """
        Run backtest for a specific period.

        Args:
            start_date: Period start
            end_date: Period end
            train_mode: If True, collect signals for training only (no trading)
            use_ml: If True, filter trades using ML
            pre_fetched_data: Optional pre-fetched data to avoid redundant API calls

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
        period_engine = VWAPBacktestEngine(
            period_config,
            ml_optimizer=self.ml_optimizer if use_ml else None,
            use_ml=use_ml,
            min_win_probability=self.min_win_probability,
            adaptive_filter=self.adaptive_filter if use_ml else None  # Pass adaptive filter for rejection tracking
        )

        # Apply relaxed parameters
        if self.relaxed_params:
            for key, value in self.relaxed_params.items():
                if hasattr(period_engine, key):
                    setattr(period_engine, key, value)

        # Run the backtest with pre-fetched data (if available)
        results = await period_engine.run(start_date, end_date, pre_fetched_data=pre_fetched_data)

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
        logger.info("[INDIVIDUAL WINDOW RESULTS]")
        logger.info("="*100)

        # Track aggregate metrics
        total_trades = 0
        total_wins = 0
        total_losses = 0
        total_pnl = 0.0
        total_fees = 0.0

        # ML filtering stats
        total_signals_all_windows = 0
        rejected_signals_all_windows = 0
        approved_signals_all_windows = 0

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

            # Skip if no results (backtest failed or returned None)
            if period_res is None:
                logger.warning(f"\n[Window #{period_num}]: {start_date.strftime('%d/%m/%y')} - {end_date.strftime('%d/%m/%y')} - NO RESULTS")
                continue

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

            # Extract ML stats (before using them!)
            total_signals = perf.get('total_signals_generated', 0)
            rejected_signals = perf.get('signals_rejected_by_ml', 0)
            approved_signals = perf.get('signals_approved_by_ml', 0)
            ml_filter_rate = perf.get('ml_filter_rate', 0)

            # Accumulate for totals
            total_trades += trades
            total_wins += perf.get('winning_trades', 0)
            total_losses += perf.get('losing_trades', 0)
            total_pnl += perf.get('total_pnl', 0)
            total_fees += perf.get('total_fees', 0)

            # Accumulate ML stats
            total_signals_all_windows += total_signals
            rejected_signals_all_windows += rejected_signals
            approved_signals_all_windows += approved_signals

            # Track for averages
            if trades > 0:  # Only include windows with trades
                window_win_rates.append(win_rate)
                window_ending_capitals.append(ending_capital)
                window_max_drawdowns.append(abs(max_drawdown))
                window_max_profits.append(largest_win)

            # Display window summary
            regime = wf_result.get('regime', 'UNKNOWN')
            logger.info(f"\n[Window #{period_num}]: {start_date.strftime('%d/%m/%y')} - {end_date.strftime('%d/%m/%y')} | Regime: {regime}")
            logger.info(f"   {'Starting Capital:':<25} ${starting_capital:.2f}")
            logger.info(f"   {'Ending Capital:':<25} ${ending_capital:.2f}")
            logger.info(f"   {'PnL:':<25} ${net_pnl:+.2f}")
            logger.info(f"   {'Win Rate:':<25} {win_rate:.1f}%")
            logger.info(f"   {'Trades Executed:':<25} {trades}")
            logger.info(f"   {'Total Signals:':<25} {total_signals}")
            logger.info(f"   {'ML Rejected:':<25} {rejected_signals}")
            logger.info(f"   {'ML Approved:':<25} {approved_signals}")
            logger.info(f"   {'ML Filter Rate:':<25} {ml_filter_rate:.1f}%")
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

        # Calculate ML filter efficiency
        overall_ml_filter_rate = (rejected_signals_all_windows / total_signals_all_windows * 100) if total_signals_all_windows > 0 else 0

        # Print aggregate summary
        logger.info("\n" + "="*100)
        logger.info("[AGGREGATE RESULTS (ALL WINDOWS)]")
        logger.info("="*100)

        # Date range
        if self.walk_forward_results:
            first_window = self.walk_forward_results[0]
            last_window = self.walk_forward_results[-1]
            logger.info(f"\n{'Backtest Period:':<30} {first_window['start'].strftime('%d/%m/%Y')} to {last_window['end'].strftime('%d/%m/%Y')}")
            logger.info(f"{'Total Duration:':<30} {(last_window['end'] - first_window['start']).days} days")
            logger.info(f"{'Test Windows:':<30} {len(self.walk_forward_results)}")

        logger.info(f"\n{'METRIC':<30} {'VALUE':<30}")
        logger.info("-"*100)

        # Capital & Returns
        logger.info(f"{'Starting Capital:':<30} ${self.initial_capital:.2f}")
        logger.info(f"{'Final Balance:':<30} ${final_balance:.2f}")
        logger.info(f"{'Net PnL:':<30} ${net_pnl:+.2f}")
        logger.info(f"{'Return:':<30} {return_pct:+.2f}%")
        logger.info("")

        # Trading Performance
        logger.info(f"{'Total Trades Executed:':<30} {total_trades}")
        logger.info(f"{'Winning Trades:':<30} {total_wins}")
        logger.info(f"{'Losing Trades:':<30} {total_losses}")
        logger.info(f"{'Overall Win Rate:':<30} {win_rate_overall:.2f}%")
        logger.info("")

        # ML Filtering Stats
        logger.info("ML FILTERING PERFORMANCE:")
        logger.info(f"{'Total Signals Generated:':<30} {total_signals_all_windows}")
        logger.info(f"{'Signals Rejected by ML:':<30} {rejected_signals_all_windows}")
        logger.info(f"{'Signals Approved by ML:':<30} {approved_signals_all_windows}")
        logger.info(f"{'ML Filter Rate:':<30} {overall_ml_filter_rate:.1f}%")
        logger.info(f"{'ML Training Samples:':<30} {len(self.all_signals)}")
        logger.info("")

        # Averages
        logger.info(f"{'Average Win Rate:':<30} {avg_win_rate:.2f}%")
        logger.info(f"{'Average Ending Capital:':<30} ${avg_ending_capital:.2f}")
        logger.info(f"{'Avg Max Drawdown:':<30} ${avg_max_drawdown:.2f}")
        logger.info(f"{'Avg Max Profit (Single):':<30} ${avg_max_profit:.2f}")
        logger.info("")
        logger.info(f"{'Total Fees Paid:':<30} ${total_fees:.2f}")

        # Performance assessment
        logger.info("\n" + "="*100)
        logger.info("[PERFORMANCE ASSESSMENT]")
        logger.info("="*100)
        if win_rate_overall >= self.min_win_probability * 100:
            logger.info(f"[PASS] TARGET ACHIEVED: {win_rate_overall:.2f}% >= {self.min_win_probability*100:.0f}%")
        else:
            logger.info(f"[FAIL] TARGET MISSED: {win_rate_overall:.2f}% < {self.min_win_probability*100:.0f}%")

        if return_pct > 0:
            logger.info(f"[PASS] PROFITABLE: {return_pct:+.2f}% return")
        else:
            logger.info(f"[FAIL] UNPROFITABLE: {return_pct:+.2f}% return")

        logger.info("="*100)

        # Aggregate all trades from all windows for dashboard
        all_trades = []
        walk_forward_windows_metadata = []
        for wf_result in self.walk_forward_results:
            period_res = wf_result['results']
            if period_res and 'trades' in period_res:
                all_trades.extend(period_res['trades'])

            # Build window metadata for dashboard
            if period_res:
                walk_forward_windows_metadata.append({
                    'period': wf_result['period'],
                    'start': wf_result['start'],
                    'end': wf_result['end'],
                    'regime': wf_result.get('regime', 'UNKNOWN'),
                    'performance': period_res.get('performance', {}),
                    'config': period_res.get('backtest_config', {})
                })

        # Build aggregated results dictionary
        aggregated = {
            'backtest_config': {
                'symbol': self.symbol,
                'timeframe': self.timeframe,
                'days': self.days,
                'start_date': self.start_date.strftime('%Y-%m-%d') if self.start_date else None,
                'end_date': self.end_date.strftime('%Y-%m-%d') if self.end_date else None,
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
                'avg_max_profit': avg_max_profit,
                # Add ML stats to performance for dashboard
                'total_signals_generated': total_signals_all_windows,
                'signals_rejected_by_ml': rejected_signals_all_windows,
                'signals_approved_by_ml': approved_signals_all_windows,
                'ml_filter_rate': overall_ml_filter_rate
            },
            'trades': all_trades,  # Combined trades from all windows
            'walk_forward_windows': walk_forward_windows_metadata,  # For dashboard window breakdown
            'walk_forward_periods': self.walk_forward_results  # Keep original for compatibility
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

        # Save OHLCV data for dashboard
        if hasattr(self, 'ohlcv_data') and self.ohlcv_data is not None:
            ohlcv_path = Path('data/vwap_ml_backtest') / 'ohlcv_data.parquet'
            self.ohlcv_data.to_parquet(ohlcv_path, index=False)
            logger.info(f"[SAVE] OHLCV data saved to: {ohlcv_path}")


async def main():
    parser = argparse.ArgumentParser(description='VWAP ML Backtest with Walk-Forward Analysis')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading symbol')
    parser.add_argument('--timeframe', type=str, default='1m', choices=['1m', '5m', '15m'], help='Timeframe (1m, 5m, 15m)')
    parser.add_argument('--days', type=int, default=30, help='Number of days to backtest (from now backwards)')
    parser.add_argument('--start', type=str, default=None, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None, help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=100.0, help='Initial capital')
    parser.add_argument('--leverage', type=int, default=20, help='Leverage')
    parser.add_argument('--min-win-prob', type=float, default=0.60, help='Minimum win probability (default: 0.60)')
    parser.add_argument('--walk-window', type=int, default=7, help='Walk-forward training window (days)')
    parser.add_argument('--retrain-interval', type=int, default=3, help='Retrain interval (days)')
    parser.add_argument('--stop-loss', type=float, default=None, help='Stop loss in points (default: auto based on timeframe)')
    parser.add_argument('--take-profit', type=float, default=None, help='Take profit in points (default: auto based on timeframe)')

    args = parser.parse_args()

    # Parse dates if provided
    start_date = None
    end_date = None
    if args.start and args.end:
        from datetime import timezone
        start_date = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc)

    # Set default SL/TP based on timeframe (user can override with CLI args)
    timeframe_defaults = {
        '1m': {'stop_points': 150, 'target_points': 200},
        '5m': {'stop_points': 200, 'target_points': 400},
        '15m': {'stop_points': 300, 'target_points': 600},
    }

    # Get defaults for selected timeframe
    defaults = timeframe_defaults.get(args.timeframe, timeframe_defaults['1m'])

    # Override with CLI args if provided
    stop_loss = args.stop_loss if args.stop_loss is not None else defaults['stop_points']
    take_profit = args.take_profit if args.take_profit is not None else defaults['target_points']

    logger.info(f"\n[CONFIG] Timeframe: {args.timeframe}")
    logger.info(f"[CONFIG] Stop Loss: {stop_loss} points")
    logger.info(f"[CONFIG] Take Profit: {take_profit} points\n")

    # Relaxed parameters for different timeframes
    relaxed_params = {
        'stop_points': stop_loss,
        'target_points': take_profit,
    }

    if args.timeframe == '5m':
        relaxed_params.update({
            'min_zone_strength': 60,  # Lower from 70
            'band_proximity_dollars': 400,  # Increase from 300
            'zone_proximity_dollars': 600,  # Increase from 500
        })
    elif args.timeframe == '15m':
        relaxed_params.update({
            'min_zone_strength': 50,  # Lower from 70
            'band_proximity_dollars': 500,  # Increase from 300
            'zone_proximity_dollars': 700,  # Increase from 500
        })

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
