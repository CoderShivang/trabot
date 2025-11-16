"""
Diagnostic script to identify the capital growth bug

Analyzes backtest results to find abnormal position sizing or PnL
"""

import json
import sys
from pathlib import Path

def analyze_backtest(results_file):
    """Analyze backtest results for abnormal patterns"""

    with open(results_file, 'r') as f:
        results = json.load(f)

    trades = results.get('trades', [])
    config = results.get('backtest_config', {})

    print(f"\n{'='*100}")
    print(f"DIAGNOSTIC ANALYSIS: {Path(results_file).name}")
    print(f"{'='*100}\n")

    print(f"Config:")
    print(f"  Initial Capital: ${config.get('initial_capital', 0):.2f}")
    print(f"  Final Capital: ${config.get('final_capital', 0):.2f}")
    print(f"  Leverage: {config.get('leverage', 0)}x")
    print(f"  Total Trades: {len(trades)}\n")

    # Track capital over time
    capital = config.get('initial_capital', 100)

    print(f"{'Trade':<6} {'Entry $':<10} {'Exit $':<10} {'Qty':<12} {'Notional $':<12} {'PnL $':<10} {'Capital $':<12} {'Reason'}")
    print(f"{'-'*100}")

    abnormal_trades = []

    for i, trade in enumerate(trades[:50], 1):  # Analyze first 50 trades
        entry_price = trade.get('entry_price', 0)
        exit_price = trade.get('exit_price', 0)
        quantity = trade.get('quantity', 0)
        pnl = trade.get('pnl', 0)
        exit_reason = trade.get('exit_reason', '')

        notional = quantity * entry_price
        capital += pnl

        # Flag abnormal trades
        is_abnormal = False
        abnormal_reasons = []

        # Check for huge position size relative to capital
        if notional > capital * 50:  # Position is 50x capital
            is_abnormal = True
            abnormal_reasons.append(f"HUGE POSITION: {notional/capital:.1f}x capital")

        # Check for huge PnL
        if abs(pnl) > capital * 0.5:  # PnL is > 50% of capital
            is_abnormal = True
            abnormal_reasons.append(f"HUGE PNL: {abs(pnl)/capital*100:.1f}% of capital")

        # Check for small stop distance
        stop_loss = trade.get('stop_loss', 0)
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance > 0 and stop_distance < entry_price * 0.001:  # Stop < 0.1% of price
            is_abnormal = True
            abnormal_reasons.append(f"TINY STOP: ${stop_distance:.2f}")

        marker = "⚠️ " if is_abnormal else "   "

        print(f"{marker}{i:<5} ${entry_price:<9,.0f} ${exit_price:<9,.0f} {quantity:<12.6f} ${notional:<11,.0f} ${pnl:<9.2f} ${capital:<11,.2f} {exit_reason}")

        if is_abnormal:
            abnormal_trades.append((i, abnormal_reasons))
            for reason in abnormal_reasons:
                print(f"       └─> {reason}")

    print(f"\n{'='*100}")
    print(f"SUMMARY")
    print(f"{'='*100}\n")

    if abnormal_trades:
        print(f"🚨 Found {len(abnormal_trades)} abnormal trades:")
        for trade_num, reasons in abnormal_trades[:10]:
            print(f"\n  Trade #{trade_num}:")
            for reason in reasons:
                print(f"    - {reason}")
    else:
        print("✅ No obvious abnormalities detected in first 50 trades")

    print(f"\nCapital progression: ${config.get('initial_capital', 0):.2f} → ${capital:.2f}")
    print(f"Return: {((capital / config.get('initial_capital', 100)) - 1) * 100:.2f}%\n")

if __name__ == "__main__":
    # Find most recent backtest results
    results_dir = Path('data/vwap_backtest')

    if results_dir.exists():
        json_files = sorted(results_dir.glob('vwap_backtest_*.json'), key=lambda x: x.stat().st_mtime, reverse=True)

        if json_files:
            print(f"\nFound {len(json_files)} backtest result files")
            print(f"Analyzing most recent: {json_files[0].name}\n")
            analyze_backtest(json_files[0])
        else:
            print("No backtest results found in data/vwap_backtest/")
    else:
        print("Backtest results directory not found")
        print("\nUsage: python diagnose_capital_bug.py [results_file.json]")

    # Also check ML backtest results
    ml_results_dir = Path('data/vwap_ml_backtest')

    if ml_results_dir.exists():
        json_files = sorted(ml_results_dir.glob('vwap_backtest_*.json'), key=lambda x: x.stat().st_mtime, reverse=True)

        if json_files:
            print(f"\n\nFound {len(json_files)} ML backtest result files")
            print(f"Analyzing most recent: {json_files[0].name}\n")
            analyze_backtest(json_files[0])
