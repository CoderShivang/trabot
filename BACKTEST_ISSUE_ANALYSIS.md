# STRATEGY PARAMETER FIXES

## Issue: Unrealistic backtest results
- 970 trades in 68 days (14/day)
- 73% win rate (vs baseline 45-47%)
- $39k from $100 (looks too good)

## Root Causes Found:

### 1. Confidence Threshold Too Low
**File**: `src/strategy/vwap_strategy.py`
**Lines**: 914, 1051

**Current** (WRONG):
```python
if confidence >= 50:  # Lowered from 65 for initial testing
```

**Should Be**:
```python
if confidence >= 65:  # Standard threshold for quality setups
```

### 2. Min Zone Strength Too Low
**File**: `src/strategy/vwap_strategy.py`
**Line**: 368

**Current**:
```python
self.min_zone_strength = self.config.get('min_zone_strength', 20)
```

**Recommended**:
```python
self.min_zone_strength = self.config.get('min_zone_strength', 60)
```

## Recommendation:

**STOP the current backtest and fix these parameters first.**

After fixing, you should see:
- Fewer trades (~200-300 instead of 970)
- Win rate closer to baseline (45-50%)
- More realistic returns

## Note:
The PnL calculations, fee deductions, and position sizing are ALL CORRECT.
The issue is purely that the strategy is being too aggressive/permissive with signal generation.
