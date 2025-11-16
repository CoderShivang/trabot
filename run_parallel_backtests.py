"""
Run 90d baseline and 180d training backtests in parallel

This saves time by running both backtests simultaneously:
- 90d baseline (Aug 17 - Nov 15)
- 180d training (Feb 18 - Aug 17)

After both complete, you can run ML training and testing.
"""

import asyncio
import logging
from datetime import datetime, timezone
from src.backtesting.vwap_backtest_engine import VWAPBacktestEngine

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def run_90d_baseline():
    """Run 90-day baseline backtest"""
    logger.info("="*80)
    logger.info("STARTING 90-DAY BASELINE BACKTEST")
    logger.info("="*80)
    logger.info("Period: Aug 17 - Nov 15, 2025 (90 days)")
    logger.info("")

    config = {
        'symbol': 'BTCUSDT',
        'timeframe': '1m',
        'initial_capital': 100.0,
        'leverage': 20,
        'risk_per_trade': 0.02
    }

    engine = VWAPBacktestEngine(config)
    start = datetime(2025, 8, 17, tzinfo=timezone.utc)
    end = datetime(2025, 11, 15, tzinfo=timezone.utc)

    results_path = await engine.run(start, end)

    logger.info("")
    logger.info("="*80)
    logger.info("90-DAY BASELINE COMPLETE")
    logger.info("="*80)
    logger.info(f"Results saved to: {results_path}")

    return results_path

async def run_180d_training():
    """Run 180-day training backtest"""
    logger.info("="*80)
    logger.info("STARTING 180-DAY TRAINING BACKTEST")
    logger.info("="*80)
    logger.info("Period: Feb 18 - Aug 17, 2025 (180 days)")
    logger.info("")

    config = {
        'symbol': 'BTCUSDT',
        'timeframe': '1m',
        'initial_capital': 100.0,
        'leverage': 20,
        'risk_per_trade': 0.02
    }

    engine = VWAPBacktestEngine(config)
    start = datetime(2025, 2, 18, tzinfo=timezone.utc)
    end = datetime(2025, 8, 17, tzinfo=timezone.utc)

    results_path = await engine.run(start, end)

    logger.info("")
    logger.info("="*80)
    logger.info("180-DAY TRAINING COMPLETE")
    logger.info("="*80)
    logger.info(f"Results saved to: {results_path}")

    return results_path

async def main():
    logger.info("\n" + "="*80)
    logger.info("PARALLEL BACKTEST EXECUTION")
    logger.info("="*80)
    logger.info("")
    logger.info("Running TWO backtests in parallel:")
    logger.info("  1. 90-day baseline (Aug 17 - Nov 15)")
    logger.info("  2. 180-day training (Feb 18 - Aug 17)")
    logger.info("")
    logger.info("This will take ~20-30 minutes total (vs 40-60 minutes sequential)")
    logger.info("="*80 + "\n")

    # Run both backtests in parallel
    results = await asyncio.gather(
        run_90d_baseline(),
        run_180d_training(),
        return_exceptions=True
    )

    baseline_results, training_results = results

    logger.info("\n" + "="*80)
    logger.info("BOTH BACKTESTS COMPLETE!")
    logger.info("="*80)

    if isinstance(baseline_results, Exception):
        logger.error(f"90d baseline failed: {baseline_results}")
    else:
        logger.info(f"✓ 90d baseline: {baseline_results}")

    if isinstance(training_results, Exception):
        logger.error(f"180d training failed: {training_results}")
    else:
        logger.info(f"✓ 180d training: {training_results}")

    logger.info("")
    logger.info("="*80)
    logger.info("NEXT STEP: Train ML and test")
    logger.info("="*80)
    logger.info("")
    logger.info("Run this command to train ML model and test on 90d:")
    logger.info("  python train_ml_and_compare.py")
    logger.info("")
    logger.info("This will:")
    logger.info("  1. Load 180d training data")
    logger.info("  2. Train ML models (RF, GB, XGB)")
    logger.info("  3. Run 90d ML-filtered backtest")
    logger.info("  4. Compare with 90d baseline")
    logger.info("")

if __name__ == "__main__":
    asyncio.run(main())
