"""
Run backtest on historical Binance data.

Usage:
    python run_backtest.py --symbol BTCUSDT --days 7
    python run_backtest.py --symbol ETHUSDT --start 2025-01-01 --end 2025-01-07
"""

import asyncio
import argparse
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from backtesting.backtest_engine import BacktestEngine
from config import load_config
from utils.logger import setup_logger

logger = setup_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description='Run strategy backtest')

    parser.add_argument('--symbol', type=str, default='BTCUSDT',
                        help='Trading pair (default: BTCUSDT)')

    parser.add_argument('--days', type=int, default=7,
                        help='Number of days to backtest (default: 7)')

    parser.add_argument('--start', type=str, default=None,
                        help='Start date (YYYY-MM-DD)')

    parser.add_argument('--end', type=str, default=None,
                        help='End date (YYYY-MM-DD)')

    parser.add_argument('--timeframe', type=str, default='1m',
                        choices=['1m', '5m', '15m'],
                        help='Execution timeframe (default: 1m)')

    return parser.parse_args()


async def main():
    args = parse_args()

    # Load configuration
    logger.info("[MAIN] Loading configuration...")
    config = load_config()

    # Determine date range
    if args.start and args.end:
        start_date = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    else:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=args.days)

    logger.info("=" * 80)
    logger.info("BACKTEST CONFIGURATION")
    logger.info("=" * 80)
    logger.info(f"Symbol: {args.symbol}")
    logger.info(f"Start: {start_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"End: {end_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"Duration: {(end_date - start_date).days} days")
    logger.info(f"Timeframe: {args.timeframe}")
    logger.info(f"Starting Balance: $100")
    logger.info(f"Leverage: {config.trading.leverage}×")
    logger.info(f"Position Size: ${config.trading.position_size_usdt}")
    logger.info(f"Risk per Trade: ${config.risk.per_trade_max_loss_usdt}")
    logger.info("=" * 80)

    # Create backtest engine
    engine = BacktestEngine(config)
    await engine.initialize()

    # Run backtest
    logger.info("\n[MAIN] Starting backtest...\n")
    metrics = await engine.run_backtest(
        symbol=args.symbol,
        start_date=start_date,
        end_date=end_date,
        timeframe=args.timeframe
    )

    # Print results
    logger.info("\n" + "=" * 80)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 80)
    logger.info(f"Starting Balance: ${engine.starting_balance:.2f}")
    logger.info(f"Ending Balance: ${engine.current_balance:.2f}")
    logger.info(f"Net P&L: ${metrics.net_pnl:+.2f}")
    logger.info(f"ROI: {metrics.roi_pct:+.2f}%")
    logger.info("")
    logger.info(f"Total Trades: {metrics.total_trades}")
    logger.info(f"Winning Trades: {metrics.winning_trades}")
    logger.info(f"Losing Trades: {metrics.losing_trades}")
    logger.info(f"Win Rate: {metrics.win_rate:.2f}%")
    logger.info("")
    logger.info(f"Average Win: ${metrics.avg_win:.2f}")
    logger.info(f"Average Loss: ${metrics.avg_loss:.2f}")
    logger.info(f"Largest Win: ${metrics.largest_win:.2f}")
    logger.info(f"Largest Loss: ${metrics.largest_loss:.2f}")
    logger.info(f"Profit Factor: {metrics.profit_factor:.2f}")
    logger.info(f"Expectancy: ${metrics.expectancy:.2f} per trade")
    logger.info(f"Risk/Reward Ratio: {metrics.avg_risk_reward:.2f}")
    logger.info("")
    logger.info(f"Max Drawdown: ${metrics.max_drawdown:.2f} ({metrics.max_drawdown_pct:.2f}%)")
    logger.info(f"Max Consecutive Losses: {metrics.max_consecutive_losses}")
    logger.info(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    logger.info("")
    logger.info(f"Trades per Day: {metrics.trades_per_day:.2f}")
    logger.info(f"Avg Trade Duration: {metrics.avg_trade_duration_minutes:.1f} minutes")
    logger.info("")
    logger.info(f"Long Trades: {metrics.long_trades} (Win Rate: {metrics.long_win_rate:.2f}%)")
    logger.info(f"Short Trades: {metrics.short_trades} (Win Rate: {metrics.short_win_rate:.2f}%)")
    logger.info("")
    logger.info(f"Total Fees: ${metrics.total_fees:.2f}")
    logger.info("=" * 80)

    # Recommendations
    logger.info("\n" + "=" * 80)
    logger.info("RECOMMENDATIONS")
    logger.info("=" * 80)

    if metrics.win_rate < 45:
        logger.warning("⚠️  Win rate below 45% - Consider increasing entry score threshold")

    if metrics.profit_factor < 1.5:
        logger.warning("⚠️  Profit factor below 1.5 - Strategy may not be profitable long-term")

    if metrics.max_drawdown_pct > 30:
        logger.warning("⚠️  Max drawdown > 30% - Reduce position size or tighten stops")

    if metrics.trades_per_day < 1:
        logger.info("ℹ️  Low trade frequency - Consider lowering entry threshold slightly")

    if metrics.trades_per_day > 10:
        logger.warning("⚠️  High trade frequency - May be overtrading, consider higher threshold")

    if metrics.sharpe_ratio > 1.5:
        logger.info("✓ Excellent risk-adjusted returns (Sharpe > 1.5)")

    if metrics.win_rate >= 50 and metrics.profit_factor >= 1.5:
        logger.info("✓ Strategy shows positive expectancy - Ready for paper trading")

    logger.info("=" * 80)

    # Cleanup
    await engine.binance_client.disconnect()

    logger.info("\n[MAIN] Backtest completed successfully!")
    logger.info(f"[MAIN] Results saved to data/backtest_results/")


if __name__ == '__main__':
    asyncio.run(main())
