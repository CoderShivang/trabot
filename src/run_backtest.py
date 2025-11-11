"""
Run backtests on historical data
"""
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from backtesting.backtest_engine import BacktestEngine
from config import Config
from utils.logger import setup_logger
from dotenv import load_dotenv

load_dotenv()
logger = setup_logger(__name__)


def print_metrics(metrics):
    """Pretty print backtest metrics"""
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)

    print(f"\n📊 TRADING STATISTICS")
    print(f"  Total Trades:        {metrics.total_trades}")
    print(f"  Winning Trades:      {metrics.winning_trades}")
    print(f"  Losing Trades:       {metrics.losing_trades}")
    print(f"  Win Rate:            {metrics.win_rate:.2f}%")
    print(f"  Long Trades:         {metrics.long_trades} (Win Rate: {metrics.long_win_rate:.2f}%)")
    print(f"  Short Trades:        {metrics.short_trades} (Win Rate: {metrics.short_win_rate:.2f}%)")

    print(f"\n💰 PROFIT & LOSS")
    print(f"  Net P&L:             ${metrics.net_pnl:+.2f}")
    print(f"  Total Fees:          ${metrics.total_fees:.2f}")
    print(f"  ROI:                 {metrics.roi_pct:+.2f}%")
    print(f"  Profit Factor:       {metrics.profit_factor:.2f}")
    print(f"  Expectancy:          ${metrics.expectancy:+.2f} per trade")

    print(f"\n📈 WIN/LOSS ANALYSIS")
    print(f"  Average Win:         ${metrics.avg_win:.2f}")
    print(f"  Average Loss:        ${metrics.avg_loss:.2f}")
    print(f"  Largest Win:         ${metrics.largest_win:.2f}")
    print(f"  Largest Loss:        ${metrics.largest_loss:.2f}")
    print(f"  Avg Risk/Reward:     {metrics.avg_risk_reward:.2f}")

    print(f"\n⚠️  RISK METRICS")
    print(f"  Max Drawdown:        ${metrics.max_drawdown:.2f} ({metrics.max_drawdown_pct:.2f}%)")
    print(f"  Max Consecutive Losses: {metrics.max_consecutive_losses}")
    print(f"  Sharpe Ratio:        {metrics.sharpe_ratio:.2f}")

    print(f"\n⏱️  TIME METRICS")
    print(f"  Duration:            {metrics.duration_days:.1f} days")
    print(f"  Avg Trade Duration:  {metrics.avg_trade_duration_minutes:.1f} minutes")
    print(f"  Trades Per Day:      {metrics.trades_per_day:.2f}")

    print("\n" + "=" * 60 + "\n")


async def run_backtest(args):
    """Run backtest with specified parameters"""

    # Load config
    config = Config.from_yaml(args.config)

    # Parse dates
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        logger.error("Use YYYY-MM-DD format (e.g., 2025-11-04)")
        sys.exit(1)

    if start_date >= end_date:
        logger.error("Start date must be before end date")
        sys.exit(1)

    # Initialize backtest engine
    logger.info("[BACKTEST] Initializing backtest engine...")
    engine = BacktestEngine(config)
    await engine.initialize()

    # Run backtest
    metrics = await engine.run_backtest(
        symbol=args.symbol,
        start_date=start_date,
        end_date=end_date,
        timeframe=args.timeframe
    )

    # Print results
    print_metrics(metrics)

    # Disconnect
    await engine.binance_client.disconnect()

    return metrics


def main():
    parser = argparse.ArgumentParser(description='Run trading strategy backtest')
    parser.add_argument('symbol', help='Trading symbol (e.g., BTCUSDT)')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--timeframe', default='1m', choices=['1m', '5m', '15m'],
                        help='Execution timeframe (default: 1m)')
    parser.add_argument('--config', default='config/bot_config.yaml',
                        help='Path to config file')

    args = parser.parse_args()

    # Run backtest
    asyncio.run(run_backtest(args))


if __name__ == "__main__":
    main()
