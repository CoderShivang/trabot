"""
Run 180-day backtest for ML training data generation

Period: Feb 18 - Aug 17, 2025 (180 days)
Purpose: Generate training data for ML model
NO OVERLAP with 90d testing period (Aug 17 - Nov 15)
"""

import asyncio
import json
from datetime import datetime, timezone
from src.backtesting.vwap_backtest_engine import VWAPBacktestEngine
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("="*80)
    logger.info("180-DAY TRAINING BACKTEST (OUT-OF-SAMPLE)")
    logger.info("="*80)
    logger.info("")
    logger.info("Period: Feb 18 - Aug 17, 2025 (180 days)")
    logger.info("Testing Period: Aug 17 - Nov 15, 2025 (90 days)")
    logger.info("NO OVERLAP - Prevents look-ahead bias")
    logger.info("")
    logger.info("Purpose: Generate ML training data")
    logger.info("Position Sizing: Full compounding with dynamic leverage")
    logger.info("  - $100-$199: 20x leverage")
    logger.info("  - $200-$399: 15x leverage")
    logger.info("  - $400-$599: 10x leverage")
    logger.info("  - $600+:     5x leverage")
    logger.info("")

    config = {
        'symbol': 'BTCUSDT',
        'timeframe': '1m',
        'initial_capital': 100.0,
        'leverage': 20,
        'risk_per_trade': 0.02
    }

    engine = VWAPBacktestEngine(config)

    # 180-day period for training (NO overlap with testing period)
    start = datetime(2025, 2, 18, tzinfo=timezone.utc)
    end = datetime(2025, 8, 17, tzinfo=timezone.utc)

    logger.info("="*80)
    logger.info("RUNNING BACKTEST...")
    logger.info("="*80)
    logger.info("Progress will show: Capital, Win Rate, Current Leverage")
    logger.info("")

    await engine.run(start, end)

    logger.info("")
    logger.info("="*80)
    logger.info("NEXT STEPS")
    logger.info("="*80)
    logger.info("")
    logger.info("1. Train ML model on this 180-day data:")
    logger.info("   python train_ml_and_test.py")
    logger.info("")
    logger.info("2. Run 90-day baseline backtest (no ML):")
    logger.info("   python run_90d_baseline_tiered.py")
    logger.info("")
    logger.info("3. Run 90-day ML-filtered backtest:")
    logger.info("   python run_vwap_ml_backtest.py --days 90 --filter ml")
    logger.info("")
    logger.info("4. Compare results to measure ML improvement")
    logger.info("   Target: 55-60% win rate (vs 45-47% baseline)")
    logger.info("")

if __name__ == "__main__":
    asyncio.run(main())
