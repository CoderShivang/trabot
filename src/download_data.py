"""
Download historical data from Binance and cache it locally for offline backtesting.
Run this script ONCE from a location with Binance API access (or with VPN).
"""
import asyncio
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from data.binance_client import BinanceClient
from config import Config
from utils.logger import setup_logger
from dotenv import load_dotenv

load_dotenv()
logger = setup_logger(__name__)


async def download_data(symbol: str, start_date: datetime, end_date: datetime, config: Config):
    """Download and cache historical data"""

    # Create cache directory
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Initialize Binance client (without skip_ping since we need real connection)
    logger.info("[DOWNLOAD] Connecting to Binance API...")
    client = BinanceClient(config, force_mainnet_data=True, backtest_mode=False)

    try:
        # Try normal connection (will fail if geo-restricted)
        await client.connect(skip_ping=False)
    except Exception as e:
        logger.error(f"[DOWNLOAD] Failed to connect to Binance: {e}")
        logger.error("[DOWNLOAD] This script requires API access. Use VPN or run from allowed location.")
        return False

    # Download klines for multiple timeframes
    timeframes = ['1m', '15m', '1h']
    start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)

    all_data = {
        'symbol': symbol,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'timeframes': {}
    }

    for tf in timeframes:
        logger.info(f"[DOWNLOAD] Downloading {symbol} {tf} data...")

        timeframe_ms = {
            '1m': 60 * 1000,
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '1h': 60 * 60 * 1000
        }[tf]

        all_klines = []
        current_start = start_ms

        while current_start < end_ms:
            try:
                chunk_end = min(current_start + (1000 * timeframe_ms), end_ms)

                klines = await client.get_klines(
                    symbol=symbol,
                    interval=tf,
                    limit=1000,
                    start_time=current_start,
                    end_time=chunk_end
                )

                if not klines:
                    break

                all_klines.extend(klines)
                logger.info(f"  Fetched {len(klines)} {tf} candles (total: {len(all_klines)})")

                if klines:
                    current_start = klines[-1][0] + timeframe_ms
                else:
                    break

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"[DOWNLOAD] Error downloading {tf} data: {e}")
                break

        all_data['timeframes'][tf] = all_klines
        logger.info(f"[DOWNLOAD] ✓ Downloaded {len(all_klines)} {tf} candles")

    # Save to cache file
    cache_filename = f"{symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"
    cache_path = cache_dir / cache_filename

    logger.info(f"[DOWNLOAD] Saving data to {cache_path}...")
    with open(cache_path, 'w') as f:
        json.dump(all_data, f)

    # Calculate file size
    file_size_mb = cache_path.stat().st_size / (1024 * 1024)
    logger.info(f"[DOWNLOAD] ✓ Data saved ({file_size_mb:.2f} MB)")
    logger.info(f"[DOWNLOAD] ✓ Cache file: {cache_path}")

    await client.disconnect()
    return True


def main():
    parser = argparse.ArgumentParser(description='Download historical data for offline backtesting')
    parser.add_argument('symbol', help='Trading symbol (e.g., BTCUSDT)')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--config', default='config/bot_config.yaml', help='Path to config file')

    args = parser.parse_args()

    # Load config
    config = Config.from_yaml(args.config)

    # Parse dates
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        logger.error("Use YYYY-MM-DD format")
        sys.exit(1)

    if start_date >= end_date:
        logger.error("Start date must be before end date")
        sys.exit(1)

    # Download data
    success = asyncio.run(download_data(args.symbol, start_date, end_date, config))

    if success:
        print("\n" + "=" * 60)
        print("✓ DATA DOWNLOAD COMPLETE")
        print("=" * 60)
        print(f"Symbol: {args.symbol}")
        print(f"Period: {args.start} to {args.end}")
        print(f"Timeframes: 1m, 15m, 1h")
        print(f"\nYou can now run backtests offline using:")
        print(f"  python src/run_backtest.py {args.symbol} --start {args.start} --end {args.end} --offline")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✗ DATA DOWNLOAD FAILED")
        print("=" * 60)
        print("Make sure you have:")
        print("  1. Valid Binance API keys in .env file")
        print("  2. VPN connection to allowed location")
        print("  3. Or running from non-restricted location")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
