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


def print_trades_with_ist(trades):
    """Print detailed trade information with IST timestamps and trade reasoning"""
    from datetime import datetime, timedelta, timezone

    if not trades:
        print("No trades executed during backtest period.")
        return

    print("\n" + "=" * 100)
    print("DETAILED TRADE LOG WITH REASONING (IST - Indian Standard Time)")
    print("=" * 100)

    # IST is UTC+5:30
    ist_offset = timedelta(hours=5, minutes=30)

    for i, trade in enumerate(trades, 1):
        # Convert timestamps from milliseconds to datetime
        entry_time_utc = datetime.fromtimestamp(trade['entry_time'] / 1000, tz=timezone.utc)
        exit_time_utc = datetime.fromtimestamp(trade['exit_time'] / 1000, tz=timezone.utc)

        # Convert to IST
        entry_time_ist = entry_time_utc + ist_offset
        exit_time_ist = exit_time_utc + ist_offset

        # Extract CLC score and market context
        clc = trade.get('clc_score', {})
        market_ctx = clc.get('market_context', {})
        reasons = clc.get('reasons', [])
        nearby_sr = clc.get('nearby_sr_zones', [])

        print(f"\n{'─' * 100}")
        print(f"TRADE #{i} - {trade['direction']}")
        print(f"{'─' * 100}")

        # Basic Trade Info
        print(f"\nTRADE DETAILS:")
        print(f"  Entry Time IST:  {entry_time_ist.strftime('%Y-%m-%d %H:%M:%S')} IST")
        print(f"  Entry Price:     ${trade['entry_price']:,.2f}")
        print(f"  Exit Time IST:   {exit_time_ist.strftime('%Y-%m-%d %H:%M:%S')} IST")
        print(f"  Exit Price:      ${trade['exit_price']:,.2f}")
        print(f"  Exit Reason:     {trade['exit_reason']}")
        print(f"  Duration:        {trade['duration_minutes']:.1f} minutes")

        # Position Sizing
        print(f"\nPOSITION SIZING:")
        print(f"  Quantity:        {trade['quantity']:.8f} BTC")
        print(f"  Notional:        ${trade['notional_value']:,.2f}")
        print(f"  Leverage:        {trade['leverage']}x")
        print(f"  Initial Margin:  ${trade['initial_margin']:.2f}")

        # P&L
        print(f"\nPROFIT & LOSS:")
        print(f"  Gross P&L:       ${trade['pnl']:+.2f}")
        print(f"  Fees:            ${trade['fees']:.2f}")
        print(f"  Net P&L:         ${trade['net_pnl']:+.2f}")
        print(f"  ROE:             {trade['roe_pct']:+.2f}%")

        # Trade Logic & Reasoning
        print(f"\nTRADE LOGIC:")
        if market_ctx:
            regime = market_ctx.get('regime', 'unknown').upper()
            adx = market_ctx.get('adx', 0)
            print(f"  Market Regime:   {regime} (ADX={adx:.1f})")

        if reasons:
            print(f"  Entry Reasons:")
            for reason in reasons:
                print(f"    • {reason}")

        # Market Context - Proximity to Key Levels
        print(f"\nPROXIMITY TO KEY LEVELS:")
        if market_ctx:
            entry_price = trade['entry_price']
            vwap = market_ctx.get('vwap', 0)
            ema20 = market_ctx.get('ema20', 0)
            ema50 = market_ctx.get('ema50', 0)
            ema200 = market_ctx.get('ema200', 0)

            if vwap > 0:
                vwap_dist = ((entry_price - vwap) / vwap) * 100
                print(f"  VWAP:            ${vwap:,.2f} ({vwap_dist:+.2f}%)")

            if ema20 > 0:
                ema20_dist = ((entry_price - ema20) / ema20) * 100
                print(f"  EMA 20:          ${ema20:,.2f} ({ema20_dist:+.2f}%)")

            if ema50 > 0:
                ema50_dist = ((entry_price - ema50) / ema50) * 100
                print(f"  EMA 50:          ${ema50:,.2f} ({ema50_dist:+.2f}%)")

            if ema200 > 0:
                ema200_dist = ((entry_price - ema200) / ema200) * 100
                print(f"  EMA 200:         ${ema200:,.2f} ({ema200_dist:+.2f}%)")

        # Nearby S/R Zones
        if nearby_sr:
            print(f"\nNEARBY SUPPORT/RESISTANCE ZONES:")
            for zone in nearby_sr:
                level = zone.get('level', 0)
                zone_type = zone.get('type', 'unknown').upper()
                dist_pct = zone.get('distance_pct', 0)
                strength = zone.get('strength', 0)
                print(f"  {zone_type:12} @ ${level:,.2f} (±{dist_pct:.2f}%, strength: {strength:.1f}/10)")

    print("\n" + "=" * 100 + "\n")


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
    engine = BacktestEngine(config, offline_mode=args.offline)
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

    # Print detailed trade information with IST timestamps
    print_trades_with_ist(engine.closed_trades)

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
    parser.add_argument('--offline', action='store_true',
                        help='Use cached data instead of fetching from API')

    args = parser.parse_args()

    # Run backtest
    asyncio.run(run_backtest(args))


if __name__ == "__main__":
    main()
