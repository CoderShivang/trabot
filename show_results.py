import json
import sys

file_path = sys.argv[1] if len(sys.argv) > 1 else 'data/vwap_backtest/vwap_backtest_BTCUSDT_1763187622.json'

with open(file_path) as f:
    data = json.load(f)

print("=" * 80)
print(f" {data['backtest_config']['timeframe'].upper()} TIMEFRAME - 30 DAY BACKTEST RESULTS")
print("=" * 80)
print(f"Initial Capital: ${data['backtest_config']['initial_capital']:.2f}")
print(f"Final Capital: ${data['backtest_config']['final_capital']:.2f}")
print(f"Leverage: {data['backtest_config']['leverage']}x")
print()

p = data['performance']
print("PERFORMANCE SUMMARY:")
print("-" * 80)
print(f"Total Trades: {p['total_trades']}")
print(f"Winners: {p['winning_trades']} | Losers: {p['losing_trades']}")
print(f"Win Rate: {p['win_rate']:.2f}% (Target: 60%)")
print()
print(f"Net PnL: ${p['net_pnl']:.2f}")
print(f"Return: {p['return_pct']:.2f}%")
print()
print(f"Avg Win: ${p['avg_win']:.2f} | Avg Loss: ${p['avg_loss']:.2f}")
print(f"Largest Win: ${p['largest_win']:.2f} | Largest Loss: ${p['largest_loss']:.2f}")
print()
print(f"Total Fees: ${p['total_fees']:.2f}")
print(f"Avg Trade Duration: {p['avg_trade_duration_minutes']:.1f} minutes")
print("=" * 80)

if p['win_rate'] >= 60.0:
    print(f"✓ WIN RATE TARGET ACHIEVED: {p['win_rate']:.2f}% >= 60%")
else:
    print(f"✗ WIN RATE TARGET MISSED: {p['win_rate']:.2f}% < 60%")
print()
