"""
Comprehensive VWAP ML Backtests Runner

Runs backtests across all timeframes (1m, 5m, 15m) for 30 days
with relaxed parameters for higher timeframes.

Usage:
    python run_comprehensive_ml_backtests.py
"""

import asyncio
import subprocess
import json
import os
from datetime import datetime
from pathlib import Path

# Relaxed parameters for different timeframes
TIMEFRAME_CONFIGS = {
    '1m': {
        'timeframe': '1m',
        'target': 200,
        'stop': 150,
        'band_proximity': 300,
        'zone_proximity': 500,
        'min_zone_strength': 70
    },
    '5m': {
        'timeframe': '5m',
        'target': 250,
        'stop': 180,
        'band_proximity': 400,  # Relaxed
        'zone_proximity': 600,  # Relaxed
        'min_zone_strength': 60  # Relaxed
    },
    '15m': {
        'timeframe': '15m',
        'target': 300,
        'stop': 200,
        'band_proximity': 500,  # More relaxed
        'zone_proximity': 700,  # More relaxed
        'min_zone_strength': 50  # More relaxed
    }
}

def run_backtest(timeframe: str, days: int = 30):
    """Run a single backtest with specific timeframe configuration"""
    config = TIMEFRAME_CONFIGS[timeframe]

    print(f"\n{'='*80}")
    print(f"Running {timeframe} backtest (30 days)")
    print(f"Config: {config}")
    print(f"{'='*80}\n")

    cmd = [
        'python', 'run_vwap_backtest.py',
        '--symbol', 'BTCUSDT',
        '--timeframe', config['timeframe'],
        '--days', str(days),
        '--capital', '100',
        '--leverage', '20',
        '--risk', '0.02',
        '--target', str(config['target']),
        '--stop', str(config['stop']),
        '--band-proximity', str(config['band_proximity']),
        '--zone-proximity', str(config['zone_proximity']),
        '--min-zone-strength', str(config['min_zone_strength'])
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR running {timeframe} backtest:")
        print(result.stderr)
        return None

    print(result.stdout)
    return result

def find_latest_result_file(timeframe: str):
    """Find the most recent backtest result file for a given timeframe"""
    results_dir = Path('data/vwap_backtest')

    if not results_dir.exists():
        return None

    # Find all JSON files for this symbol and timeframe
    pattern = f"vwap_backtest_BTCUSDT_*.json"
    files = list(results_dir.glob(pattern))

    if not files:
        return None

    # Get the most recent file
    latest_file = max(files, key=lambda p: p.stat().st_mtime)

    # Load and check if it matches our timeframe
    try:
        with open(latest_file, 'r') as f:
            data = json.load(f)
            if data.get('backtest_config', {}).get('timeframe') == timeframe:
                return latest_file
    except:
        pass

    return None

def generate_comparison_report():
    """Generate comprehensive comparison report"""
    print("\n" + "="*80)
    print(" COMPREHENSIVE BACKTEST RESULTS - 30 DAYS")
    print("="*80 + "\n")

    results = {}

    for tf in ['1m', '5m', '15m']:
        result_file = find_latest_result_file(tf)

        if result_file:
            with open(result_file, 'r') as f:
                data = json.load(f)
                results[tf] = data
        else:
            print(f"Warning: No result file found for {tf}")

    if not results:
        print("No results found!")
        return

    # Print detailed comparison
    print(f"{'Metric':<30} {'1min':<20} {'5min':<20} {'15min':<20}")
    print("-" * 90)

    metrics_to_compare = [
        ('Final Balance ($)', lambda d: f"${d['backtest_config']['final_capital']:.2f}"),
        ('Net PnL ($)', lambda d: f"${d['performance']['net_pnl']:.2f}"),
        ('Return (%)', lambda d: f"{d['performance']['return_pct']:.2f}%"),
        ('Total Trades', lambda d: str(d['performance']['total_trades'])),
        ('Win Rate (%)', lambda d: f"{d['performance']['win_rate']:.2f}%"),
        ('Winners', lambda d: str(d['performance']['winning_trades'])),
        ('Losers', lambda d: str(d['performance']['losing_trades'])),
        ('Avg Win ($)', lambda d: f"${d['performance']['avg_win']:.2f}"),
        ('Avg Loss ($)', lambda d: f"${d['performance']['avg_loss']:.2f}"),
        ('Largest Win ($)', lambda d: f"${d['performance']['largest_win']:.2f}"),
        ('Largest Loss ($)', lambda d: f"${d['performance']['largest_loss']:.2f}"),
        ('Total Fees ($)', lambda d: f"${d['performance']['total_fees']:.2f}"),
        ('Avg Duration (min)', lambda d: f"{d['performance']['avg_trade_duration_minutes']:.1f}"),
    ]

    for metric_name, metric_func in metrics_to_compare:
        row = [metric_name]
        for tf in ['1m', '5m', '15m']:
            if tf in results:
                try:
                    value = metric_func(results[tf])
                    row.append(value)
                except:
                    row.append('N/A')
            else:
                row.append('N/A')
        print(f"{row[0]:<30} {row[1]:<20} {row[2]:<20} {row[3]:<20}")

    print("="*90)

    # Find best performing timeframe
    best_return = None
    best_tf = None
    best_wr = None
    best_wr_tf = None

    for tf, data in results.items():
        return_pct = data['performance']['return_pct']
        win_rate = data['performance']['win_rate']

        if best_return is None or return_pct > best_return:
            best_return = return_pct
            best_tf = tf

        if best_wr is None or win_rate > best_wr:
            best_wr = win_rate
            best_wr_tf = tf

    print("\nKEY INSIGHTS:")
    if best_tf:
        print(f"  Best Return: {best_tf.upper()} ({best_return:.2f}%)")
    if best_wr_tf:
        print(f"  Best Win Rate: {best_wr_tf.upper()} ({best_wr:.2f}%)")

    # Check which timeframes meet the 60% win rate target
    print("\nWIN RATE TARGET (60%):")
    for tf, data in results.items():
        wr = data['performance']['win_rate']
        status = "✓ ACHIEVED" if wr >= 60.0 else "✗ MISSED"
        print(f"  {tf.upper()}: {wr:.2f}% - {status}")

    # Save comprehensive report
    report_file = f"data/vwap_backtest/comprehensive_report_{int(datetime.now().timestamp())}.json"
    os.makedirs('data/vwap_backtest', exist_ok=True)

    report = {
        'timestamp': datetime.now().isoformat(),
        'duration_days': 30,
        'results_by_timeframe': results,
        'best_return': {'timeframe': best_tf, 'return_pct': best_return},
        'best_win_rate': {'timeframe': best_wr_tf, 'win_rate': best_wr}
    }

    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\nReport saved to: {report_file}")
    print("="*90 + "\n")

def main():
    print("\n" + "="*80)
    print(" VWAP STRATEGY - COMPREHENSIVE 30-DAY BACKTESTS")
    print("="*80)
    print("\nRunning backtests for:")
    print("  - 1m timeframe (standard parameters)")
    print("  - 5m timeframe (relaxed parameters)")
    print("  - 15m timeframe (more relaxed parameters)")
    print("\nThis will take several minutes...")
    print("="*80 + "\n")

    # Run backtests sequentially
    for timeframe in ['1m', '5m', '15m']:
        run_backtest(timeframe, days=30)

    # Generate comparison report
    generate_comparison_report()

    print("\n✓ All backtests complete!")

if __name__ == "__main__":
    main()
