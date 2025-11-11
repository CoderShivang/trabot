# 🎯 Complete Entry Logic Explained

## Your Trading Style (Support & Resistance Based)

You trade primarily off **S/R levels, psychological levels, moving averages, and VWAP**, looking for:
- Price reactions at key zones
- Volume confirmation
- Order flow absorption patterns
- Large institutional orders

---

## 🔍 LONG Entry Logic (Step-by-Step)

### Visual Flow
```
START: BTC at $50,000
        ↓
[1] PRE-CHECKS ───→ Any fail? → REJECT
        ↓ All pass
[2] CONTEXT (Bias) ───→ Bearish? → Heavy penalty
        ↓ Bullish or Neutral
[3] LOCATION (S/R) ───→ Not at level? → REJECT
        ↓ At key zone
[4] CONFIRMATION (Order Flow) ───→ <2 signals? → REJECT
        ↓ 2+ Tier 1 signals
[5] BIG ORDERS ───→ Adds bonus points
        ↓
[6] CALCULATE CLC SCORE ───→ <75? → Check ML
        ↓ ≥75 or ML Override
[7] HUMAN FEEDBACK ───→ Adjust score
        ↓
[8] FINAL DECISION ───→ ENTER LONG ✓
```

---

### Phase-by-Phase Breakdown

#### **PHASE 1: PRE-CHECKS** (1ms, ultra-fast rejection)

**Purpose:** Filter out obvious "no-go" conditions before expensive calculations

```python
def pre_checks() -> bool:
    """Fast rejection filters"""

    # 1. Position limits
    if has_position(symbol):
        return REJECT("Already in BTC position")

    if count_positions() >= max_positions:
        return REJECT("Max positions reached (1/1)")

    # 2. Risk limits
    if daily_pnl <= -30:
        return REJECT("Daily loss limit hit (-$30)")

    if consecutive_losses >= 3:
        return REJECT("Max consecutive losses (3)")

    # 3. Time filters
    current_hour = datetime.now(UTC).hour

    if current_hour not in [7,8,9,12,13,14,19,20,21]:
        return REJECT("Outside trading hours (London/NY sessions)")

    # 4. Recent history at this level
    for trade in last_10_trades:
        if abs(trade.entry_price - current_price) / current_price < 0.005:  # Within 0.5%
            if trade.pnl < 0 and (now - trade.time) < 3600:  # Lost within 1 hour
                return REJECT(f"Recent loss at ${trade.entry_price} (1h ago)")

    # 5. Cooldown
    if (now - last_trade_time) < 180:  # 3 minutes
        return REJECT("Cooldown: 3 min between trades")

    return PASS("All pre-checks passed ✓")
```

**Why This Phase Matters:**
- Prevents stupid mistakes (double entries, risk blowups)
- Saves computation time (90% of candles rejected here)
- Enforces discipline (no revenge trading at same level)

---

#### **PHASE 2: CONTEXT ANALYSIS** (Multi-Timeframe Bias)

**Purpose:** Determine if market structure supports LONG direction

```python
def analyze_context() -> (bias, score):
    """Check 1H, 15M, 1M alignment"""

    # === 1-HOUR TIMEFRAME (Primary Bias) ===
    ctx_1h = {
        'price': 50000,
        'vwap': 49850,
        'ema50': 50200,
        'ema200': 49500,
        'atr': 300
    }

    score = 0
    bias_votes = 0

    # Check 1: Price vs VWAP
    if price > vwap:  # 50000 > 49850 ✓
        score += 20
        bias_votes += 1
        reasons.append("Price above 1H VWAP")

    # Check 2: EMA structure
    if ema50 > ema200:  # 50200 > 49500 ✓
        score += 25
        bias_votes += 1
        reasons.append("EMA50 > EMA200 (bullish)")

    # Trend strength (how far apart are EMAs?)
    trend_strength = abs(ema50 - ema200) / ema200
    # = abs(50200 - 49500) / 49500 = 0.0141 (1.41%)

    if trend_strength > 0.02:  # Strong trend
        score += 10
        reasons.append("Strong trend (2%+ EMA separation)")

    # Determine 1H bias
    if bias_votes >= 2:
        bias_1h = BULLISH
    elif bias_votes <= -2:
        bias_1h = BEARISH
    else:
        bias_1h = NEUTRAL

    # === 15-MINUTE TIMEFRAME (Secondary) ===
    ctx_15m = analyze_timeframe("15m")
    bias_15m = determine_bias(ctx_15m)

    # === 1-MINUTE TIMEFRAME (Execution) ===
    ctx_1m = analyze_timeframe("1m")
    bias_1m = determine_bias(ctx_1m)

    # === ALIGNMENT SCORE ===
    alignment = 0

    if bias_1h == bias_15m:
        alignment += 50  # Higher TFs agree (important!)

    if bias_15m == bias_1m:
        alignment += 30  # Execution aligns with 15M

    if bias_1h == bias_1m:
        alignment += 20  # Full cascade alignment

    # Apply alignment multiplier
    if alignment >= 80:  # All aligned
        score *= 1.3  # 30% bonus
        reasons.append("✓ All timeframes aligned")
    elif alignment >= 50:  # Partial alignment
        score *= 1.0  # Neutral
    else:  # Misalignment
        score *= 0.5  # 50% penalty
        warnings.append("⚠️ Timeframe misalignment")

    return {
        'bias_1h': bias_1h,
        'bias_15m': bias_15m,
        'bias_1m': bias_1m,
        'score': score,
        'alignment': alignment,
        'trend_strength': trend_strength
    }
```

**Example Output:**
```python
{
    'bias_1h': BULLISH,
    'bias_15m': BULLISH,
    'bias_1m': BULLISH,
    'score': 58.5,  # (45 × 1.3 alignment bonus)
    'alignment': 100,  # Perfect alignment
    'trend_strength': 0.0141
}
```

**Why This Phase Matters:**
- **Prevents counter-trend trades** (shorting in bull market)
- **Higher timeframe = higher importance** (1H > 15M > 1M)
- **Alignment bonus** rewards setups where all TFs agree

---

#### **PHASE 3: LOCATION DETECTION** (Your Core Edge)

**Purpose:** Find the **exact price levels** where you'd trade manually

**The 6 Detection Methods:**

```python
def detect_all_locations(symbol, current_price) -> zones:
    """Run all 6 methods, then consolidate"""

    all_zones = []

    # ========================================
    # METHOD 1: FREQUENCY-BASED (Swing Points)
    # ========================================
    # Scans last 500 candles for repeated touches

    klines_15m = get_klines("15m", limit=500)
    swings = []

    for i in range(20, len(klines) - 20):
        high = klines[i].high
        low = klines[i].low

        # Is this a swing high?
        if high == max([k.high for k in klines[i-20:i+20]]):
            swings.append({'price': high, 'type': 'resistance'})

        # Is this a swing low?
        if low == min([k.low for k in klines[i-20:i+20]]):
            swings.append({'price': low, 'type': 'support'})

    # Cluster nearby swings
    clusters = cluster_by_proximity(swings, threshold=0.003)  # 0.3%

    for cluster in clusters:
        avg_price = mean([s['price'] for s in cluster])
        touches = len(cluster)

        if touches >= 3:  # Minimum 3 touches
            all_zones.append({
                'level': avg_price,
                'type': cluster[0]['type'],
                'strength': min(touches, 10),  # Cap at 10
                'method': 'frequency',
                'touches': touches
            })

    # ========================================
    # METHOD 2: VOLUME PROFILE (High Volume Nodes)
    # ========================================
    # Where most trading volume occurred

    volume_by_price = {}

    for kline in klines_15m:
        # Distribute volume across price range
        price_range = kline.high - kline.low
        volume = kline.volume

        # Create $100 buckets for BTC
        for price in range(int(kline.low), int(kline.high), 100):
            bucket = round(price / 100) * 100
            volume_by_price[bucket] = volume_by_price.get(bucket, 0) + volume

    # Find top 3 volume nodes
    top_nodes = sorted(volume_by_price.items(), key=lambda x: x[1], reverse=True)[:3]

    for price, volume in top_nodes:
        all_zones.append({
            'level': price,
            'type': 'both',  # High volume = both S/R
            'strength': 6.0,
            'method': 'volume_profile',
            'volume': volume
        })

    # ========================================
    # METHOD 3: LIQUIDITY HEATMAP (Stop Clusters)
    # ========================================
    # Where stop-loss orders likely sit

    liquidity_levels = []

    # Find swing highs (stops above)
    for swing_high in [s for s in swings if s['type'] == 'resistance']:
        # Stops typically 20-50 points above swing high
        stop_cluster = swing_high['price'] + 50

        liquidity_levels.append({
            'level': stop_cluster,
            'type': 'resistance',
            'strength': 5.0,
            'method': 'liquidity',
            'liquidity_score': 8.0
        })

    # Find swing lows (stops below)
    for swing_low in [s for s in swings if s['type'] == 'support']:
        stop_cluster = swing_low['price'] - 50

        liquidity_levels.append({
            'level': stop_cluster,
            'type': 'support',
            'strength': 5.0,
            'method': 'liquidity',
            'liquidity_score': 8.0
        })

    all_zones.extend(liquidity_levels)

    # ========================================
    # METHOD 4: FIBONACCI RETRACEMENT
    # ========================================
    # From recent swing high to low

    recent_high = max([k.high for k in klines_15m[-50:]])
    recent_low = min([k.low for k in klines_15m[-50:]])

    fib_range = recent_high - recent_low

    fib_levels = {
        0.236: 3.0,
        0.382: 5.0,
        0.500: 6.0,
        0.618: 7.0,  # Golden ratio (strongest)
        0.786: 4.0
    }

    for ratio, strength in fib_levels.items():
        if current_price > (recent_high + recent_low) / 2:  # Uptrend
            level = recent_low + (fib_range * ratio)
            zone_type = 'support'
        else:  # Downtrend
            level = recent_high - (fib_range * ratio)
            zone_type = 'resistance'

        # Only add if near current price
        if abs(level - current_price) / current_price <= 0.02:  # Within 2%
            all_zones.append({
                'level': level,
                'type': zone_type,
                'strength': strength,
                'method': 'fibonacci',
                'ratio': ratio
            })

    # ========================================
    # METHOD 5: PSYCHOLOGICAL LEVELS (Round Numbers)
    # ========================================
    # $50,000, $49,500, etc.

    if symbol == "BTCUSDT":
        round_to = 1000  # BTC rounds to thousands
        half_step = 500
    else:  # ETH
        round_to = 100
        half_step = 50

    psychological_levels = []

    base = round(current_price / round_to) * round_to

    for offset in [-2, -1, 0, 1, 2]:
        level = base + (offset * round_to)

        if abs(level - current_price) / current_price <= 0.01:  # Within 1%
            psychological_levels.append({
                'level': level,
                'type': 'both',
                'strength': 8.0,  # Psychological levels are strong
                'method': 'psychological'
            })

        # Add half-levels (e.g., $50,500)
        half_level = level + half_step
        if abs(half_level - current_price) / current_price <= 0.01:
            psychological_levels.append({
                'level': half_level,
                'type': 'both',
                'strength': 5.0,
                'method': 'psychological'
            })

    all_zones.extend(psychological_levels)

    # ========================================
    # METHOD 6: MANUAL ZONES (Your Marks)
    # ========================================
    # Zones you marked in dashboard

    manual_zones = load_manual_zones()

    for zone in manual_zones:
        if zone['symbol'] == symbol:
            # Your zones get automatic boost
            all_zones.append({
                'level': zone['level'],
                'type': zone['type'],
                'strength': zone['confidence'] * 2,  # 5 stars = 10 strength
                'method': 'manual',
                'human_confidence': zone['confidence']
            })

    # ========================================
    # CONSOLIDATION (Merge Close Zones)
    # ========================================

    consolidated = []
    used = set()

    for i, zone1 in enumerate(all_zones):
        if i in used:
            continue

        # Find all zones within 0.3% of this one
        cluster = [zone1]
        used.add(i)

        for j, zone2 in enumerate(all_zones):
            if j in used or i == j:
                continue

            distance_pct = abs(zone1['level'] - zone2['level']) / zone1['level']

            if distance_pct <= 0.003:  # Within 0.3%
                cluster.append(zone2)
                used.add(j)

        # Merge cluster
        avg_level = mean([z['level'] for z in cluster])
        methods = list(set([z['method'] for z in cluster]))
        base_strength = max([z['strength'] for z in cluster])

        # CONFLUENCE BONUS
        confluence_bonus = (len(methods) - 1) * 1.5

        final_strength = min(10.0, base_strength + confluence_bonus)

        # MANUAL OVERRIDE BONUS
        if 'manual' in methods:
            final_strength = min(10.0, final_strength * 1.5)

        consolidated.append({
            'level': avg_level,
            'type': cluster[0]['type'],
            'strength': final_strength,
            'methods': methods,
            'confluence': len(methods),
            'manual_marked': 'manual' in methods
        })

    # ========================================
    # CHECK IF AT A ZONE
    # ========================================

    at_location = False
    best_zone = None
    location_score = 0

    for zone in sorted(consolidated, key=lambda z: z['strength'], reverse=True):
        distance_pct = abs(current_price - zone['level']) / current_price

        if distance_pct <= 0.005:  # Within 0.5%
            at_location = True
            best_zone = zone

            # Score based on strength
            location_score = 40 * (zone['strength'] / 10)

            break

    return {
        'all_zones': consolidated,
        'at_location': at_location,
        'best_zone': best_zone,
        'location_score': location_score
    }
```

**Example Output:**
```python
{
    'all_zones': [
        {
            'level': 49828,
            'type': 'support',
            'strength': 10.0,
            'methods': ['frequency', 'volume_profile', 'fibonacci', 'manual'],
            'confluence': 4,
            'manual_marked': True
        },
        {
            'level': 50000,
            'type': 'both',
            'strength': 8.0,
            'methods': ['psychological'],
            'confluence': 1,
            'manual_marked': False
        }
    ],
    'at_location': True,
    'best_zone': {
        'level': 50000,
        'type': 'both',
        'strength': 8.0,
        'methods': ['psychological']
    },
    'location_score': 32  # 40 × (8/10)
}
```

**Why This Phase Matters:**
- **This is YOUR edge** - where you'd trade manually
- **6 methods voting** = high confidence when they agree
- **Your manual marks** get 50% automatic boost
- **Confluence is king** - 4 methods > 1 method

---

#### **PHASE 4: ORDER FLOW CONFIRMATION** (Institutional Activity)

**Purpose:** Confirm NOW is the right time to enter (not just at the level)

```python
def analyze_order_flow(orderbook, recent_trades) -> confirmation:
    """Read the tape for institutional activity"""

    score = 0
    signals = []
    tier1_count = 0  # High-quality institutional signals

    # ========================================
    # SIGNAL 1: ORDERBOOK IMBALANCE
    # ========================================
    # Are there more buyers or sellers?

    bid_volume = sum(orderbook.bids[:10], key=lambda x: x[1])  # Top 10 bids
    ask_volume = sum(orderbook.asks[:10], key=lambda x: x[1])  # Top 10 asks

    imbalance = bid_volume / (bid_volume + ask_volume)

    if imbalance >= 0.70:  # 70%+ bids (buying pressure)
        score += 15
        signals.append(f"imbalance:{imbalance:.2f}")

    # ========================================
    # SIGNAL 2: CUMULATIVE DELTA
    # ========================================
    # Net buying vs selling in recent trades

    buy_volume = 0
    sell_volume = 0

    for trade in recent_trades:
        if trade['isBuyerMaker']:  # Sell order (market sell hit bid)
            sell_volume += trade['qty']
        else:  # Buy order (market buy hit ask)
            buy_volume += trade['qty']

    delta = (buy_volume - sell_volume) / (buy_volume + sell_volume)

    if delta >= 0.60:  # 60%+ net buying
        score += 20
        signals.append(f"delta:{delta:.2f}")

    # ========================================
    # SIGNAL 3: ABSORPTION (TIER 1) ⭐
    # ========================================
    # Large order absorbing opposing flow without price movement

    # Check for repeated hits at a price level
    level_hits = {}

    for trade in recent_trades[-50:]:  # Last 50 trades
        price_bucket = round(trade['price'] / 10) * 10  # $10 buckets

        if price_bucket not in level_hits:
            level_hits[price_bucket] = {'count': 0, 'volume': 0}

        level_hits[price_bucket]['count'] += 1
        level_hits[price_bucket]['volume'] += trade['qty']

    # Find levels hit 5+ times
    for price, data in level_hits.items():
        if data['count'] >= 5:
            # Check if price stayed stable (absorption)
            price_range = max_price - min_price in recent_trades

            if price_range < 20:  # Price didn't move much
                # ABSORPTION DETECTED
                score += 25
                signals.append(f"absorption@{price}")
                tier1_count += 1  # ⭐ TIER 1 SIGNAL
                break

    # ========================================
    # SIGNAL 4: LARGE MARKET ORDER (TIER 1) ⭐
    # ========================================
    # Single trade above size threshold

    avg_trade_size = mean([t['qty'] * t['price'] for t in recent_trades])
    threshold = avg_trade_size * 5  # 5× average

    for trade in recent_trades[-20:]:
        trade_size_usd = trade['qty'] * trade['price']

        if trade_size_usd > max(threshold, 50000):  # At least $50k for BTC
            # LARGE ORDER DETECTED
            score += 30
            direction = 'BUY' if not trade['isBuyerMaker'] else 'SELL'
            signals.append(f"large_{direction}_{trade_size_usd/1000:.0f}k")
            tier1_count += 1  # ⭐ TIER 1 SIGNAL
            break

    # ========================================
    # SIGNAL 5: TAPE VELOCITY
    # ========================================
    # Trades per second (indicates urgency)

    recent_2sec = [t for t in recent_trades if t['time'] > (now - 2000)]
    velocity = len(recent_2sec) / 2  # Trades per second

    if velocity > 30:  # >30 trades/second
        score += 10
        signals.append(f"high_velocity:{velocity:.0f}tps")

    # ========================================
    # SIGNAL 6: SWEEP (Liquidity Grab)
    # ========================================
    # Price rapidly moving through levels

    # Check if price ran through multiple levels quickly
    price_levels_hit = []

    for i in range(len(recent_trades) - 10, len(recent_trades)):
        if i < 0:
            continue
        price_levels_hit.append(recent_trades[i]['price'])

    price_range = max(price_levels_hit) - min(price_levels_hit)
    time_elapsed = (recent_trades[-1]['time'] - recent_trades[-10]['time']) / 1000

    if price_range > 30 and time_elapsed < 5:  # 30+ points in <5 seconds
        score += 15
        signals.append(f"sweep:{price_range:.0f}pts")

    # ========================================
    # SIGNAL 7: DELTA-PRICE DIVERGENCE (Warning)
    # ========================================
    # Delta says one thing, price says another

    # Calculate delta slope
    delta_slope = calculate_delta_slope(recent_trades)
    price_slope = calculate_price_slope(recent_trades)

    if delta_slope * price_slope < 0:  # Opposite directions
        # Price up but delta down = distribution (bad for longs)
        # This is a WARNING, not confirmation
        signals.append("divergence_warning")
        score -= 10  # Negative points

    # ========================================
    # FINAL CHECK
    # ========================================

    meets_requirements = (
        tier1_count >= 1 and  # At least 1 institutional signal
        score >= 40           # Minimum weighted score
    )

    return {
        'score': score,
        'signals': signals,
        'tier1_count': tier1_count,
        'meets_requirements': meets_requirements
    }
```

**Example Output:**
```python
{
    'score': 70,
    'signals': [
        'absorption@49995',
        'large_BUY_120k',
        'sweep:35pts'
    ],
    'tier1_count': 2,  # absorption + large order
    'meets_requirements': True
}
```

**Why This Phase Matters:**
- **Timing is everything** - level alone isn't enough
- **Institutional signals > retail signals** (Tier 1 vs Tier 2)
- **Absorption + Large Orders** = smart money active
- **Prevents fakeouts** - level present but no buying pressure

---

#### **PHASE 5: BIG ORDERS TRACKING**

Already covered in Phase 4, but adds:
- **Iceberg detection** (orders refilling)
- **Spoofing detection** (orders appearing/disappearing)
- **5-minute accumulation tracking** (rolling institutional flow)

---

#### **PHASE 6: CALCULATE CLC SCORE**

```python
total_score = (
    context_score * 0.25 +        # 58.5 × 0.25 = 14.6
    location_score * 0.30 +       # 32.0 × 0.30 = 9.6
    confirmation_score * 0.25 +   # 70.0 × 0.25 = 17.5
    big_orders_score * 0.20       # 60.0 × 0.20 = 12.0
)  # = 53.7

# Counter-trend penalty
if direction != context_bias and context_bias != NEUTRAL:
    if trend_strength > 0.05:
        total_score *= 0.5  # Heavy penalty (strong counter-trend)
    elif trend_strength > 0.02:
        total_score *= 0.7  # Medium penalty
    else:
        total_score *= 0.85  # Light penalty

# In this case: No penalty (both BULLISH)
final_score = 53.7
```

---

#### **PHASE 7: ENTRY CRITERIA CHECK + ML OVERRIDE**

```python
# Standard criteria
meets_criteria = (
    total_score >= 75 and          # 53.7 < 75 ✗
    at_location == True and        # ✓
    len(signals) >= 2 and          # 3 >= 2 ✓
    tier1_signals >= 1             # 2 >= 1 ✓
)

# REJECTED by standard rules

# But ML can override...
if use_ml:
    features = extract_features(trade_data)
    win_prob = ml_model.predict(features)

    if win_prob >= 0.55:  # 55%+ confidence
        meets_criteria = True  # OVERRIDE ✓
        log(f"ML override: {win_prob*100:.1f}% win probability")
```

---

#### **PHASE 8: EXECUTE TRADE**

```python
if meets_criteria:
    # Position sizing
    risk_amount = 15  # $15 per trade
    risk_points = 150  # BTC risk
    quantity = risk_amount / risk_points  # 0.1 BTC

    # Entry details
    entry_price = 50000
    stop_loss = 50000 - 150 = 49850
    take_profit = 50000 + 200 = 50200

    # Open position
    open_position(
        symbol="BTCUSDT",
        direction="LONG",
        entry=50000,
        qty=0.1,
        sl=49850,
        tp=50200
    )

    log("[ENTRY] LONG BTC @ $50,000, SL: $49,850, TP: $50,200")
```

---

## 🔴 SHORT Entry Logic (Key Differences)

**Context Requirements:**
- Price BELOW 1H VWAP
- EMA50 < EMA200 (bearish structure)
- All timeframes BEARISH or NEUTRAL

**Location Requirements:**
- At RESISTANCE zone (not support)
- Preferably rejected from psychological level (e.g., failed to break $50k)

**Confirmation Requirements:**
- Orderbook imbalance: ASKS > BIDS (selling pressure)
- Cumulative delta: NEGATIVE (more selling)
- Absorption at ASK side (large sells absorbing buys)
- Large SELL orders detected

**Entry:**
```python
direction = "SHORT"
entry_price = 50000
stop_loss = 50000 + 150  # ABOVE entry (protect from rallies)
take_profit = 50000 - 200  # BELOW entry (target downside)
```

---

## 📊 Summary Scorecard

| Phase | Weight | Example | Pass? |
|-------|--------|---------|-------|
| Context | 25% | 58.5 points | ✓ |
| Location | 30% | 32.0 points | ✓ |
| Confirmation | 25% | 70.0 points | ✓✓ |
| Big Orders | 20% | 60.0 points | ✓ |
| **Total CLC** | 100% | **53.7** | ✗ (need 75) |
| **ML Override** | N/A | **68% win prob** | ✓✓ (>55%) |
| **Final Decision** | N/A | **ENTER LONG** | ✓✓✓ |

---

## 🎯 Key Takeaways

1. **Location is King (30% weight)** - Your S/R edge
2. **Confluence Multiplies Confidence** - 4 methods > 1 method
3. **Tier 1 Signals Matter Most** - Absorption + Large Orders = institutional
4. **Timeframe Alignment is Critical** - 1H+15M+1M must agree
5. **ML is Safety Net** - Can override low scores if patterns match winners
6. **Human Feedback Teaches Bot** - Your marks get 50% boost, bot learns your style

---

**Remember:** This logic runs on EVERY candle during backtest. Most candles (99%) are rejected in Phase 1-3. Only the best setups make it to entry!
