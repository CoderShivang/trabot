"""
VWAP Backtest Dashboard

Displays comprehensive trade analysis from VWAP backtest results including:
- Individual trade details with entry reasons
- Performance metrics (PNL, win rate, profit factor)
- Long/Short bias analysis
- Confidence score distribution
- Time-based patterns

Usage:
    python dashboard_vwap.py <results_file.json>
    python dashboard_vwap.py  # Will load latest results file
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import statistics


def load_latest_results() -> Dict:
    """Load the most recent backtest results"""
    results_dir = Path('data/vwap_backtest')

    if not results_dir.exists():
        print("[ERROR] No results directory found. Run backtest first.")
        sys.exit(1)

    json_files = list(results_dir.glob('vwap_backtest_*.json'))

    if not json_files:
        print("[ERROR] No backtest results found. Run backtest first.")
        sys.exit(1)

    # Get most recent file
    latest_file = max(json_files, key=lambda p: p.stat().st_mtime)

    print(f"[INFO] Loading results from: {latest_file.name}\n")

    with open(latest_file, 'r') as f:
        return json.load(f)


def load_results(filepath: str) -> Dict:
    """Load backtest results from file"""
    with open(filepath, 'r') as f:
        return json.load(f)


def format_timestamp_ist(timestamp_ms: int) -> str:
    """Convert UTC timestamp to IST format"""
    utc = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    ist = utc + timedelta(hours=5, minutes=30)
    return ist.strftime('%Y-%m-%d %H:%M:%S IST')


def calculate_profit_factor(trades: List[Dict]) -> float:
    """Calculate profit factor (gross wins / gross losses)"""
    total_wins = sum(t['pnl'] for t in trades if t['pnl'] and t['pnl'] > 0)
    total_losses = abs(sum(t['pnl'] for t in trades if t['pnl'] and t['pnl'] < 0))

    if total_losses == 0:
        return float('inf') if total_wins > 0 else 0

    return total_wins / total_losses


def calculate_sharpe_ratio(trades: List[Dict]) -> float:
    """Calculate Sharpe ratio (simplified - per trade basis)"""
    pnls = [t['pnl_pct'] for t in trades if t['pnl_pct']]

    if not pnls or len(pnls) < 2:
        return 0

    avg_return = statistics.mean(pnls)
    std_return = statistics.stdev(pnls)

    if std_return == 0:
        return 0

    # Annualized approximation (252 trading days, assuming ~20 trades per day on 1m TF)
    return (avg_return / std_return) * (252 * 20) ** 0.5


def analyze_long_short_bias(trades: List[Dict]) -> Dict:
    """Analyze performance by direction"""
    longs = [t for t in trades if t['direction'] == 'LONG']
    shorts = [t for t in trades if t['direction'] == 'SHORT']

    long_pnl = sum(t['pnl'] for t in longs if t['pnl'])
    short_pnl = sum(t['pnl'] for t in shorts if t['pnl'])

    long_wins = len([t for t in longs if t['pnl'] and t['pnl'] > 0])
    short_wins = len([t for t in shorts if t['pnl'] and t['pnl'] > 0])

    return {
        'long': {
            'count': len(longs),
            'wins': long_wins,
            'win_rate': (long_wins / len(longs) * 100) if longs else 0,
            'total_pnl': long_pnl
        },
        'short': {
            'count': len(shorts),
            'wins': short_wins,
            'win_rate': (short_wins / len(shorts) * 100) if shorts else 0,
            'total_pnl': short_pnl
        }
    }


def analyze_signal_types(trades: List[Dict]) -> Dict:
    """Analyze performance by signal type"""
    # Count by exit reason in the JSON (we don't have signal_type in the trades)
    # But we can infer from the position_id or analyze exit reasons
    tp_trades = [t for t in trades if t.get('exit_reason') == 'TP']
    sl_trades = [t for t in trades if t.get('exit_reason') == 'SL']

    return {
        'tp_exits': {
            'count': len(tp_trades),
            'pnl': sum(t['pnl'] for t in tp_trades if t['pnl'])
        },
        'sl_exits': {
            'count': len(sl_trades),
            'pnl': sum(t['pnl'] for t in sl_trades if t['pnl'])
        }
    }


def display_dashboard(results: Dict):
    """Display comprehensive dashboard"""
    config = results['backtest_config']
    perf = results['performance']
    trades = results['trades']
    order_stats = results['order_stats']

    # Header
    print("=" * 100)
    print(f"{'VWAP BACKTEST DASHBOARD':^100}")
    print("=" * 100)

    # Configuration
    print(f"\n{'CONFIGURATION':^100}")
    print("-" * 100)
    print(f"  Symbol: {config['symbol']}")
    print(f"  Timeframe: {config['timeframe']}")
    print(f"  Initial Margin: ${config['initial_capital']:,.2f}")
    print(f"  Leverage: {config.get('leverage', 'N/A')}x")
    print(f"  Max Position Size: ${config.get('max_position_size', config['initial_capital']):,.2f}")
    print(f"  Final Capital: ${config['final_capital']:,.2f}")
    print(f"  Maker Fee: {config['maker_fee']*100:.3f}%")

    # Performance Summary
    print(f"\n{'PERFORMANCE SUMMARY':^100}")
    print("-" * 100)

    return_pct = perf['return_pct']
    profit_factor = calculate_profit_factor(trades)
    sharpe = calculate_sharpe_ratio(trades)

    print(f"  Net P&L: ${perf['net_pnl']:,.2f}")
    print(f"  Return: {return_pct:.2f}%")
    print(f"  Total Fees: ${perf['total_fees']:,.2f}")
    print()
    print(f"  Total Trades: {perf['total_trades']}")
    print(f"  Winning Trades: {perf['winning_trades']} ({perf['win_rate']:.1f}%)")
    print(f"  Losing Trades: {perf['losing_trades']}")
    print()
    print(f"  Avg Win: ${perf['avg_win']:,.2f}")
    print(f"  Avg Loss: ${perf['avg_loss']:,.2f}")
    print(f"  Largest Win: ${perf['largest_win']:,.2f}")
    print(f"  Largest Loss: ${perf['largest_loss']:,.2f}")
    print()
    print(f"  Profit Factor: {profit_factor:.2f}")
    print(f"  Sharpe Ratio: {sharpe:.2f}")
    print(f"  Avg Trade Duration: {perf['avg_trade_duration_minutes']:.1f} minutes")

    # Order Stats
    print(f"\n{'ORDER STATISTICS':^100}")
    print("-" * 100)
    print(f"  Entry Fills: {order_stats['entry_fills']}")
    print(f"  Entry Timeouts: {order_stats['entry_timeouts']}")
    print(f"  TP Fills: {order_stats['tp_fills']}")
    print(f"  SL Fills: {order_stats['sl_fills']}")
    print(f"  Fill Rate: {(order_stats['entry_fills'] / (order_stats['entry_fills'] + order_stats['entry_timeouts']) * 100):.1f}%")

    # Long/Short Bias
    bias = analyze_long_short_bias(trades)
    print(f"\n{'LONG/SHORT ANALYSIS':^100}")
    print("-" * 100)
    print(f"  LONG Trades: {bias['long']['count']} | Wins: {bias['long']['wins']} | Win Rate: {bias['long']['win_rate']:.1f}% | P&L: ${bias['long']['total_pnl']:,.2f}")
    print(f"  SHORT Trades: {bias['short']['count']} | Wins: {bias['short']['wins']} | Win Rate: {bias['short']['win_rate']:.1f}% | P&L: ${bias['short']['total_pnl']:,.2f}")

    # Signal Analysis
    signal_analysis = analyze_signal_types(trades)
    print(f"\n{'EXIT ANALYSIS':^100}")
    print("-" * 100)
    print(f"  Take Profit Exits: {signal_analysis['tp_exits']['count']} | P&L: ${signal_analysis['tp_exits']['pnl']:,.2f}")
    print(f"  Stop Loss Exits: {signal_analysis['sl_exits']['count']} | P&L: ${signal_analysis['sl_exits']['pnl']:,.2f}")

    # Individual Trades
    print(f"\n{'INDIVIDUAL TRADES':^100}")
    print("-" * 100)
    print(f"{'#':<4} {'Time (IST)':<22} {'Dir':<6} {'Entry':<12} {'Exit':<12} {'P&L':<12} {'%':<8} {'Duration':<10} {'Reason':<6}")
    print("-" * 100)

    for i, trade in enumerate(trades, 1):
        entry_time = format_timestamp_ist(trade['entry_time'])
        entry_price = f"${trade['entry_price']:,.2f}"
        exit_price = f"${trade['exit_price']:,.2f}" if trade['exit_price'] else "N/A"
        pnl = f"${trade['pnl']:,.2f}" if trade['pnl'] else "N/A"
        pnl_pct = f"{trade['pnl_pct']:.2f}%" if trade['pnl_pct'] else "N/A"
        duration = f"{trade['duration_minutes']:.1f}m" if trade['duration_minutes'] else "N/A"
        reason = trade.get('exit_reason', 'N/A')

        # Color code P&L
        if trade['pnl'] and trade['pnl'] > 0:
            pnl_display = f"{pnl} ✓"
        elif trade['pnl'] and trade['pnl'] < 0:
            pnl_display = f"{pnl} ✗"
        else:
            pnl_display = pnl

        print(f"{i:<4} {entry_time:<22} {trade['direction']:<6} {entry_price:<12} {exit_price:<12} {pnl_display:<12} {pnl_pct:<8} {duration:<10} {reason:<6}")

    # Best and Worst Trades
    print(f"\n{'TOP 5 BEST TRADES':^100}")
    print("-" * 100)
    sorted_trades = sorted(trades, key=lambda t: t['pnl'] if t['pnl'] else 0, reverse=True)
    for i, trade in enumerate(sorted_trades[:5], 1):
        entry_time = format_timestamp_ist(trade['entry_time'])
        print(f"  {i}. {trade['direction']} | {entry_time} | P&L: ${trade['pnl']:,.2f} ({trade['pnl_pct']:.2f}%) | Duration: {trade['duration_minutes']:.1f}m")

    print(f"\n{'TOP 5 WORST TRADES':^100}")
    print("-" * 100)
    for i, trade in enumerate(sorted_trades[-5:][::-1], 1):
        entry_time = format_timestamp_ist(trade['entry_time'])
        print(f"  {i}. {trade['direction']} | {entry_time} | P&L: ${trade['pnl']:,.2f} ({trade['pnl_pct']:.2f}%) | Duration: {trade['duration_minutes']:.1f}m")

    print("\n" + "=" * 100)


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        # Load specified file
        filepath = sys.argv[1]
        if not Path(filepath).exists():
            print(f"[ERROR] File not found: {filepath}")
            sys.exit(1)
        results = load_results(filepath)
    else:
        # Load latest results
        results = load_latest_results()

    display_dashboard(results)


if __name__ == '__main__':
    main()
