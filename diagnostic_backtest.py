"""
Diagnostic backtest - Shows why trades are rejected.
Enables INFO/DEBUG logging to see scoring and rejection reasons.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from backtesting.backtest_engine import BacktestEngine
from config import load_config
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def main():
    """Run diagnostic backtest with full logging"""

    config = load_config()

    # Use historical data from January 2025 (known volatile period with clear trends)
    end_date = datetime(2025, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    start_date = datetime(2025, 1, 10, 0, 0, 0, tzinfo=timezone.utc)

    print("\n" + "=" * 80)
    print("DIAGNOSTIC BACKTEST - See why trades are rejected")
    print("=" * 80)
    print(f"Period: {start_date} to {end_date} (12 hours = 720 candles)")
    print("Using historical data from January 2025")
    print("=" * 80)
    print("\nWill show:")
    print("  - Scores for each evaluation")
    print("  - Confirmation signals detected")
    print("  - Rejection reasons")
    print("=" * 80)
    print()

    engine = BacktestEngine(config)
    await engine.initialize()

    # Temporarily disable log suppression to see what's happening
    # We'll monkey-patch the backtest to skip the logging.disable() calls
    original_run_backtest = engine.run_backtest

    async def diagnostic_run_backtest(*args, **kwargs):
        """Run backtest but skip log suppression"""
        import logging as logging_module

        # Temporarily set INFO level (not ERROR) to see logs
        old_disable = logging_module.disable
        logging_module.disable = lambda level: None  # No-op

        try:
            result = await original_run_backtest(*args, **kwargs)
        finally:
            # Restore
            logging_module.disable = old_disable

        return result

    engine.run_backtest = diagnostic_run_backtest

    # Run with logs enabled
    print("[DIAGNOSTIC] Starting backtest with full logging...\n")

    try:
        metrics = await engine.run_backtest(
            symbol='BTCUSDT',
            start_date=start_date,
            end_date=end_date,
            timeframe='1m'
        )

        print("\n" + "=" * 80)
        print("DIAGNOSTIC COMPLETE")
        print("=" * 80)
        print(f"Total Trades: {metrics.total_trades}")
        print("\nCheck the logs above to see:")
        print("  1. What scores were generated")
        print("  2. How many confirmation signals detected")
        print("  3. Why trades were rejected")
        print("=" * 80)

    finally:
        await engine.binance_client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
