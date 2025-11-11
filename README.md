# 🤖 CLC Trading Bot - Advanced S/R Trading System

An intelligent algorithmic trading bot for BTC/USDT and ETH/USDT on Binance Futures. Uses a sophisticated **Context-Location-Confirmation (CLC)** strategy with multi-method Support/Resistance detection, order flow analysis, and adaptive machine learning.

**Target**: $10/day profit on $100 starting capital (~10% daily ROI)
**Leverage**: 30-100× (automatically managed based on balance)
**Trading Style**: Support/Resistance based scalping with institutional order flow confirmation

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure your API keys
cp .env.example .env
# Edit .env with your Binance API credentials

# 3. Edit configuration (optional)
nano config/bot_config.yaml

# 4. Run backtests to validate strategy
python run_backtest.py --symbol BTCUSDT --days 7

# 5. Launch interactive dashboard
streamlit run dashboard.py

# 6. Start live trading (paper trading by default)
python main.py
```

---

## ✨ Key Features

### 🎯 Multi-Method S/R Detection
- **6 Independent Detection Methods**:
  1. **Frequency-Based**: Swing highs/lows from 15m timeframe
  2. **Volume Profile**: High-volume price nodes (POC, VAH, VAL)
  3. **Liquidity Heatmap**: Stop clusters above/below key levels
  4. **Fibonacci Levels**: 0.236, 0.382, 0.5, 0.618, 0.786 retracements
  5. **Psychological Levels**: Round numbers ($50k, $49.5k for BTC)
  6. **Manual Zones**: Human-marked levels with performance tracking

- **Confluence Scoring**: Zones detected by multiple methods get higher confidence
- **Dynamic Weighting**: Historical performance adjusts future zone strength
- **Zone Consolidation**: Merges overlapping zones within 0.3% of each other

### 🧠 ML-Powered Trade Filtering
- **Random Forest Classifier**: Predicts win probability for each setup
- **18 Feature Extraction**: CLC scores, time, market microstructure, location quality
- **Adaptive Learning**: Retrains every 100 trades
- **VPS-Friendly**: CPU-only, lightweight (sklearn), no GPU needed
- **Feature Importance Analysis**: Shows which factors matter most

### 📊 Trade Explainability
Every trade generates a detailed explanation:
- **Why** the algo took this trade
- **What** signals were detected
- **Which** S/R methods agreed
- **How** the CLC score was calculated
- **What** the ML model predicted
- **Context** from previous human ratings

### 🎨 Interactive Dashboard (Streamlit)
- **One-Click Backtesting**: Select date range, run instantly
- **Visual Chart Analysis**: See MA, VWAP, S/R zones on charts
- **Trade-by-Trade Review**: Expandable explanations for each entry
- **Rate Trades**: 1-5 star rating system (feeds ML training)
- **Mark Missed Setups**: Track opportunities the algo missed
- **ML Insights**: Feature importance, model performance, suggestions

### 🔄 Adaptive Feedback Loop
- Human ratings adjust future trade parameters
- Missed setup analysis identifies patterns
- Zone performance tracking improves detection
- Quality score enables learning after 30+ ratings
- S/R zone multipliers based on historical success

---

## 📖 Strategy Explanation

### The CLC Framework

The bot evaluates every potential trade using three layers:

```
┌─────────────────────────────────────────┐
│  1. CONTEXT (25% weight)                │
│  ↓ Is the market structure favorable?  │
│                                         │
│  2. LOCATION (30% weight)               │
│  ↓ Are we at a key S/R zone?          │
│                                         │
│  3. CONFIRMATION (25% weight)           │
│  ↓ Is order flow confirming direction? │
│                                         │
│  4. BIG ORDERS (20% weight)             │
│  ↓ Institutional activity detected?    │
│                                         │
│  = TOTAL CLC SCORE (0-100)              │
│    Need ≥75 to enter trade              │
└─────────────────────────────────────────┘
```

### 1️⃣ CONTEXT ANALYSIS (Market Structure)

**What it checks:**
- **Trend alignment**: Are 1m, 5m, 15m timeframes aligned?
- **VWAP position**: Is price above/below VWAP?
- **MA alignment**: Are MAs stacked correctly?
- **Recent momentum**: Strong directional candles?

**Scoring:**
- Each bullish/bearish signal adds to context score
- Stronger signals (multi-timeframe alignment) count more
- Score normalized to 0-100 scale

**Example (LONG):**
```
✓ Price above VWAP (+15 points)
✓ 1m, 5m, 15m all uptrending (+25 points)
✓ MA(20) < MA(50) < Price (+15 points)
✓ 3 consecutive green candles (+10 points)
= Context Score: 65/100
```

### 2️⃣ LOCATION DETECTION (S/R Zones)

**How S/R zones are detected:**

The bot uses **6 independent methods** that "vote" on price levels:

#### Method 1: Frequency-Based Detection
- Scans last 100 candles on 15m timeframe
- Identifies swing highs and swing lows
- Groups similar levels within 0.3%

#### Method 2: Volume Profile
- Divides price range into buckets
- Calculates volume at each bucket
- Top 5 volume nodes become S/R zones
- Point of Control (POC) = highest volume level

#### Method 3: Liquidity Heatmap
- Estimates stop loss clusters
- Above swing highs (resistance from shorts' stops)
- Below swing lows (support from longs' stops)
- Areas with 2× expected volume become zones

#### Method 4: Fibonacci Retracements
- Uses last 100 candles to find swing range
- Calculates 0.236, 0.382, 0.5, 0.618, 0.786 levels
- Each level becomes potential S/R zone

#### Method 5: Psychological Levels
- Round numbers that traders watch
- BTC: Every $500 ($50,000, $50,500, $51,000)
- ETH: Every $50 ($3,000, $3,050, $3,100)
- Active within ±2% of current price

#### Method 6: Manual Zones
- Human-marked levels from dashboard
- Automatically boosted by 50%
- Track hits, bounces, false breaks
- Adjust strength based on performance

**Confluence Calculation:**
```python
if 4+ methods agree: +50% strength bonus
if 3 methods agree:  +30% strength bonus
if 2 methods agree:  +15% strength bonus
if manual zone:      +50% strength bonus
```

**Zone Strength Factors:**
- Number of methods that detected it
- Historical bounce rate
- Volume at level
- Number of touches
- Manual override boost

**Location Score:**
```
if price within zone bounds:
    score = zone_strength × 10  # 0-100 scale
    if manual zone:
        score *= 1.5
else:
    score = 0
```

### 3️⃣ ORDER FLOW CONFIRMATION

**What it detects:**
1. **Absorption** (Tier 1 - Institutional)
   - Large buy volume but price doesn't move up = sellers absorbing
   - Large sell volume but price doesn't move down = buyers absorbing
   - Indicates institutional positioning

2. **Spoofing Detection** (Tier 1)
   - Large orders that appear and disappear quickly
   - Fake liquidity meant to manipulate

3. **Tape Momentum** (Tier 2)
   - Consecutive aggressive buys/sells
   - Indicates retail momentum

4. **Volume Spike** (Tier 2)
   - Current volume > 2× average
   - Shows increased interest

5. **Spread Tightening** (Tier 2)
   - Bid-ask spread narrowing before move
   - Better liquidity conditions

**Scoring:**
- Tier 1 signals (absorption, spoofing): 30-40 points each
- Tier 2 signals (momentum, volume, spread): 10-20 points each
- Need 2+ signals for high confirmation score

### 4️⃣ BIG ORDERS DETECTION

**Detection Logic:**
```python
big_order_threshold = median_order_size × 5

if order_size > big_order_threshold:
    # Classify as institutional activity
    # Check if directional or neutral
    # Add to big_orders_score
```

**Types:**
- **Aggressive Big Buy**: Market buy > threshold
- **Aggressive Big Sell**: Market sell > threshold
- **Passive Big Bid**: Limit buy at support
- **Passive Big Ask**: Limit sell at resistance

**Scoring:**
- Each big order: 20-30 points
- Directional alignment: +10 bonus
- Multiple big orders: cumulative

---

## 📈 LONG Entry Logic (Step by Step)

### Phase 1: Pre-Checks
```
✓ Market open (not in cooldown)
✓ No existing position
✓ Not at daily loss limit ($30)
✓ Spread reasonable (<20 bps)
✓ Sufficient volume (> 50% of 24h avg)
```

### Phase 2: Context Analysis (Bullish)
```
Check for bullish structure:
- Price > VWAP
- Price > MA(20) and MA(50)
- 1m, 5m, 15m trends aligned up
- Recent green candles
→ Context Score calculated (target: 60+)
```

### Phase 3: Location Detection
```
Run all 6 S/R detection methods:
1. Frequency: Find recent swing lows
2. Volume Profile: Identify high-volume support
3. Liquidity: Locate stop clusters below
4. Fibonacci: Calculate retracement levels
5. Psychological: Check for round number support
6. Manual: Check human-marked zones

Consolidate zones within 0.3%
Calculate confluence scores
Select best support zone
→ Location Score calculated (target: 70+)
```

### Phase 4: Check if Price at Support Zone
```
current_price within [zone.lower_bound, zone.upper_bound]?

If YES:
    at_location = True
    Use zone strength for scoring
If NO:
    at_location = False
    Location score reduced to 20
```

### Phase 5: Order Flow Confirmation (Bullish)
```
Check for bullish order flow:
- Buying absorption at support? (Tier 1)
- Sell spoofing detected? (Tier 1)
- Consecutive aggressive buys? (Tier 2)
- Volume spike? (Tier 2)
- Spread tightening? (Tier 2)

Count signals:
→ Confirmation Score (target: 60+)
```

### Phase 6: Big Orders Detection (Bullish)
```
Scan recent trades for:
- Big aggressive buys
- Big passive bids at support

If detected:
→ Big Orders Score (target: 50+)
```

### Phase 7: Calculate CLC Score
```python
total_score = (
    context_score * 0.25 +
    location_score * 0.30 +
    confirmation_score * 0.25 +
    big_orders_score * 0.20
)

# Apply learning adjustments if enabled
if learning_enabled:
    adjusted_threshold = feedback_system.get_adjusted_threshold('LONG', 75.0)
else:
    adjusted_threshold = 75.0
```

### Phase 8: ML Override (Optional)
```python
if ml_enabled and total_score >= 65:
    win_probability = ml_model.predict(trade_features)

    if win_probability >= 0.65:
        # ML is confident - take trade even if score < 75
        enter_long()
    elif total_score >= adjusted_threshold:
        # Score high enough without ML
        enter_long()
    else:
        # Neither condition met
        reject_trade()
```

### Phase 9: Entry Execution
```python
if total_score >= adjusted_threshold or ml_override:
    # Calculate position size
    position_size = min(
        config.position_size_usdt,
        balance × (leverage/100)
    )

    # Calculate stops
    stop_loss = entry_price - (config.stop_loss_points / current_price)
    take_profit = entry_price + (config.take_profit_points / current_price)

    # Execute market order
    place_market_order('BUY', position_size, leverage)

    # Set stop loss and take profit
    place_stop_loss_order(stop_loss)
    place_take_profit_order(take_profit)

    # Generate explanation
    explanation = create_trade_explanation(...)
    save_explanation(explanation)
```

---

## 📉 SHORT Entry Logic (Step by Step)

### Phase 1: Pre-Checks
```
✓ Market open (not in cooldown)
✓ No existing position
✓ Not at daily loss limit ($30)
✓ Spread reasonable (<20 bps)
✓ Sufficient volume (> 50% of 24h avg)
```

### Phase 2: Context Analysis (Bearish)
```
Check for bearish structure:
- Price < VWAP
- Price < MA(20) and MA(50)
- 1m, 5m, 15m trends aligned down
- Recent red candles
→ Context Score calculated (target: 60+)
```

### Phase 3: Location Detection
```
Run all 6 S/R detection methods:
1. Frequency: Find recent swing highs
2. Volume Profile: Identify high-volume resistance
3. Liquidity: Locate stop clusters above
4. Fibonacci: Calculate retracement levels
5. Psychological: Check for round number resistance
6. Manual: Check human-marked zones

Consolidate zones within 0.3%
Calculate confluence scores
Select best resistance zone
→ Location Score calculated (target: 70+)
```

### Phase 4: Check if Price at Resistance Zone
```
current_price within [zone.lower_bound, zone.upper_bound]?

If YES:
    at_location = True
    Use zone strength for scoring
If NO:
    at_location = False
    Location score reduced to 20
```

### Phase 5: Order Flow Confirmation (Bearish)
```
Check for bearish order flow:
- Selling absorption at resistance? (Tier 1)
- Buy spoofing detected? (Tier 1)
- Consecutive aggressive sells? (Tier 2)
- Volume spike? (Tier 2)
- Spread tightening? (Tier 2)

Count signals:
→ Confirmation Score (target: 60+)
```

### Phase 6: Big Orders Detection (Bearish)
```
Scan recent trades for:
- Big aggressive sells
- Big passive asks at resistance

If detected:
→ Big Orders Score (target: 50+)
```

### Phase 7: Calculate CLC Score
```python
total_score = (
    context_score * 0.25 +
    location_score * 0.30 +
    confirmation_score * 0.25 +
    big_orders_score * 0.20
)

# Apply learning adjustments if enabled
if learning_enabled:
    adjusted_threshold = feedback_system.get_adjusted_threshold('SHORT', 75.0)
else:
    adjusted_threshold = 75.0
```

### Phase 8: ML Override (Optional)
```python
if ml_enabled and total_score >= 65:
    win_probability = ml_model.predict(trade_features)

    if win_probability >= 0.65:
        # ML is confident - take trade even if score < 75
        enter_short()
    elif total_score >= adjusted_threshold:
        # Score high enough without ML
        enter_short()
    else:
        # Neither condition met
        reject_trade()
```

### Phase 9: Entry Execution
```python
if total_score >= adjusted_threshold or ml_override:
    # Calculate position size
    position_size = min(
        config.position_size_usdt,
        balance × (leverage/100)
    )

    # Calculate stops
    stop_loss = entry_price + (config.stop_loss_points / current_price)
    take_profit = entry_price - (config.take_profit_points / current_price)

    # Execute market order
    place_market_order('SELL', position_size, leverage)

    # Set stop loss and take profit
    place_stop_loss_order(stop_loss)
    place_take_profit_order(take_profit)

    # Generate explanation
    explanation = create_trade_explanation(...)
    save_explanation(explanation)
```

---

## 🎨 Dashboard Usage

### Running the Dashboard
```bash
streamlit run dashboard.py
```

Opens at `http://localhost:8501`

### Tab 1: Chart & Trades
- **Select Symbol**: BTCUSDT or ETHUSDT
- **Select Date Range**: Last 7/14/30 days or custom
- **Click "Run Backtest"**: Processes historical data
- **View Trade Timeline**: Each trade shown with entry/exit
- **Expand Trade**: See full explanation (why taken, what detected)

### Tab 2: Performance Metrics
- **Overall Statistics**: Win rate, profit factor, Sharpe ratio
- **Equity Curve**: Balance over time
- **Drawdown Chart**: Peak-to-trough drops
- **Trade Distribution**: Win/loss by hour, day, direction

### Tab 3: ML Insights
- **Model Performance**: Training/test accuracy
- **Feature Importance**: Which factors matter most
- **Win Probability Distribution**: How confident was ML
- **Parameter Suggestions**: Recommended threshold adjustments

### Tab 4: Rate Trades
- **Select Trade**: Dropdown of all backtest trades
- **View Explanation**: Full breakdown of the setup
- **Rate 1-5 Stars**: 5 = excellent, 1 = terrible
- **Add Notes**: Why you rated it this way
- **Submit**: Saves to feedback system
- **Auto-Retrain**: ML retrains every 10 ratings

### Tab 5: Missed Setups
- **Mark Opportunity**: Price level bot should have entered
- **Select Direction**: LONG or SHORT
- **Choose Reasons**: Why was this a good setup?
  - S/R bounce
  - Strong volume
  - Clear rejection
  - Psychological level
  - Institutional activity
- **Expected Outcome**: Would have won/lost/uncertain
- **Add Notes**: Context about the missed trade
- **View Analysis**: After 5+ marks, see common patterns

---

## 🔧 Configuration

### Environment Variables (.env)
```bash
# Binance API
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_secret_here
BINANCE_TESTNET=true  # Start with testnet!

# Notifications (optional)
DISCORD_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### Bot Configuration (config/bot_config.yaml)
```yaml
trading:
  symbols: ["BTCUSDT", "ETHUSDT"]
  timeframe: "1m"
  leverage: 50  # Starting leverage
  position_size_usdt: 15.0
  max_positions: 1

strategy:
  entry_threshold: 75.0  # Minimum CLC score
  require_location: true  # Must be at S/R zone
  require_confirmation: true  # Need 2+ order flow signals
  ml_override_enabled: false  # Start disabled

risk:
  per_trade_max_loss_usdt: 15.0
  daily_max_loss_usdt: 30.0
  stop_loss_points: 200  # BTC points
  take_profit_points: 200  # 1:1 R/R
  partial_profit_pct: 0.5  # Take 50% at 1:1
  trailing_stop_enabled: true

sr_detection:
  lookback_candles: 100
  zone_size_pct: 0.003  # 0.3% zone width
  min_zone_strength: 5.0  # 0-10 scale
  confluence_bonus_2methods: 0.15
  confluence_bonus_3methods: 0.30
  confluence_bonus_4methods: 0.50

learning:
  enabled: false  # Enables after 30 quality ratings
  min_samples_for_ml: 100
  retrain_every_n_trades: 100
  feedback_file: "data/feedback.json"
```

---

## 📂 Project Structure

```
trabot/
├── src/
│   ├── strategy/
│   │   ├── clc_engine.py          # Main CLC scoring logic
│   │   ├── location_detector.py   # 6-method S/R detection
│   │   └── order_flow_analyzer.py # Tape reading, absorption
│   ├── learning/
│   │   ├── ml_optimizer.py        # Random Forest trade filtering
│   │   └── feedback_system.py     # Human rating storage
│   ├── backtesting/
│   │   └── backtest_engine.py     # Historical simulation
│   ├── utils/
│   │   ├── trade_explainability.py  # Explanation generation
│   │   └── logger.py              # Logging setup
│   └── config.py                  # Configuration loading
├── config/
│   └── bot_config.yaml            # Main configuration
├── data/
│   ├── feedback.json              # Trade ratings
│   ├── manual_zones.json          # Human-marked S/R zones
│   └── backtest_results/          # Backtest outputs
├── dashboard.py                   # Streamlit UI
├── run_backtest.py               # CLI backtest runner
├── main.py                       # Live trading entry point
├── requirements.txt
├── README.md                     # This file
├── BACKTESTING_GUIDE.md          # Detailed backtest docs
└── ENTRY_LOGIC_EXPLAINED.md      # Full entry logic breakdown
```

---

## 🎯 Getting Started (First Time Users)

### Step 1: Install and Configure
```bash
# Clone repo
git clone <repo-url>
cd trabot

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
nano .env  # Add your Binance API keys

# Keep BINANCE_TESTNET=true for now!
```

### Step 2: Run Your First Backtest
```bash
# Test 7 days of BTC
python run_backtest.py --symbol BTCUSDT --days 7

# Expected results:
# - Win Rate: 50-60%
# - Profit Factor: 1.5-2.5
# - ROI: +30% to +70% per week
# - Max Drawdown: <20%
```

### Step 3: Launch Dashboard
```bash
streamlit run dashboard.py

# 1. Select BTCUSDT, last 7 days
# 2. Click "Run Backtest"
# 3. Review trades in Chart & Trades tab
# 4. Go to "Rate Trades" tab
# 5. Rate 30+ trades (be honest!)
# 6. Learning will auto-enable
```

### Step 4: Validate Strategy
```bash
# Run multiple backtests
python run_backtest.py --symbol BTCUSDT --days 30
python run_backtest.py --symbol ETHUSDT --days 30

# Check consistency:
# - Win rate stable across periods?
# - Profit factor > 1.5 consistently?
# - Drawdowns manageable?
```

### Step 5: Paper Trade
```bash
# In .env, keep BINANCE_TESTNET=true
# Start the bot
python main.py

# Monitor for 1-2 weeks:
# - Are live results similar to backtest?
# - Any execution issues?
# - Slippage acceptable?
```

### Step 6: Go Live (When Ready)
```bash
# In .env, set BINANCE_TESTNET=false
# Start with minimum position size
# Increase gradually as confidence builds

# ONLY GO LIVE IF:
✓ Backtest win rate > 50%
✓ Backtest profit factor > 1.5
✓ Paper trading successful for 2+ weeks
✓ You understand all risks
✓ You can afford to lose the capital
```

---

## 📊 Expected Performance

### Target Metrics (Based on $100 Starting Capital)
```
Daily Target:        $10 profit (10% daily ROI)
Weekly Target:       ~$70 profit (70% weekly ROI)
Monthly Target:      ~$300 profit (300% monthly ROI)

Win Rate:            50-60%
Profit Factor:       1.5-2.5
Average Win:         $12-15
Average Loss:        $8-10
Trades per Day:      3-8
Risk per Trade:      $10-15
Max Daily Drawdown:  $30 (stop trading if hit)
```

### Realistic Expectations
- **Good Week**: +50% to +100% ROI
- **Average Week**: +20% to +50% ROI
- **Bad Week**: -10% to +10% ROI
- **Monthly**: +100% to +200% ROI (if consistent)

### When Things Go Wrong
- **3 losses in a row**: Reduce position size by 30%
- **Daily loss limit hit**: Stop trading for the day
- **Weekly loss > -20%**: Review trades, adjust parameters
- **Monthly loss**: Pause, re-evaluate strategy

---

## 🔍 Advanced Topics

### How to Mark S/R Zones Manually

**Option 1: Via Dashboard**
1. Go to "Chart & Trades" tab
2. Click "Add Manual Zone" button
3. Enter price level (e.g., 50000.0 for BTC)
4. Select type: Support, Resistance, or Both
5. Zone automatically tracked and validated

**Option 2: Via Code**
```python
from src.learning.feedback_system import AdaptiveFeedbackSystem
from config import load_config

config = load_config()
feedback = AdaptiveFeedbackSystem(config)

# Add support zone at $50,000
zone = feedback.add_manual_zone(
    price_level=50000.0,
    zone_type='support',
    size_pct=0.003  # 0.3% zone width
)

# Zone automatically gets 50% strength boost
# Performance tracked across all future touches
```

### How Learning Works

**Phase 1: Collection (0-30 ratings)**
- Bot trades normally with default parameters
- You rate trades 1-5 stars
- System calculates "quality score" (how aligned your ratings are with outcomes)

**Phase 2: Learning Enabled (30+ quality ratings)**
- `learning_enabled` flag set to `True`
- Bot starts using human feedback to adjust thresholds
- Manual zones get extra weight
- Missed setup patterns influence future entries

**Phase 3: ML Training (100+ trades)**
- Random Forest model trains on historical outcomes
- 18 features extracted per trade
- Model predicts win probability for new setups
- Can override CLC score if highly confident

**Phase 4: Continuous Improvement (ongoing)**
- Model retrains every 100 trades
- Parameter adjustments based on recent performance
- Zone strengths updated based on bounce rate
- Adaptive thresholds for different market conditions

### Debugging Poor Performance

**Win Rate < 40%?**
- Raise `entry_threshold` in config (try 80.0)
- Set `require_location: true` to force S/R entries
- Review context analysis - might be entering against trend

**Too Few Trades?**
- Lower `entry_threshold` (try 70.0)
- Reduce `min_zone_strength` to 4.0
- Check if `require_confirmation` is too strict

**Large Drawdowns?**
- Reduce `leverage` (try 30× instead of 50×)
- Lower `position_size_usdt` (try $10 instead of $15)
- Tighten `stop_loss_points` (try 150 instead of 200)
- Enable `trailing_stop_enabled`

**ML Performing Poorly?**
- Need 100+ trades for training
- Check feature importance - which features matter?
- May need more human ratings (aim for 50+)
- Consider disabling ML until more data collected

### Modifying Detection Methods

**Add Your Own Detection Method:**

Edit `src/strategy/location_detector.py`:

```python
def _detect_custom_method(self, candles, current_price, direction):
    """
    Your custom S/R detection logic here.

    Returns:
        List[SRZone]: Detected zones
    """
    zones = []

    # Example: Detect gaps in price action
    for i in range(1, len(candles)):
        gap = candles[i]['open'] - candles[i-1]['close']
        if abs(gap / current_price) > 0.01:  # 1% gap
            zones.append(SRZone(
                level=(candles[i]['open'] + candles[i-1]['close']) / 2,
                zone_type='both',
                strength=7.0,
                methods=[SRDetectionMethod.CUSTOM],
                # ... other fields
            ))

    return zones

# Add to detect_all_zones()
custom_zones = self._detect_custom_method(candles, current_price, direction)
all_zones.extend(custom_zones)
```

---

## ⚠️ Risk Warnings

### Critical Risks
- **Leverage Risk**: 50-100× leverage can liquidate account in seconds
- **API Risk**: Exchange downtime can prevent closing positions
- **Slippage Risk**: Fast markets may not fill at expected prices
- **Bug Risk**: Code errors could cause unintended trades
- **Market Risk**: Crypto is highly volatile, gaps/wicks happen

### Safety Measures Implemented
- ✅ Hard per-trade loss limit ($15)
- ✅ Hard daily loss limit ($30)
- ✅ Automatic leverage scaling as balance grows
- ✅ Stop loss on every trade
- ✅ Partial profit taking at 1:1 R/R
- ✅ Trailing stops after profit threshold
- ✅ Paper trading mode (testnet)
- ✅ Position limit (1 at a time)
- ✅ Spread checks before entry
- ✅ Volume checks before entry

### Best Practices
1. **Start with testnet** - Use fake money first
2. **Start small** - Use minimum capital you can afford to lose
3. **Monitor daily** - Check bot at least once per day
4. **Review trades weekly** - Understand what it's doing
5. **Keep learning enabled** - Your feedback improves it
6. **Never invest money you need** - Only risk capital
7. **Have a kill switch** - Know how to stop the bot instantly
8. **Diversify** - Don't put all capital in one bot

---

## 🛠️ Troubleshooting

### Bot Won't Start
```bash
# Check Python version (need 3.8+)
python --version

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Check API keys
cat .env | grep BINANCE_API

# Test API connection
python -c "from src.exchange.binance_client import BinanceClient; import asyncio; asyncio.run(BinanceClient({}).test_connection())"
```

### Dashboard Not Loading
```bash
# Check Streamlit installation
pip show streamlit

# Clear Streamlit cache
streamlit cache clear

# Run with verbose logging
streamlit run dashboard.py --logger.level=debug
```

### Backtest Errors
```bash
# Check data directory exists
mkdir -p data/backtest_results

# Run with smaller date range
python run_backtest.py --symbol BTCUSDT --days 1

# Check Binance API limits
# (Public data has rate limits)
```

### No Trades Being Taken
```bash
# Check thresholds in config
cat config/bot_config.yaml | grep threshold

# Run with lower threshold temporarily
# Edit bot_config.yaml: entry_threshold: 65.0

# Check location detection
# Add debug logging to location_detector.py
```

---

## 📚 Additional Resources

- **BACKTESTING_GUIDE.md** - Complete guide to backtesting system
- **ENTRY_LOGIC_EXPLAINED.md** - Detailed breakdown of every entry condition
- **config/bot_config.yaml** - All configurable parameters with comments

---

## 💬 Support & Community

- **Issues**: Use GitHub issues for bugs
- **Questions**: Use GitHub discussions for questions
- **Feature Requests**: Submit via GitHub issues with [FEATURE] tag

---

## 📜 License

[Your License Here]

---

## ⚡ Quick Reference

### Common Commands
```bash
# Backtest
python run_backtest.py --symbol BTCUSDT --days 7

# Dashboard
streamlit run dashboard.py

# Live bot (testnet)
python main.py

# Live bot (real money)
# Set BINANCE_TESTNET=false in .env first
python main.py
```

### Configuration Quick Edits
```bash
# Lower entry threshold (more trades)
sed -i 's/entry_threshold: 75.0/entry_threshold: 70.0/' config/bot_config.yaml

# Reduce leverage (safer)
sed -i 's/leverage: 50/leverage: 30/' config/bot_config.yaml

# Increase stop loss (tighter)
sed -i 's/stop_loss_points: 200/stop_loss_points: 150/' config/bot_config.yaml
```

### Emergency Stop
```bash
# Kill the bot
pkill -f main.py

# Close all positions (via Binance API)
python -c "from src.exchange.binance_client import BinanceClient; import asyncio; c = BinanceClient({}); asyncio.run(c.close_all_positions())"
```

---

**Built with ❤️ for scalpers who demand precision.**
