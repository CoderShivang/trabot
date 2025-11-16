"""
Train ML on 60 days BEFORE the 90-day baseline,
then test on the FULL 90 days as unseen data
"""

import asyncio
import json
from datetime import datetime, timezone
from src.backtesting.vwap_backtest_engine import VWAPBacktestEngine
from src.backtesting.vwap_ml_backtest_engine import VWAPMLBacktestEngine
from src.learning.vwap_ml_optimizer import VWAPMLOptimizer
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("="*80)
    logger.info("ML TRAINING FOR 90-DAY OUT-OF-SAMPLE TEST")
    logger.info("="*80)
    logger.info("")
    logger.info("Training Period: Feb 18 - Aug 17, 2025 (180 days)")
    logger.info("Testing Period:  Aug 17 - Nov 15, 2025 (90 days - SAME AS BASELINE)")
    logger.info("Train/Test Split: 67/33 (2:1 ratio)")
    logger.info("")
    logger.info("Will compare with existing baseline (no need to re-run baseline)")
    logger.info("")

    # Step 1: Run 180-day training baseline to collect signals
    logger.info("="*80)
    logger.info("STEP 1: Running 180-day training baseline (Feb 18 - Aug 17, 2025)")
    logger.info("="*80)

    config = {
        'symbol': 'BTCUSDT',
        'timeframe': '1m',
        'initial_capital': 100.0,
        'leverage': 20,
        'risk_per_trade': 0.02
    }

    training_engine = VWAPBacktestEngine(config)

    # Training period: 180 days BEFORE the baseline test period
    training_start = datetime(2025, 2, 18, tzinfo=timezone.utc)
    training_end = datetime(2025, 8, 17, tzinfo=timezone.utc)

    logger.info(f"Running training backtest...")
    training_results_path = await training_engine.run(training_start, training_end)

    # Load training results
    with open(training_results_path, 'r') as f:
        training_data = json.load(f)

    training_trades = training_data.get('trades', [])
    logger.info(f"Training trades collected: {len(training_trades)}")

    # Step 2: Prepare training data for ML
    logger.info("")
    logger.info("="*80)
    logger.info("STEP 2: Training ML models on 60-day data")
    logger.info("="*80)

    training_signals = []
    training_outcomes = []

    for trade in training_trades:
        signal = trade.get('signal', {})
        sr_zone = signal.get('sr_zone', {})
        entry_price = trade.get('entry_price', 0)
        vwap_band = signal.get('vwap_band', entry_price)

        # Calculate vwap_distance_pct (approximation)
        vwap_distance_pct = ((entry_price - vwap_band) / vwap_band * 100) if vwap_band > 0 else 0

        # Calculate zone_distance_pct if zone exists
        zone_level = sr_zone.get('level', entry_price)
        zone_distance_pct = abs((entry_price - zone_level) / zone_level * 100) if zone_level > 0 else 0

        # Calculate vwap_band_distance (in price terms)
        vwap_band_distance = abs(entry_price - vwap_band)

        # Improved signal data with calculated features
        signal_data = {
            'signal': {
                'direction': trade.get('direction', 'LONG'),
                'confidence': signal.get('confidence', 75),
                'entry_price': entry_price,
                'signal_type': signal.get('signal_type', 'mean_reversion'),
                'vwap_band': vwap_band,
                'vwap_distance_pct': vwap_distance_pct,
                'vwap_band_distance': vwap_band_distance,
                'htf_confluence': signal.get('htf_confluence', False),
                'zone_distance_pct': zone_distance_pct,
                'local_sr_present': sr_zone.get('strength', 0) > 0,  # True if zone exists
                # Features we can't reconstruct - use conservative defaults
                'price_structure': 'neutral',  # Can't determine from saved data
                'rapid_momentum': False,  # Conservative default
                'regime_filter': 'neutral',  # Can't determine from saved data
                # S/R zone features
                'sr_zone': sr_zone
            },
            'market_data': {
                'current_price': entry_price,
                'timestamp': trade.get('entry_time', 0),
                'price': entry_price,
                'volume': 100000,  # Use average volume as placeholder
                'volatility': abs(trade.get('take_profit', entry_price) - trade.get('stop_loss', entry_price)),  # Approx from SL/TP distance
                'volume_ratio': 1.0,  # Neutral default
                'spread_bps': 10
            }
        }
        training_signals.append(signal_data)

        # Outcome: 1 if profitable, 0 if loss
        pnl = trade.get('pnl', 0)
        training_outcomes.append(1 if pnl > 0 else 0)

    # Train ML models
    ml_optimizer = VWAPMLOptimizer(min_win_probability=0.60)
    logger.info(f"Training ML models on {len(training_signals)} signals...")
    metrics = ml_optimizer.train_models(training_signals, training_outcomes)

    logger.info("ML models trained successfully!")
    logger.info(f"Training metrics: {metrics}")

    # Step 3: Run 90-day ML-filtered backtest
    logger.info("")
    logger.info("="*80)
    logger.info("STEP 3: Running 90-day ML-filtered backtest (UNSEEN DATA)")
    logger.info("="*80)

    ml_engine = VWAPMLBacktestEngine(config, ml_optimizer=ml_optimizer)

    # Testing period: SAME 90 days as existing baseline
    test_start = datetime(2025, 8, 17, tzinfo=timezone.utc)
    test_end = datetime(2025, 11, 15, tzinfo=timezone.utc)

    logger.info(f"Running ML-filtered backtest on 90 days...")
    ml_results = await ml_engine.run(test_start, test_end)

    # Step 4: Load existing baseline results
    logger.info("")
    logger.info("="*80)
    logger.info("STEP 4: Loading existing baseline results")
    logger.info("="*80)

    # Use the existing 90-day baseline file
    baseline_file = 'data/vwap_backtest/vwap_backtest_BTCUSDT_1763210773.json'
    logger.info(f"Loading baseline from: {baseline_file}")
    with open(baseline_file, 'r') as f:
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
    logger.info(f"  Return: {baseline_perf.get('return_pct'):.2f}%")

    logger.info("")
    logger.info("ML-FILTERED (90 days, ML enabled):")
    logger.info(f"  Trades: {ml_perf.get('total_trades')}")
    logger.info(f"  Win Rate: {ml_perf.get('win_rate'):.2f}%")
    logger.info(f"  Final Capital: ${ml_config.get('final_capital'):.2f}")
    logger.info(f"  Return: {ml_perf.get('return_pct'):.2f}%")
    logger.info(f"  Signals Filtered: {ml_filter_stats.get('signals_filtered')} ({ml_filter_stats.get('filter_rate'):.1f}%)")

    logger.info("")
    logger.info("IMPROVEMENT:")
    wr_improvement = ml_perf.get('win_rate', 0) - baseline_perf.get('win_rate', 0)
    return_improvement = ml_perf.get('return_pct', 0) - baseline_perf.get('return_pct', 0)
    logger.info(f"  Win Rate: {wr_improvement:+.2f}%")
    logger.info(f"  Return: {return_improvement:+.2f}%")
    logger.info(f"  Capital Gain: ${ml_config.get('final_capital', 0) - baseline_config.get('final_capital', 0):+.2f}")

    if ml_perf.get('win_rate', 0) >= 60.0:
        logger.info("")
        logger.info("TARGET ACHIEVED: ML Win Rate >= 60%")
    else:
        logger.info("")
        logger.info(f"TARGET MISSED: ML Win Rate {ml_perf.get('win_rate', 0):.2f}% < 60%")

    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
