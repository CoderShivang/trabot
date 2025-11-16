"""
Run 90-day baseline backtest with tiered position sizing
Same period as ML test for fair comparison
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
    logger.info("90-DAY BASELINE BACKTEST (TIERED POSITION SIZING)")
    logger.info("="*80)
    logger.info("")
    logger.info("Period: Aug 17 - Nov 15, 2025 (90 days)")
    logger.info("Position Sizing: Tiered (scales at $100, $200, $400, ...)")
    logger.info("Purpose: Fair comparison with ML-filtered backtest")
    logger.info("")

    config = {
        'symbol': 'BTCUSDT',
        'timeframe': '1m',
        'initial_capital': 100.0,
        'leverage': 20,
        'risk_per_trade': 0.02
    }

    engine = VWAPBacktestEngine(config)

    # Same 90-day period as ML test
    start = datetime(2025, 8, 17, tzinfo=timezone.utc)
    end = datetime(2025, 11, 15, tzinfo=timezone.utc)

    logger.info("="*80)
    logger.info("RUNNING BACKTEST...")
    logger.info("="*80)

    results_path = await engine.run(start, end)

    # Load and display results
    with open(results_path, 'r') as f:
        results = json.load(f)

    perf = results.get('performance', {})
    config_out = results.get('backtest_config', {})

    logger.info("")
    logger.info("="*80)
    logger.info("BASELINE RESULTS (90 DAYS - TIERED SIZING)")
    logger.info("="*80)
    logger.info("")
    logger.info(f"Total Trades: {perf.get('total_trades')}")
    logger.info(f"Winners: {perf.get('winning_trades')} | Losers: {perf.get('losing_trades')}")
    logger.info(f"Win Rate: {perf.get('win_rate'):.2f}%")
    logger.info("")
    logger.info(f"Initial Capital: ${config_out.get('initial_capital'):.2f}")
    logger.info(f"Final Capital: ${config_out.get('final_capital'):.2f}")
    logger.info(f"Net PnL: ${perf.get('net_pnl'):.2f}")
    logger.info(f"Return: {perf.get('return_pct'):.2f}%")
    logger.info(f"Total Fees: ${perf.get('total_fees'):.2f}")
    logger.info("")
    logger.info(f"Results saved to: {results_path}")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
