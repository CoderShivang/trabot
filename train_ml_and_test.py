"""
Train ML models on 60-day baseline data, then test on 30-day out-of-sample period

Steps:
1. Load 90-day baseline results
2. Split trades: first 60 days for training, last 30 days for reference
3. Train ML models (RF, GB, XGB) on 60-day data
4. Run new 30-day backtest (Oct 16 - Nov 15) with ML filtering
5. Compare baseline vs ML-filtered results
"""

import json
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.learning.vwap_ml_optimizer import VWAPMLOptimizer
from src.backtesting.vwap_ml_backtest_engine import VWAPMLBacktestEngine
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

async def main():
    # Load 90-day baseline results
    baseline_file = 'data/vwap_backtest/vwap_backtest_BTCUSDT_1763210773.json'

    logger.info("=" * 80)
    logger.info("ML TRAINING AND OUT-OF-SAMPLE TESTING")
    logger.info("=" * 80)
    logger.info(f"Loading baseline results from: {baseline_file}")

    with open(baseline_file) as f:
        baseline_data = json.load(f)

    # Get all trades from baseline
    all_trades = baseline_data.get('trades', [])
    total_trades = len(all_trades)

    logger.info(f"Total trades in 90-day baseline: {total_trades}")

    # Split trades by time - first 60 days for training
    # Baseline period: Aug 17 - Nov 15 (90 days)
    # Training: Aug 17 - Oct 16 (60 days)
    # Testing: Oct 16 - Nov 15 (30 days)

    split_date = datetime(2025, 10, 16, tzinfo=timezone.utc)

    training_trades = []
    testing_trades = []

    for trade in all_trades:
        # Convert Unix timestamp (milliseconds) to datetime
        trade_time = datetime.fromtimestamp(trade['entry_time'] / 1000, tz=timezone.utc)
        if trade_time < split_date:
            training_trades.append(trade)
        else:
            testing_trades.append(trade)

    logger.info(f"Training trades (Aug 17 - Oct 16): {len(training_trades)}")
    logger.info(f"Testing trades (Oct 16 - Nov 15): {len(testing_trades)}")

    # Prepare training data for ML
    logger.info("\n" + "=" * 80)
    logger.info("TRAINING ML MODELS")
    logger.info("=" * 80)

    training_signals = []
    training_outcomes = []

    for trade in training_trades:
        # Extract actual signal data from trade
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
                'timestamp': trade.get('entry_time', 0),  # Keep as Unix timestamp (ms)
                'volume': 0,  # Not stored in trade data
                'volatility': 0,  # Not stored in trade data
                'spread_bps': 10  # Assume default
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

    # Now run 30-day backtest with ML filtering
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING 30-DAY ML-FILTERED BACKTEST")
    logger.info("=" * 80)
    logger.info("Period: Oct 16 - Nov 15, 2025 (30 days)")
    logger.info("ML Filtering: ENABLED (min 60% win probability)")

    # Configure backtest
    config = {
        'symbol': 'BTCUSDT',
        'timeframe': '1m',
        'initial_capital': 100.0,
        'leverage': 20,
        'risk_per_trade': 0.02
    }

    # Create ML backtest engine
    ml_engine = VWAPMLBacktestEngine(config, ml_optimizer=ml_optimizer)

    # Run backtest on the 30-day out-of-sample period
    start_date = datetime(2025, 10, 16, tzinfo=timezone.utc)
    end_date = datetime(2025, 11, 15, tzinfo=timezone.utc)

    ml_results = await ml_engine.run(start_date, end_date)

    # Compare results
    logger.info("\n" + "=" * 80)
    logger.info("COMPARISON: BASELINE VS ML-FILTERED")
    logger.info("=" * 80)

    # Calculate baseline stats for last 30 days
    baseline_30d_trades = len(testing_trades)
    baseline_30d_wins = sum(1 for t in testing_trades if t.get('pnl', 0) > 0)
    baseline_30d_wr = (baseline_30d_wins / baseline_30d_trades * 100) if baseline_30d_trades > 0 else 0
    baseline_30d_pnl = sum(t.get('pnl', 0) for t in testing_trades)

    # ML stats
    ml_stats = ml_results.get('performance', {})
    ml_trades = ml_stats.get('total_trades', 0)
    ml_wr = ml_stats.get('win_rate', 0)
    ml_pnl = ml_stats.get('net_pnl', 0)

    ml_filter_stats = ml_results.get('ml_filtering_stats', {})

    logger.info(f"\nBASELINE (Last 30 days, no ML):")
    logger.info(f"  Trades: {baseline_30d_trades}")
    logger.info(f"  Win Rate: {baseline_30d_wr:.2f}%")
    logger.info(f"  Net PnL: ${baseline_30d_pnl:.2f}")

    logger.info(f"\nML-FILTERED (Last 30 days, ML enabled):")
    logger.info(f"  Trades: {ml_trades}")
    logger.info(f"  Win Rate: {ml_wr:.2f}%")
    logger.info(f"  Net PnL: ${ml_pnl:.2f}")
    logger.info(f"  Signals Filtered: {ml_filter_stats.get('signals_filtered', 0)}")
    logger.info(f"  Filter Rate: {ml_filter_stats.get('filter_rate', 0):.1f}%")

    logger.info(f"\nIMPROVEMENT:")
    wr_improvement = ml_wr - baseline_30d_wr
    pnl_improvement = ml_pnl - baseline_30d_pnl
    logger.info(f"  Win Rate: {wr_improvement:+.2f}%")
    logger.info(f"  Net PnL: ${pnl_improvement:+.2f}")

    if ml_wr >= 60.0:
        logger.info(f"\n✓ ML TARGET ACHIEVED: {ml_wr:.2f}% >= 60%")
    else:
        logger.warning(f"\n✗ ML TARGET MISSED: {ml_wr:.2f}% < 60%")

    logger.info("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
