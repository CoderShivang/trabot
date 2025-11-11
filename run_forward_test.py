#!/usr/bin/env python3
"""
Forward Testing Runner - Real-time simulation with live market data.

Connects to live Binance Futures market and simulates trading in real-time.
No actual orders are placed - all positions are tracked in memory.

Usage:
    python run_forward_test.py

Features:
- Analyzes live market data as it comes in
- Simulates position entries/exits
- Sends Discord/Telegram notifications for every trade
- Tracks performance metrics
- Saves results to data/forward_test_results.json

Press Ctrl+C to stop and view results.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config import load_config
from forward_testing.forward_test_engine import ForwardTestEngine
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def main():
    """Main forward testing entry point"""
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config()

        # Create engine
        engine = ForwardTestEngine(config)

        # Initialize
        await engine.initialize()

        # Start forward testing
        logger.info("="*50)
        logger.info("FORWARD TESTING MODE")
        logger.info("="*50)
        logger.info("The bot will analyze LIVE market data and simulate trades.")
        logger.info("NO REAL ORDERS will be placed.")
        logger.info("You'll receive notifications for all simulated trades.")
        logger.info("Press Ctrl+C to stop.\n")

        await engine.start()

    except KeyboardInterrupt:
        logger.info("\n[MAIN] Stopped by user")
    except Exception as e:
        logger.error(f"[MAIN] Error: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
