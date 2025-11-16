"""
Analyze the failed backtest to extract win rate
"""
import re

log_file = "C:/Users/shivang/trabot/training_180d_progress.log"

# Find all completed trades in the log
wins = 0
losses = 0

with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        # Look for trade closure messages (wins have positive P&L, losses negative)
        # Pattern: [INFO] [EXIT] ... PnL=$X.XX or similar
        if '[EXIT]' in line or 'Trade closed' in line:
            # Try to find if it's a win or loss
            if 'PnL=$' in line or 'pnl=' in line.lower():
                # Extract PnL value
                pnl_match = re.search(r'[Pp]n[Ll]=?\$?(-?\d+\.?\d*)', line)
                if pnl_match:
                    pnl = float(pnl_match.group(1))
                    if pnl > 0:
                        wins += 1
                    else:
                        losses += 1

total_trades = wins + losses
win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

print("=" * 70)
print("FAILED BACKTEST ANALYSIS (Capital grew from $100 to $6294 at 9%)")
print("=" * 70)
print(f"Total Trades Analyzed: {total_trades}")
print(f"Winners: {wins}")
print(f"Losers: {losses}")
print(f"Win Rate: {win_rate:.2f}%")
print()
print(f"Capital Gain: ${6294 - 100:.2f} (6194%)")
print(f"Average P&L per trade: ${(6294-100)/430:.2f}") if total_trades > 0 else None
print("=" * 70)
