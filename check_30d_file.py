import json
from datetime import datetime

file = 'data/vwap_backtest/vwap_backtest_BTCUSDT_1763198486.json'
with open(file) as f:
    data = json.load(f)

config = data.get('backtest_config', {})
perf = data.get('performance', {})

print('FILE:', file)
print('='*70)
print('Trades:', perf.get('total_trades'))
print('Win Rate: %.2f%%' % perf.get('win_rate'))
print('Winners:', perf.get('winning_trades'), '| Losers:', perf.get('losing_trades'))
print()
print('Initial Capital: $%.2f' % config.get('initial_capital', 100))
print('Final Capital: $%.2f' % config.get('final_capital'))
print('Net PnL: $%.2f' % perf.get('net_pnl'))
print('Return: %.2f%%' % perf.get('return_pct'))
print('Total Fees: $%.2f' % perf.get('total_fees'))
print('='*70)

# Check first and last trade dates
trades = data.get('trades', [])
if trades:
    first = datetime.fromtimestamp(trades[0]['entry_time']/1000).strftime('%Y-%m-%d')
    last = datetime.fromtimestamp(trades[-1]['entry_time']/1000).strftime('%Y-%m-%d')
    print('Period: %s to %s' % (first, last))
    days = (trades[-1]['entry_time'] - trades[0]['entry_time']) / 1000 / 86400
    print('Duration: %.1f days' % days)
