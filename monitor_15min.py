"""
Monitor 180-day training backtest every 15 minutes
Alerts if buggy capital values appear
"""

import time
import re
from datetime import datetime

LOG_FILE = "C:/Users/shivang/trabot/training_180d_progress.log"
CHECK_INTERVAL = 900  # 15 minutes in seconds
CAPITAL_ALERT_THRESHOLD = 500  # Alert if capital > $500 (indicates bug)

def get_latest_progress():
    """Extract latest progress from log file"""
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # Find last line with "Backtesting:" and capital info
        for line in reversed(lines):
            if 'Backtesting:' in line and 'Capital=' in line:
                # Extract progress percentage
                pct_match = re.search(r'(\d+)%', line)
                # Extract bar count
                bar_match = re.search(r'(\d+)/(\d+)', line)
                # Extract trades
                trades_match = re.search(r'Trades=(\d+)', line)
                # Extract capital
                capital_match = re.search(r'Capital=\$(\d+)', line)

                if pct_match and bar_match and capital_match:
                    pct = int(pct_match.group(1))
                    current_bar = int(bar_match.group(1))
                    total_bars = int(bar_match.group(2))
                    trades = int(trades_match.group(1)) if trades_match else 0
                    capital = int(capital_match.group(1))

                    return {
                        'percent': pct,
                        'current_bar': current_bar,
                        'total_bars': total_bars,
                        'trades': trades,
                        'capital': capital,
                        'found': True
                    }

        return {'found': False}
    except FileNotFoundError:
        return {'found': False, 'error': 'Log file not found'}
    except Exception as e:
        return {'found': False, 'error': str(e)}

def print_status(progress):
    """Print formatted status"""
    print("=" * 80)
    print(f"180-DAY TRAINING BACKTEST - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    if not progress.get('found'):
        print(f"❌ No progress data found")
        if 'error' in progress:
            print(f"   Error: {progress['error']}")
    else:
        pct = progress['percent']
        current = progress['current_bar']
        total = progress['total_bars']
        trades = progress['trades']
        capital = progress['capital']

        print(f"Progress: {pct}% ({current:,} / {total:,} bars)")
        print(f"Trades: {trades}")
        print(f"Capital: ${capital}")

        # Check for buggy capital values
        if capital > CAPITAL_ALERT_THRESHOLD:
            print("")
            print("🚨 WARNING: BUGGY CAPITAL DETECTED! 🚨")
            print(f"   Capital ${capital} exceeds threshold ${CAPITAL_ALERT_THRESHOLD}")
            print("   Old buggy code may be running!")
            print("   Tiered sizing should keep capital < $500")
        else:
            print("✅ Capital in expected range (tiered sizing working)")

        # ETA estimation
        if pct > 0:
            bars_remaining = total - current
            # Estimate ~17 bars/sec based on current speed
            seconds_remaining = bars_remaining / 17
            hours_remaining = seconds_remaining / 3600
            print(f"ETA: ~{hours_remaining:.1f} hours remaining")

    print("=" * 80)
    print("")

def monitor():
    """Monitor backtest every 15 minutes"""
    print("🔍 Starting 180-day backtest monitor")
    print(f"Checking every 15 minutes for buggy capital values...")
    print(f"Alert threshold: ${CAPITAL_ALERT_THRESHOLD}")
    print("")

    update_count = 0

    try:
        while True:
            update_count += 1
            progress = get_latest_progress()
            print_status(progress)

            # Check if completed
            if progress.get('found') and progress['percent'] >= 100:
                print("✅ Backtest completed!")
                break

            # Wait 15 minutes before next check
            if update_count == 1:
                print("Next check in 15 minutes...")
            else:
                print(f"Next check in 15 minutes... (Update #{update_count})")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n⛔ Monitoring stopped by user")

if __name__ == "__main__":
    monitor()
