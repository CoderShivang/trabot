# Capital Growth Bug - Root Cause & Fix

## Problem
180-day backtest shows unrealistic capital growth: $100 → $5,000 at just 8% completion (~14 days).

## Root Causes

### 1. No Minimum Stop Distance Validation
**Current Code** (vwap_backtest_engine.py:552-561):
```python
risk_amount = position_base * self.risk_per_trade
stop_distance = abs(signal.entry_price - signal.stop_loss)

if stop_distance == 0:
    logger.warning("[RISK] Stop distance is zero, skipping trade")
    return

quantity = risk_amount / stop_distance  # ← BUG: No minimum stop check!
```

**Issue**: If stop_distance is $10 on a $100,000 BTC price (0.01%), the position size becomes:
- quantity = $2 / $10 = 0.2 BTC
- notional = $20,000 (200x capital!)

Even after leverage capping to $2,000, this is still 20x capital exposure.

###2. Tiered Position Sizing Still Compounds Exponentially
**Current Tiers**:
```python
if self.current_capital < 200:
    position_base = 100
elif self.current_capital < 400:
    position_base = 200  # 2x Tier 1
elif self.current_capital < 800:
    position_base = 400  # 2x Tier 2
elif self.current_capital < 1600:
    position_base = 800  # 2x Tier 3
else:
    position_base = 1600  # 2x Tier 4
```

**Issue**: With a winning streak, you quickly jump tiers and double position sizes, causing runaway growth.

## Proposed Fixes

### Fix #1: Add Minimum Stop Distance Requirement ✅

```python
def _place_entry_order(self, signal: TradeSignal, timestamp: int):
    """Place limit entry order with leverage"""

    stop_distance = abs(signal.entry_price - signal.stop_loss)

    # MINIMUM STOP DISTANCE: 0.1% of entry price for BTC
    min_stop_distance = signal.entry_price * 0.001  # 0.1%

    if stop_distance == 0:
        logger.warning("[RISK] Stop distance is zero, skipping trade")
        return

    if stop_distance < min_stop_distance:
        logger.warning(f"[RISK] Stop too tight (${stop_distance:.2f} < ${min_stop_distance:.2f}), skipping trade")
        return  # Skip trade if stop is too tight

    # Continue with position sizing...
```

### Fix #2: Use Fixed Position Sizing (No Compounding) ✅

**Option A: Pure Fixed Position Sizing** (Recommended for realistic testing)
```python
def _place_entry_order(self, signal: TradeSignal, timestamp: int):
    """Place limit entry order with leverage - FIXED SIZING"""

    # ALWAYS use initial capital for position sizing (no compounding)
    position_base = self.initial_capital

    risk_amount = position_base * self.risk_per_trade
    stop_distance = abs(signal.entry_price - signal.stop_loss)

    # ... rest of logic
```

**Option B: More Conservative Tiering** (If you want some compounding)
```python
# Much slower tier progression to prevent runaway growth
if self.current_capital < 300:
    position_base = 100
elif self.current_capital < 600:
    position_base = 150  # Only 1.5x (not 2x)
elif self.current_capital < 1200:
    position_base = 200  # 1.33x
else:
    position_base = 250  # Cap at 2.5x initial capital
```

### Fix #3: Add Position Size Sanity Checks ✅

```python
# After calculating quantity
notional_value = quantity * signal.entry_price
max_notional = position_base * self.leverage

# Additional sanity check: Never exceed 20x initial capital
absolute_max_notional = self.initial_capital * 20

if notional_value > absolute_max_notional:
    quantity = absolute_max_notional / signal.entry_price
    logger.warning(f"[RISK] Position capped to 20x initial capital (${absolute_max_notional:,.2f})")
elif notional_value > max_notional:
    quantity = max_notional / signal.entry_price
    logger.warning(f"[RISK] Position capped by tiered leverage (${max_notional:,.2f})")
```

## Recommendation

For realistic backtesting, I recommend:

1. ✅ **Add minimum stop distance validation** (Fix #1)
2. ✅ **Use pure fixed position sizing** (Fix #2, Option A)
3. ✅ **Add position size sanity checks** (Fix #3)

This will ensure:
- No unrealistic position sizes from tight stops
- Consistent risk per trade
- Capital can only grow from trading edge, not compounding luck

## Implementation

Apply these fixes to:
1. `src/backtesting/vwap_backtest_engine.py` (line 472+)
2. `src/backtesting/vwap_ml_backtest_engine.py` (line 530+)

Then re-run your 180d backtest to validate.
