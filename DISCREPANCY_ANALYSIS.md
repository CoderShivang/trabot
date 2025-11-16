# BACKTEST DISCREPANCY ANALYSIS

## The Mystery

User observations:
- **OLD 180d test** (May 19 - Nov 15): ~900 trades total, 45-47% WR, realistic growth
- **NEW 180d test** (Feb 18 - Aug 17): 1000+ trades at 38% complete, 73% WR, unrealistic growth

## Key Finding: DIFFERENT TIME PERIODS

**OLD Test**: May 19 - Nov 15, 2025
**NEW Test**: Feb 18 - Aug 17, 2025

These are COMPLETELY different 6-month periods!

## What I Verified (NO CHANGES):

✅ **Strategy code**: IDENTICAL
- Confidence threshold: 50% (both)
- Min zone strength: 20 (both)
- Signal generation logic: IDENTICAL
- No logic changes in commit 2b986ca (only ML feature collection)

✅ **Position sizing**: CHANGED (but this explains growth, not win rate)
- OLD: Tiered with cap at $1600
- NEW: Full compounding (this causes faster capital growth)

## What I CANNOT Explain:

❌ **Win Rate Jump**: 47% → 73%
- Position sizing doesn't affect win rate
- Strategy logic is identical
- Only the TIME PERIOD changed

❌ **Trade Density**: ~5 trades/day → ~15 trades/day
- OLD: 900 trades / 180 days = 5 trades/day
- NEW: 1000 trades / 68 days = 14.7 trades/day
- 3x more trade density!

## Possible Causes:

### Theory 1: Market Regime Difference
- Feb-Aug 2025 might have had stronger trending conditions
- More VWAP band touches
- More S/R zone activations
- This would explain BOTH more trades AND higher win rate

### Theory 2: Data Quality Issue
- Are we getting different data from Binance for this period?
- Could there be gaps or anomalies in Feb-Aug data?

### Theory 3: Hidden Bug
- Is there a bug causing duplicate signal generation?
- Is there a bug in how positions are tracked?
- Is the progress bar showing wrong numbers?

## Recommendation:

**STOP the backtest and investigate:**

1. Check the actual JSON file from the OLD test
   - What were the exact dates?
   - What was the actual trade count?
   - What was the actual win rate?

2. Check if there's a data issue
   - Are we getting proper 1m candles for Feb-Aug?
   - Any gaps or missing data?

3. Add debug logging to count:
   - How many signals are generated
   - How many are filtered out
   - How many result in trades

Without seeing the OLD backtest results file, I cannot definitively say what changed.
