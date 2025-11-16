"""
Train ML models on 180d data and test on 90d with comparison

Assumes you've already run: python run_parallel_backtests.py

Steps:
1. Load 180d training backtest results
2. Train ML models (RF, GB, XGB)
3. Run 90d ML-filtered backtest
4. Load 90d baseline results
5. Compare baseline vs ML-filtered
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from src.backtesting.vwap_ml_backtest_engine import VWAPMLBacktestEngine
from src.learning.vwap_ml_optimizer import VWAPMLOptimizer
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("="*80)
    logger.info("ML TRAINING AND COMPARISON")
    logger.info("="*80)
    logger.info("")

    # Find most recent 180d training results
    results_dir = Path('data/vwap_backtest')
    training_files = sorted(results_dir.glob('vwap_backtest_*.json'),
                           key=lambda x: x.stat().st_mtime, reverse=True)

    # Find training file (180 days, Feb-Aug period)
    training_file = None
    baseline_file = None

    for f in training_files:
        with open(f) as file:
            data = json.load(file)
            trades = data.get('trades', [])
            if trades:
                first_trade_time = datetime.fromtimestamp(trades[0]['entry_time']/1000, tz=timezone.utc)
                # Training period starts in Feb 2025
                if first_trade_time.year == 2025 and first_trade_time.month == 2:
                    training_file = f
                # Baseline period starts in Aug 2025
                elif first_trade_time.year == 2025 and first_trade_time.month == 8:
                    baseline_file = f

        if training_file and baseline_file:
            break

    if not training_file:
        logger.error("180d training backtest not found!")
        logger.error("Please run: python run_parallel_backtests.py first")
        return

    if not baseline_file:
        logger.error("90d baseline backtest not found!")
        logger.error("Please run: python run_parallel_backtests.py first")
        return

    logger.info(f"Using 180d training: {training_file.name}")
    logger.info(f"Using 90d baseline: {baseline_file.name}")
    logger.info("")

    # Step 1: Load training data
    logger.info("="*80)
    logger.info("STEP 1: Loading 180d training data")
    logger.info("="*80)

    with open(training_file) as f:
        training_data = json.load(f)

    training_trades = training_data.get('trades', [])
    logger.info(f"Training trades: {len(training_trades)}")

    # Step 2: Prepare ML training data
    logger.info("")
    logger.info("="*80)
    logger.info("STEP 2: Training ML models")
    logger.info("="*80)

    training_signals = []
    training_outcomes = []

    for trade in training_trades:
        signal = trade.get('signal', {})
        sr_zone = signal.get('sr_zone', {})

        signal_data = {
            'signal': {
                'direction': trade.get('direction', 'LONG'),
                'confidence': signal.get('confidence', 75),
                'entry_price': trade.get('entry_price', 0),
                'signal_type': signal.get('signal_type', 'mean_reversion'),
                'vwap_band': signal.get('vwap_band', trade.get('entry_price', 0)),
                'htf_confluence': signal.get('htf_confluence', False),
                'zone_strength': sr_zone.get('strength', 0),
                'zone_type': sr_zone.get('zone_type', 'unknown')
            },
            'market_data': {
                'current_price': trade.get('entry_price', 0),
                'timestamp': trade.get('entry_time', 0),
                'volume': 0,
                'volatility': 0,
                'spread_bps': 10
            }
        }
        training_signals.append(signal_data)

        # Outcome: 1 if profitable, 0 if loss
        pnl = trade.get('pnl', 0)
        training_outcomes.append(1 if pnl > 0 else 0)

    # Train ML models
    ml_optimizer = VWAPMLOptimizer(min_win_probability=0.60)

    if len(training_signals) >= 30:
        logger.info(f"Training ML models on {len(training_signals)} signals...")
        metrics = ml_optimizer.train_models(training_signals, training_outcomes)
        logger.info("ML models trained successfully!")
        logger.info(f"Training metrics: {metrics}")
    else:
        logger.error(f"Insufficient training data: {len(training_signals)} < 30")
        return

    # Step 3: Run 90d ML-filtered backtest
    logger.info("")
    logger.info("="*80)
    logger.info("STEP 3: Running 90d ML-filtered backtest")
    logger.info("="*80)
    logger.info("Period: Aug 17 - Nov 15, 2025 (90 days)")
    logger.info("ML Filtering: ENABLED (min 60% win probability)")

    config = {
        'symbol': 'BTCUSDT',
        'timeframe': '1m',
        'initial_capital': 100.0,
        'leverage': 20,
        'risk_per_trade': 0.02
    }

    ml_engine = VWAPMLBacktestEngine(config, ml_optimizer=ml_optimizer)

    start_date = datetime(2025, 8, 17, tzinfo=timezone.utc)
    end_date = datetime(2025, 11, 15, tzinfo=timezone.utc)

    ml_results = await ml_engine.run(start_date, end_date)

    # Step 4: Load baseline results
    logger.info("")
    logger.info("="*80)
    logger.info("STEP 4: Loading 90d baseline results")
    logger.info("="*80)

    with open(baseline_file) as f:
        baseline_data = json.load(f)

    baseline_perf = baseline_data.get('performance', {})
    baseline_config = baseline_data.get('backtest_config', {})

    ml_perf = ml_results.get('performance', {})
    ml_config = ml_results.get('backtest_config', {})
    ml_filter_stats = ml_results.get('ml_filtering_stats', {})

    # Step 5: Display comparison
    logger.info("")
    logger.info("="*80)
    logger.info("STEP 5: COMPARISON RESULTS")
    logger.info("="*80)
    logger.info("")
    logger.info("BASELINE (90 days, no ML):")
    logger.info(f"  Trades: {baseline_perf.get('total_trades')}")
    logger.info(f"  Win Rate: {baseline_perf.get('win_rate'):.2f}%")
    logger.info(f"  Final Capital: ${baseline_config.get('final_capital'):.2f}")
    logger.info(f"  Net PnL: ${baseline_perf.get('net_pnl'):.2f}")
    logger.info(f"  Return: {baseline_perf.get('return_pct'):.2f}%")

    logger.info("")
    logger.info("ML-FILTERED (90 days, ML enabled):")
    logger.info(f"  Trades: {ml_perf.get('total_trades')}")
    logger.info(f"  Win Rate: {ml_perf.get('win_rate'):.2f}%")
    logger.info(f"  Final Capital: ${ml_config.get('final_capital'):.2f}")
    logger.info(f"  Net PnL: ${ml_perf.get('net_pnl'):.2f}")
    logger.info(f"  Return: {ml_perf.get('return_pct'):.2f}%")
    logger.info(f"  Signals Filtered: {ml_filter_stats.get('signals_filtered')} ({ml_filter_stats.get('filter_rate'):.1f}%)")

    logger.info("")
    logger.info("IMPROVEMENT:")
    wr_improvement = ml_perf.get('win_rate', 0) - baseline_perf.get('win_rate', 0)
    return_improvement = ml_perf.get('return_pct', 0) - baseline_perf.get('return_pct', 0)
    pnl_improvement = ml_perf.get('net_pnl', 0) - baseline_perf.get('net_pnl', 0)
    logger.info(f"  Win Rate: {wr_improvement:+.2f}%")
    logger.info(f"  Return: {return_improvement:+.2f}%")
    logger.info(f"  Net PnL: ${pnl_improvement:+.2f}")

    if ml_perf.get('win_rate', 0) >= 60.0:
        logger.info("")
        logger.info("✓ ML TARGET ACHIEVED: Win Rate >= 60%")
    elif ml_perf.get('win_rate', 0) >= 55.0:
        logger.info("")
        logger.info("⚠ ML TARGET CLOSE: Win Rate >= 55% (target 60%)")
    else:
        logger.info("")
        logger.info(f"✗ ML TARGET MISSED: Win Rate {ml_perf.get('win_rate', 0):.2f}% < 60%")

    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
