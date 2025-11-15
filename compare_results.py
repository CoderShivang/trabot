import json
import sys

# Read three backtest results files
files = [
    ("1min", "data/vwap_backtest/vwap_backtest_BTCUSDT_1763183158.json"),
    ("5min", "data/vwap_backtest/vwap_backtest_BTCUSDT_1763183823.json"),
    ("15min", "data/vwap_backtest/vwap_backtest_BTCUSDT_1763183825.json"),
]

print("\n" + "="*80)
print(" VWAP STRATEGY BACKTEST COMPARISON - BTCUSDT (7 Days)")
print("="*80 + "\n")

results = []
for label, filepath in files:
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            c = data['backtest_config']
            p = data['performance']
            results.append((label, c, p))
    except Exception as e:
        print(f"Error reading {label}: {e}")
        continue

# Print detailed results for each timeframe
for label, c, p in results:
    print(f"\n{label.upper()} TIMEFRAME RESULTS:")
    print("-" * 80)
    print(f"Timeframe: {c['timeframe']} | Capital: ${c['initial_capital']} | Leverage: {c['leverage']}x")
    print(f"Final Balance: ${c['final_capital']:.2f}")
    print(f"Net PnL: ${p['net_pnl']:.2f} ({p['return_pct']:.2f}%)")
    print(f"\nTrading Stats:")
    print(f"  Total Trades: {p['total_trades']}")
    print(f"  Winners: {p['winning_trades']} | Losers: {p['losing_trades']}")
    print(f"  Win Rate: {p['win_rate']:.2f}%")
    print(f"  Avg Win: ${p['avg_win']:.2f} | Avg Loss: ${p['avg_loss']:.2f}")
    print(f"  Largest Win: ${p['largest_win']:.2f} | Largest Loss: ${p['largest_loss']:.2f}")
    print(f"  Avg Trade Duration: {p['avg_trade_duration_minutes']:.1f} min")
    print(f"  Total Fees: ${p['total_fees']:.2f}")
    print()

# Print comparison table
print("\n" + "="*80)
print(" COMPARISON TABLE")
print("="*80)
print(f"{'Metric':<30} {'1min':<15} {'5min':<15} {'15min':<15}")
print("-" * 80)

metrics = [
    ("Final Balance ($)", lambda c, p: f"${c['final_capital']:.2f}"),
    ("Net PnL ($)", lambda c, p: f"${p['net_pnl']:.2f}"),
    ("Return (%)", lambda c, p: f"{p['return_pct']:.2f}%"),
    ("Total Trades", lambda c, p: str(p['total_trades'])),
    ("Win Rate (%)", lambda c, p: f"{p['win_rate']:.2f}%"),
    ("Avg Win ($)", lambda c, p: f"${p['avg_win']:.2f}"),
    ("Avg Loss ($)", lambda c, p: f"${p['avg_loss']:.2f}"),
    ("Total Fees ($)", lambda c, p: f"${p['total_fees']:.2f}"),
    ("Avg Duration (min)", lambda c, p: f"{p['avg_trade_duration_minutes']:.1f}"),
]

for metric_name, metric_func in metrics:
    row = [metric_name]
    for label, c, p in results:
        row.append(metric_func(c, p))
    print(f"{row[0]:<30} {row[1]:<15} {row[2]:<15} {row[3]:<15}")

print("="*80 + "\n")

# Print best performing timeframe
best_pnl = max(results, key=lambda x: x[2]['net_pnl'])
best_wr = max(results, key=lambda x: x[2]['win_rate'])

print("INSIGHTS:")
print(f"  Best PnL: {best_pnl[0].upper()} (${best_pnl[2]['net_pnl']:.2f})")
print(f"  Best Win Rate: {best_wr[0].upper()} ({best_wr[2]['win_rate']:.2f}%)")
print()
