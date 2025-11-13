# S/R ZONE DETECTION - ALGORITHM DESIGN

## What You See vs What the Algorithm Detects

### Your Manual Process (from charts):

1. **Look for consolidation areas** (sideways price movement)
2. **Mark horizontal rectangles** where price repeatedly touches
3. **Skip choppy/noisy areas** (red ellipses - trending or messy zones)
4. **Validate by observing** how price reacts on retest

### The Algorithm Matches This:

```
┌─────────────────────────────────────────────────────────────┐
│  CHART 1 ANALYSIS (Your First Image)                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🟣 Top Purple Zone (~$45-46 level)                        │
│     Algorithm detects:                                      │
│     ✓ Consolidation zone (15+ bars, range < 2%)            │
│     ✓ Multiple swing highs clustered at $45.5              │
│     ✓ At least 3 touches visible                           │
│     ✓ NOT choppy (consistent horizontal level)             │
│     → VALID RESISTANCE ZONE                                 │
│                                                             │
│  🟣 Bottom Purple Zone (~$32-33 level)                     │
│     Algorithm detects:                                      │
│     ✓ Consolidation zone during sideways action            │
│     ✓ Multiple swing lows clustered at $32.7               │
│     ✓ Clear horizontal level                               │
│     ✓ Later validated by bounce                            │
│     → VALID SUPPORT ZONE                                    │
│                                                             │
│  🔴 Red Ellipse Area (trending down, choppy)               │
│     Algorithm SKIPS:                                        │
│     ✗ High volatility (returns.std() > 0.008)              │
│     ✗ Strong downtrend detected (slope > 3%)               │
│     ✗ High wick overlap (> 60% bars overlapping)           │
│     → REJECTED (choppy/trending area)                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│  CHART 2 ANALYSIS (Your Second Image)                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🟣 Left Side Purple Zones (multiple levels)               │
│     Algorithm detects:                                      │
│     ✓ Ranging market detected (multiple consolidations)    │
│     ✓ Each zone: tight range, horizontal, multiple touches │
│     ✓ Swing highs/lows cluster at consistent levels        │
│     → MULTIPLE VALID S/R ZONES                              │
│                                                             │
│  🟣 Center Purple Zone (~mid-level)                        │
│     Algorithm detects:                                      │
│     ✓ Price consolidates after uptrend                     │
│     ✓ Horizontal level with 3+ touches                     │
│     ✓ Low volatility in zone area                          │
│     → VALID RESISTANCE → SUPPORT (flip)                     │
│                                                             │
│  🟣 Right Side Purple Zones                                │
│     Algorithm detects:                                      │
│     ✓ Clear consolidation periods                          │
│     ✓ Distinct horizontal levels                           │
│     ✓ Rejections visible (wicks + closes)                  │
│     → VALID S/R ZONES                                       │
│                                                             │
│  🔴 Red Ellipse Area (choppy uptrend)                      │
│     Algorithm SKIPS:                                        │
│     ✗ Strong uptrend (slope positive > 3%)                 │
│     ✗ Volatile moves (high bar-to-bar variance)            │
│     ✗ No clear consolidation (range keeps expanding)       │
│     → REJECTED (trending area, not consolidation)           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Key Algorithm Features Matching Your Style

### 1. Consolidation Detection ✅
```python
# Your eyes see: "Price moving sideways in tight range"
# Algorithm checks:
range_pct = (high - low) / mid_price
if range_pct < 0.02:  # Less than 2% range
    → This is consolidation, look for S/R here
```

### 2. Horizontal Level Finding ✅
```python
# Your eyes see: "Multiple touches at same price level"
# Algorithm:
- Find all swing highs in consolidation
- Find all swing lows in consolidation  
- Cluster nearby levels (within 0.3% = "same level")
- Cluster centers = S/R levels
```

### 3. Choppy Area Rejection ✅ (Your Red Ellipses)
```python
# Your eyes see: "Too messy, skip this area"
# Algorithm checks:
if trending:           # Strong slope detected
    → SKIP
if high_volatility:    # Returns.std() > 0.008
    → SKIP  
if too_many_overlaps:  # Bars overlapping > 60%
    → SKIP
```

### 4. Zone Validation ✅
```python
# Your eyes see: "Price respects this level"
# Algorithm checks:
- Count touches (need ≥ 2)
- Count rejections (wick through + close back)
- Check consistency (volatility at zone)
- Calculate strength score (0-100)
if strength >= 40:
    → VALID S/R ZONE
```

## Strength Scoring System

The algorithm scores each zone 0-100 based on what makes a "good" zone:

```
┌──────────────────────────────────────────┐
│  ZONE STRENGTH CALCULATION               │
├──────────────────────────────────────────┤
│                                          │
│  Touches:      8 points per touch        │
│                (max 40 points)           │
│                                          │
│  Rejections:   10 points per rejection   │
│                (max 30 points)           │
│                                          │
│  Consistency:  Lower volatility          │
│                (max 20 points)           │
│                                          │
│  Clarity:      Clear support/resistance  │
│                (10 points)               │
│                                          │
│  Total: 0-100 points                     │
│                                          │
│  Threshold: Keep zones with ≥40 points   │
│                                          │
└──────────────────────────────────────────┘
```

### Example Zone Scores:

**Strong Zone (Score: 85)**
- 5 touches → 40 points
- 3 clear rejections → 30 points  
- Low volatility → 15 points
- Clear resistance → 10 points
- **Total: 95 points** ✅ EXCELLENT ZONE

**Weak Zone (Score: 30)**
- 2 touches → 16 points
- 0 rejections → 0 points
- High volatility → 5 points
- Mixed type → 0 points  
- **Total: 21 points** ❌ REJECTED

## Integration with Your VWAP Strategy

```python
# Example workflow:
detector = AdvancedSRDetector()

# 1. Detect all zones
zones = detector.detect_zones(df, lookback=200)

# 2. Filter by strength
strong_zones = [z for z in zones if z.strength >= 60]

# 3. Find zone near current price
current_price = df['close'].iloc[-1]
nearest = detector.find_nearest_zone(strong_zones, current_price)

# 4. Check VWAP confluence
if nearest and vwap_bands.is_near_band(current_price, 'lower_1std'):
    if nearest.zone_type == 'support':
        # LONG SETUP: VWAP -1σ + Support Zone
        place_limit_buy(nearest.level - 20)
```

## Key Parameters You Can Tune

```python
# Consolidation Detection
min_bars = 15              # Minimum bars for consolidation
max_range_pct = 0.02       # Max 2% range = consolidation

# Level Clustering  
tolerance_pct = 0.003      # Within 0.3% = "same level"

# Zone Validation
touch_tolerance_pct = 0.004  # Within 0.4% = "touch"
min_strength = 40            # Minimum quality score

# Choppy Detection
max_trend_slope = 0.03     # Max 3% slope
max_volatility = 0.008     # Max 0.8% volatility
max_overlap_ratio = 0.6    # Max 60% wick overlap
```

## Visual Detection Logic

```
INPUT: Price Data
    │
    ▼
┌─────────────────────────────────────┐
│  1. SCAN FOR CONSOLIDATION ZONES    │
│     (Tight range, sideways action)  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. FILTER OUT CHOPPY AREAS         │
│     (Trending, volatile, overlaps)  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. FIND HORIZONTAL LEVELS          │
│     (Cluster swing highs/lows)      │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. VALIDATE EACH LEVEL             │
│     (Touches, rejections, strength) │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  5. QUALITY FILTER                  │
│     (Keep zones with strength ≥40)  │
└─────────────────────────────────────┘
    │
    ▼
OUTPUT: High-Quality S/R Zones (Like your purple boxes!)
```

## Why This Works

Your brain naturally identifies:
1. **Sideways movement** → Algorithm finds consolidation
2. **Horizontal levels** → Algorithm clusters swing points  
3. **Messy areas** → Algorithm filters choppy zones
4. **Good zones** → Algorithm scores by touches + rejections

The algorithm replicates your visual pattern recognition using:
- **Statistics** (range %, volatility, slope)
- **Clustering** (grouping nearby levels)  
- **Validation** (counting touches/rejections)
- **Scoring** (quantifying "good" vs "bad" zones)

## Testing & Calibration

To match your zones perfectly:

1. **Run on historical data** where you've marked zones
2. **Compare algorithm output** to your manual zones
3. **Tune parameters** to increase match rate
4. **Focus on strength threshold** (maybe you want ≥50, not ≥40)

The algorithm is designed to be conservative - it will find fewer zones than possible, but they'll be high quality (like your purple boxes, not like every minor level).
