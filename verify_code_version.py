"""
Quick script to verify you're running the latest code with the infinite loop fixes.

Run this before running the backtest to ensure you have the correct version.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def check_logger_level():
    """Check if logger is set to DEBUG level"""
    from utils.logger import setup_logger
    import logging

    logger = setup_logger('test')
    level = logger.level

    if level == logging.DEBUG:
        print("✓ Logger level: DEBUG (CORRECT)")
        return True
    else:
        print(f"✗ Logger level: {logging.getLevelName(level)} (WRONG - should be DEBUG)")
        print("  → You may be running old code!")
        return False

def check_for_duplicate_call():
    """Check if the duplicate update_trade_history call was removed"""
    backtest_file = Path(__file__).parent / 'src' / 'backtesting' / 'backtest_engine.py'

    with open(backtest_file, 'r') as f:
        content = f.read()

    # Check if the problematic line exists
    if 'self.big_orders_detector.update_trade_history(symbol, recent_trades)' in content:
        print("✗ Duplicate update_trade_history call STILL EXISTS!")
        print("  → You are running OLD CODE with the infinite loop bug!")
        return False
    else:
        print("✓ Duplicate update_trade_history call removed (CORRECT)")
        return True

def check_for_new_logs():
    """Check if new logging messages exist"""
    backtest_file = Path(__file__).parent / 'src' / 'backtesting' / 'backtest_engine.py'

    with open(backtest_file, 'r') as f:
        content = f.read()

    # Check for the new emoji logs
    if '⚡ Evaluating candle' in content:
        print("✓ New logging messages found (CORRECT)")
        return True
    else:
        print("✗ New logging messages NOT FOUND!")
        print("  → You are running OLD CODE!")
        return False

def main():
    print("=" * 80)
    print("TRABOT CODE VERSION VERIFICATION")
    print("=" * 80)
    print()

    results = []

    print("Checking logger configuration...")
    results.append(check_logger_level())
    print()

    print("Checking for infinite loop fix...")
    results.append(check_for_duplicate_call())
    print()

    print("Checking for new logging messages...")
    results.append(check_for_new_logs())
    print()

    print("=" * 80)
    if all(results):
        print("✓✓✓ ALL CHECKS PASSED ✓✓✓")
        print()
        print("You are running the LATEST CODE with all fixes applied!")
        print("The backtest should work correctly now.")
        print()
        print("When you run the backtest, you should see:")
        print("  - [INFO] ⚡ Evaluating candle 0 @ $XXX.XX")
        print("  - [INFO] ✓ Scoring complete for candle 0: LONG=XX.X, SHORT=XX.X")
        print("  - [INFO] ✓ Candle 0 evaluation complete")
        print()
        print("If you DON'T see these emoji (⚡ and ✓) logs, you're still running old code!")
    else:
        print("✗✗✗ SOME CHECKS FAILED ✗✗✗")
        print()
        print("ACTION REQUIRED:")
        print("1. Make sure you're in the correct directory (C:\\Users\\shivang\\trabot)")
        print("2. Pull the latest code:")
        print("   git fetch origin")
        print("   git checkout claude/review-trading-bot-core-011CV24WM17Tzp4z7qgxXg8g")
        print("   git pull origin claude/review-trading-bot-core-011CV24WM17Tzp4z7qgxXg8g")
        print("3. Clear Python cache:")
        print("   Get-ChildItem -Path . -Include *.pyc -Recurse -Force | Remove-Item -Force")
        print("   Get-ChildItem -Path . -Include __pycache__ -Recurse -Force | Remove-Item -Recurse -Force")
        print("4. Run this script again to verify")
    print("=" * 80)

if __name__ == '__main__':
    main()
