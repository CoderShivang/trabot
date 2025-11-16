# Position Sizing System - Realistic Compounding with Dynamic Leverage

## Overview
This system implements professional-grade position sizing that balances realistic compounding with risk management through dynamic leverage scaling.

## Position Sizing (Fractional Compounding)

```python
position_base = min(self.current_capital, self.initial_capital * 3)
```

**How it works:**
- Uses **current account balance** as position base (realistic compounding)
- Capped at **3x initial capital** to prevent runaway growth
- For $100 start: max position base = $300

**Example:**
| Account Balance | Position Base | Notes |
|----------------|---------------|-------|
| $100 | $100 | Use full balance |
| $150 | $150 | Use full balance |
| $250 | $250 | Use full balance |
| $300 | $300 | At cap (3x initial) |
| $500 | $300 | Capped at 3x initial |

## Dynamic Leverage Scaling

```python
if current_capital < $200:    leverage = 20x
elif current_capital < $400:  leverage = 15x
elif current_capital < $600:  leverage = 10x
else:                          leverage = 5x
```

**Rationale:**
- **Small accounts ($100-$199)**: 20x leverage
  - Need higher leverage to make meaningful returns
  - Acceptable risk when account is small

- **Growing accounts ($200-$399)**: 15x leverage
  - Reduce risk as account doubles
  - Still aggressive enough for growth

- **Medium accounts ($400-$599)**: 10x leverage
  - More conservative approach
  - Account has 4x'd from start

- **Large accounts ($600+)**: 5x leverage
  - Very conservative for preservation
  - Account has 6x'd - protect gains

## Maximum Position Limits

### Per-Position Caps
1. **Leverage Cap**: `max_notional = position_base × current_leverage`
2. **Absolute Cap**: `max_notional = initial_capital × 20 = $2,000`

**Example at different account levels:**

| Account | Position Base | Leverage | Leverage Cap | Absolute Cap | Final Cap |
|---------|---------------|----------|--------------|--------------|-----------|
| $100 | $100 | 20x | $2,000 | $2,000 | **$2,000** |
| $200 | $200 | 15x | $3,000 | $2,000 | **$2,000** |
| $300 | $300 | 10x | $3,000 | $2,000 | **$2,000** |
| $600 | $300 | 5x | $1,500 | $2,000 | **$1,500** |

## Risk Per Trade

```python
risk_amount = position_base × 0.02  # 2% of position base
```

**Constant 2% risk** ensures:
- Consistent risk exposure across all trades
- Predictable drawdown potential
- Standard Kelly Criterion application

## Position Sizing Formula

```python
quantity = risk_amount / stop_distance
```

**Example calculation:**
- Account: $200
- Position Base: $200
- Risk: 2% = $4
- Entry: $100,000
- Stop: $99,500 (0.5% away)
- Stop Distance: $500

```
quantity = $4 / $500 = 0.008 BTC
notional = 0.008 × $100,000 = $800

Check leverage cap: $800 < ($200 × 15) = $3,000 ✅
Check absolute cap: $800 < $2,000 ✅
Position allowed ✅
```

## Safety Features

### 1. Fractional Compounding Cap
- Prevents runaway compounding
- Max position base = 3x initial capital
- Realistic growth expectations

### 2. Dynamic Leverage Reduction
- Automatically de-risks as account grows
- Professional money management
- Preserves gains on larger accounts

### 3. Absolute Position Limit
- No single position > 20x initial capital
- Emergency brake for edge cases
- Protects against calculation errors

### 4. Zero Stop Protection
- Skips trades with zero stop distance
- Prevents division by zero
- Ensures valid risk calculation

## Benefits

✅ **Realistic**: Matches how real traders scale positions
✅ **Safe**: Reduces risk as account grows
✅ **Controlled**: Multiple safety caps prevent explosions
✅ **Fair**: Both baseline and ML use same sizing system
✅ **Professional**: Industry-standard leverage scaling

## Expected Growth Profile

With 47% win rate and realistic position sizing:

| Period | Expected Account Range | Notes |
|--------|------------------------|-------|
| 30 days | $90-$150 | Small gains, high variance |
| 90 days | $80-$200 | Strategy edge emerges |
| 180 days | $70-$300 | Long-term performance clear |

**Goal**: Gradual, sustainable growth rather than exponential explosions.

## Comparison to Previous Systems

### Old Tiered System (Problematic)
```python
# Doubled at each tier - too aggressive!
if capital < $200:    position_base = $100
elif capital < $400:  position_base = $200  # 2x jump!
elif capital < $800:  position_base = $400  # 2x jump!
```
**Problem**: Exponential growth from lucky streaks

### Fixed System (Too Conservative)
```python
position_base = initial_capital  # Always $100
```
**Problem**: No compounding, unrealistic

### Current System (Optimal)
```python
position_base = min(current_capital, initial_capital × 3)
leverage = dynamic (20x → 5x as account grows)
```
**Benefit**: Realistic compounding + risk reduction

## ML Comparison Workflow

Both baseline and ML-filtered backtests use the **exact same position sizing**:

1. **180d Baseline**: Train ML model, measure realistic growth
2. **90d Baseline**: Get baseline performance (45-47% win rate)
3. **90d ML-Filtered**: Apply ML filter (target 55-60% win rate)
4. **Compare**: ML improvement purely from better trade selection

Position sizing is controlled, so performance differences = strategy edge.
