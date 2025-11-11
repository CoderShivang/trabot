# Backtest Guide - Offline Mode

## Quick Start

### Step 1: Download Historical Data (ONE-TIME with VPN)

```bash
# Connect to VPN in allowed location (US, EU, etc.)
python src/download_data.py BTCUSDT --start 2025-11-04 --end 2025-11-05
```

This will:
- Download 1m, 15m, and 1h candles
- Save to `data/cache/BTCUSDT_20251104_20251105.json`
- Can be run offline afterwards

### Step 2: Run Offline Backtest (NO VPN NEEDED)

```bash
# Run backtest using cached data
python src/run_backtest.py BTCUSDT --start 2025-11-04 --end 2025-11-05 --offline
```

---

## What Was Fixed

### 🐛 Critical Bug #1: LONG = SHORT Scores (FIXED)

**Problem:** Both directions got identical scores in mixed market conditions

**Root Cause:**
```
Mixed Market: Price > VWAP, EMA50 < EMA200
- LONG: 20 (VWAP) + 10 (EMA counter) = 30 points
- SHORT: 5 (VWAP counter) + 25 (EMA) = 30 points  ← IDENTICAL!
```

**Solution:** Complete rewrite of directional scoring logic
- Now calculates separate bullish_score and bearish_score
- Awards the appropriate score based on direction
- Heavily penalizes counter-trend trades (0.3x multiplier)

**New Behavior:**
```
Strong Bullish (Price > VWAP, EMA50 > EMA200):
- LONG: 60 points (aligned)
- SHORT: 0 points (penalized)

Strong Bearish (Price < VWAP, EMA50 < EMA200):
- LONG: 0 points (penalized)
- SHORT: 60 points (aligned)

Mixed (Price > VWAP, EMA50 < EMA200):
- LONG: 7.5 points (25 * 0.3 counter-trend penalty)
- SHORT: 35 points (aligned with EMA trend)
```

**File Changed:** `src/strategy/clc_engine.py:66-106`

---

### 🚫 Critical Bug #2: Geo-Restriction Blocking Backtests (FIXED)

**Problem:** Your location blocks all Binance API access

**Solution:** Implemented offline backtesting system
1. Created `src/download_data.py` - Downloads and caches historical data
2. Modified `BacktestEngine` to support offline mode
3. Added `--offline` flag to `run_backtest.py`

**Usage:**
```bash
# ONE-TIME: Download data with VPN
python src/download_data.py BTCUSDT --start 2025-11-04 --end 2025-11-05

# ANYTIME: Run offline backtest
python src/run_backtest.py BTCUSDT --start 2025-11-04 --end 2025-11-05 --offline
```

---

### 📊 Issue #3: Confirmation Signals Always 0 (FIXED)

**Problem:** Simulated orderbook can't generate realistic orderflow

**Why It Happened:**
- Backtest simulates balanced orderbook (50/50 bid/ask)
- Threshold was 0.7 (70% imbalance required)
- Simulated data never reached this threshold

**Solution:**
- Lowered thresholds: `imbalance_threshold: 0.55`, `delta_threshold: 0.52`
- Set `min_signals_required: 0` for backtesting
- Added note to increase to 2+ for live trading

**File Changed:** `config/bot_config.yaml:30-35`

---

### 🎯 Issue #4: Min Entry Score Too High (FIXED)

**Problem:** `min_entry_score: 50` was unreachable with new scoring

**Calculation:**
```
Max possible score with new system:
- Context: 60 points * 0.25 weight = 15
- Location: 40 points * 0.40 weight = 16
- Confirmation: 0 (optional in backtest)
- Big Orders: 0 (rare)
Total: ~31 points maximum
```

**Solution:** Lowered `min_entry_score: 20` (realistic for good setups)

**File Changed:** `config/bot_config.yaml:49`

---

## Configuration Changes Summary

```yaml
# OLD VALUES:
confirmation:
  min_signals_required: 1
  imbalance_threshold: 0.7
  delta_threshold: 0.6

scoring:
  min_entry_score: 50.0

# NEW VALUES:
confirmation:
  min_signals_required: 0  # For backtesting only
  imbalance_threshold: 0.55  # Adjusted for simulated data
  delta_threshold: 0.52

scoring:
  min_entry_score: 20.0  # Aligned with new scoring system

# IMPORTANT: For live trading, change min_signals_required back to 2+
```

---

## Testing Next Steps

### 1. Download Test Data (with VPN)

```bash
# Download 3 days of data
python src/download_data.py BTCUSDT --start 2025-11-04 --end 2025-11-07
```

### 2. Run Offline Backtest

```bash
# Test the fixed strategy
python src/run_backtest.py BTCUSDT --start 2025-11-04 --end 2025-11-07 --offline
```

### 3. Expected Improvements

With the fixes, you should now see:

✅ **Different LONG vs SHORT scores**
- Check that context scores differ based on market conditions
- LONG favored in bullish markets, SHORT in bearish

✅ **Actual trades executed**
- With min_entry_score=20, trades should occur at good setups
- Check win rate, profit factor, ROE

✅ **Reasonable trade frequency**
- Not 105 trades/day (old overtrading)
- Not 0 trades (old undersensitive)
- Target: 5-15 trades/day depending on volatility

✅ **Directional diversity**
- Should see both LONG and SHORT trades
- Distribution depends on market trend during test period

---

## Debug Logging

The system now includes extensive debug logging. Check the output for:

```
[CLC] Evaluating LONG @ price=105000.00, vwap=104800.00, ema50=104500.00, ema200=103000.00
[CLC] LONG: bullish=60, bearish=0, final_ctx=60.0
[CLC] Evaluating SHORT @ price=105000.00, vwap=104800.00, ema50=104500.00, ema200=103000.00
[CLC] SHORT: bullish=60, bearish=0, final_ctx=0.0
```

This confirms directional scoring is working correctly.

---

## Commit Hash

All fixes pushed to: **c20125b**

Branch: `claude/review-trading-bot-core-011CV24WM17Tzp4z7qgxXg8g`

---

## Known Limitations (Backtest vs Live)

### Backtest Limitations:
1. **Simulated Orderbook** - Can't replicate real orderflow nuances
2. **No Slippage Model** - Assumes perfect fills at target prices
3. **Confirmation Signals Disabled** - Set min_signals_required=0
4. **No Spoofing Detection** - Would need real orderbook state changes

### For Live Trading:
- Restore `min_signals_required: 2` (real orderflow will trigger signals)
- Monitor first trades closely to validate strategy
- Start with smaller position sizes until validated
- Consider paper trading on testnet first

---

## Questions?

If backtest still shows issues:
1. Share the output logs (first 200 lines)
2. Check `results/` folder for trade details
3. Review equity curve in `results/equity_*.csv`
