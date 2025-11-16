import json
from datetime import datetime

print("="*80)
print("30-DAY BACKTEST COMPARISON: BASELINE VS ML-FILTERED")
print("="*80)
print()

# Load standalone 30-day baseline (no ML)
baseline_file = 'data/vwap_backtest/vwap_backtest_BTCUSDT_1763198486.json'
with open(baseline_file) as f:
    baseline_data = json.load(f)

baseline_config = baseline_data.get('backtest_config', {})
baseline_perf = baseline_data.get('performance', {})
baseline_trades = baseline_data.get('trades', [])

# Get baseline date range
if baseline_trades:
    baseline_first = datetime.fromtimestamp(baseline_trades[0]['entry_time']/1000).strftime('%Y-%m-%d')
    baseline_last = datetime.fromtimestamp(baseline_trades[-1]['entry_time']/1000).strftime('%Y-%m-%d')
else:
    baseline_first = baseline_last = 'N/A'

# Load ML-filtered 30-day backtest
ml_file = 'data/vwap_ml_backtest/vwap_backtest_BTCUSDT_1763221127.json'
with open(ml_file) as f:
    ml_data = json.load(f)

ml_config = ml_data.get('backtest_config', {})
ml_perf = ml_data.get('performance', {})
ml_trades = ml_data.get('trades', [])
ml_filter_stats = ml_data.get('ml_filtering_stats', {})

# Get ML date range
if ml_trades:
    ml_first = datetime.fromtimestamp(ml_trades[0]['entry_time']/1000).strftime('%Y-%m-%d')
    ml_last = datetime.fromtimestamp(ml_trades[-1]['entry_time']/1000).strftime('%Y-%m-%d')
else:
    ml_first = ml_last = 'N/A'

print("BASELINE (NO ML FILTER)")
print("-"*80)
print(f"File: {baseline_file}")
print(f"Period: {baseline_first} to {baseline_last}")
print(f"Total Trades: {baseline_perf.get('total_trades', 0)}")
print(f"Winners: {baseline_perf.get('winning_trades', 0)} | Losers: {baseline_perf.get('losing_trades', 0)}")
print(f"Win Rate: {baseline_perf.get('win_rate', 0):.2f}%")
print(f"")
print(f"Initial Capital: ${baseline_config.get('initial_capital', 100):.2f}")
print(f"Final Capital: ${baseline_config.get('final_capital', 0):.2f}")
print(f"Net PnL: ${baseline_perf.get('net_pnl', 0):.2f}")
print(f"Return: {baseline_perf.get('return_pct', 0):.2f}%")
print(f"Total Fees: ${baseline_perf.get('total_fees', 0):.2f}")
print()

print("ML-FILTERED (60% WIN PROBABILITY THRESHOLD)")
print("-"*80)
print(f"File: {ml_file}")
print(f"Period: {ml_first} to {ml_last}")
print(f"Total Trades: {ml_perf.get('total_trades', 0)}")
print(f"Winners: {ml_perf.get('winning_trades', 0)} | Losers: {ml_perf.get('losing_trades', 0)}")
print(f"Win Rate: {ml_perf.get('win_rate', 0):.2f}%")
print(f"")
print(f"Initial Capital: ${ml_config.get('initial_capital', 100):.2f}")
print(f"Final Capital: ${ml_config.get('final_capital', 0):.2f}")
print(f"Net PnL: ${ml_perf.get('net_pnl', 0):.2f}")
print(f"Return: {ml_perf.get('return_pct', 0):.2f}%")
print(f"Total Fees: ${ml_perf.get('total_fees', 0):.2f}")
print()
print(f"ML Filter Stats:")
print(f"  Signals Evaluated: {ml_filter_stats.get('signals_evaluated', 0)}")
print(f"  Signals Filtered: {ml_filter_stats.get('signals_filtered', 0)}")
print(f"  Filter Rate: {ml_filter_stats.get('filter_rate', 0):.1f}%")
print()

print("IMPROVEMENT")
print("-"*80)
trade_reduction = baseline_perf.get('total_trades', 0) - ml_perf.get('total_trades', 0)
trade_reduction_pct = (trade_reduction / baseline_perf.get('total_trades', 1)) * 100
wr_improvement = ml_perf.get('win_rate', 0) - baseline_perf.get('win_rate', 0)
pnl_improvement = ml_perf.get('net_pnl', 0) - baseline_perf.get('net_pnl', 0)
return_improvement = ml_perf.get('return_pct', 0) - baseline_perf.get('return_pct', 0)

print(f"Trades Reduced: {trade_reduction} ({trade_reduction_pct:.1f}% fewer)")
print(f"Win Rate Improvement: {wr_improvement:+.2f}%")
print(f"Net PnL Improvement: ${pnl_improvement:+.2f}")
print(f"Return Improvement: {return_improvement:+.2f}%")
print()

if ml_perf.get('win_rate', 0) >= 60.0:
    print("✅ ML TARGET ACHIEVED: Win Rate >= 60%")
else:
    print(f"❌ ML TARGET MISSED: Win Rate {ml_perf.get('win_rate', 0):.2f}% < 60%")

print()
print("="*80)

# Save comparison to file
with open('results/ml_vs_baseline_comparison.txt', 'w') as f:
    f.write("30-DAY BACKTEST COMPARISON: BASELINE VS ML-FILTERED\n")
    f.write("="*80 + "\n\n")
    f.write(f"Baseline: {baseline_file}\n")
    f.write(f"ML-Filtered: {ml_file}\n\n")
    f.write(f"{'Metric':<25} {'Baseline':>15} {'ML-Filtered':>15} {'Change':>15}\n")
    f.write("-"*80 + "\n")
    f.write(f"{'Period':<25} {baseline_first+' to '+baseline_last:>15} {ml_first+' to '+ml_last:>15} {'-':>15}\n")
    f.write(f"{'Total Trades':<25} {baseline_perf.get('total_trades', 0):>15} {ml_perf.get('total_trades', 0):>15} {trade_reduction:>15}\n")
    f.write(f"{'Win Rate (%)':<25} {baseline_perf.get('win_rate', 0):>15.2f} {ml_perf.get('win_rate', 0):>15.2f} {wr_improvement:>+15.2f}\n")
    f.write(f"{'Final Capital ($)':<25} {baseline_config.get('final_capital', 0):>15.2f} {ml_config.get('final_capital', 0):>15.2f} {ml_config.get('final_capital', 0)-baseline_config.get('final_capital', 0):>+15.2f}\n")
    f.write(f"{'Return (%)':<25} {baseline_perf.get('return_pct', 0):>15.2f} {ml_perf.get('return_pct', 0):>15.2f} {return_improvement:>+15.2f}\n")

print("\nComparison saved to: results/ml_vs_baseline_comparison.txt")
