# 🔬 Backtesting Guide - CLC Scalper Bot

## Overview

This guide explains how to use the **hybrid backtesting system** that:
- ✅ Fetches **real historical data** from Binance (klines + order flow)
- ✅ Makes **simulated paper trades** with realistic fills
- ✅ Tests your strategy **before risking real money**
- ✅ Generates comprehensive performance metrics

---

## 🚀 Quick Start

### 1. Run Your First Backtest

```bash
# Backtest last 7 days on BTCUSDT
python run_backtest.py --symbol BTCUSDT --days 7

# Backtest specific date range
python run_backtest.py --symbol BTCUSDT --start 2025-01-01 --end 2025-01-07

# Backtest on ETHUSDT with 5-minute execution
python run_backtest.py --symbol ETHUSDT --days 14 --timeframe 5m
```

### 2. Interpret Results

After backtest completes, you'll see:

```
==================================================
BACKTEST RESULTS
==================================================
Starting Balance: $100.00
Ending Balance: $142.50
Net P&L: +$42.50
ROI: +42.50%

Total Trades: 28
Winning Trades: 17
Losing Trades: 11
Win Rate: 60.71%

Average Win: $4.20
Average Loss: $2.10
Largest Win: $12.50
Largest Loss: $7.80
Profit Factor: 2.15
Expectancy: $1.52 per trade
Risk/Reward Ratio: 2.00

Max Drawdown: $12.30 (12.30%)
Max Consecutive Losses: 3
Sharpe Ratio: 1.82

Trades per Day: 4.00
Avg Trade Duration: 18.5 minutes

Long Trades: 15 (Win Rate: 66.67%)
Short Trades: 13 (Win Rate: 53.85%)

Total Fees: $8.90
==================================================
```

---

## 📊 How the Backtesting System Works

### Architecture

```
┌─────────────────────────────────────────────────┐
│  1. FETCH REAL DATA FROM BINANCE               │
│     • Historical klines (OHLCV candles)         │
│     • Multiple timeframes (1m, 15m, 1h)         │
│     • Actual market data, not synthetic         │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  2. SIMULATE ORDERBOOK & TRADES                 │
│     • Build orderbook state from candles        │
│     • Distribute volume to simulate trades      │
│     • Realistic spread & slippage               │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  3. RUN CLC STRATEGY ON EACH CANDLE             │
│     • Context Analysis (VWAP, EMAs, bias)       │
│     • Location Detection (S/R, psychological)   │
│     • Confirmation (order flow simulation)      │
│     • Big Orders (large trade detection)        │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  4. SIMULATE POSITION MANAGEMENT                │
│     • Entry at close price (realistic fill)     │
│     • Stop loss checked against high/low        │
│     • Take profit checked against high/low      │
│     • Trailing stops, partials, risk limits     │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  5. TRACK & CALCULATE METRICS                   │
│     • P&L tracking                              │
│     • Win rate, profit factor                   │
│     • Drawdown analysis                         │
│     • Sharpe ratio, expectancy                  │
└─────────────────────────────────────────────────┘
```

---

## 🎯 Detailed Entry Logic Flow (What Actually Happens)

### Example: LONG Entry at $50,000 BTC

#### Step 1: Pre-Checks (Fast Rejections)
```python
✓ No existing BTC position
✓ Under max positions limit (1/1)
✓ Daily P&L above loss limit (-$15 > -$30)
✓ Trading hours OK (2:15 PM UTC = NY session)
✓ No recent loss at this level (last loss was at $49,500)
✓ Cooldown passed (5 minutes since last trade)

→ Proceed to evaluation
```

#### Step 2: Context Analysis (Multi-Timeframe)
```python
# 1H Timeframe
Current: $50,000
VWAP:    $49,850  → Price above VWAP (+20 points)
EMA50:   $50,200
EMA200:  $49,500  → Bullish structure (+25 points)
Bias:    BULLISH ✓

# 15M Timeframe
Current: $50,000
VWAP:    $49,900  → Above VWAP
EMA50 > EMA200    → Bullish
Bias:    BULLISH ✓

# 1M Timeframe
Current: $50,000
Price action: Higher highs, higher lows
Bias:    BULLISH ✓

# Alignment Check
All timeframes BULLISH → +30% score bonus
Context Score: 45 × 1.3 = 58.5 points
```

#### Step 3: Location Detection (6 Methods Vote)
```python
DETECTED ZONES NEAR $50,000:

Method 1 (Frequency):     $49,800 (5 touches) ✓
Method 2 (Volume Profile): $49,850 (high vol node) ✓
Method 3 (Liquidity):     $49,750 (stop cluster)
Method 4 (Fibonacci):     $49,854 (0.618 retrace) ✓
Method 5 (Psychological): $50,000 (round number) ✓✓
Method 6 (Manual - You):  $49,800 (5 stars) ✓✓

CONSOLIDATION:
Zone at $49,820 (avg of 49,800, 49,850, 49,854)
  • Detected by: 4 methods
  • Human marked: YES
  • Strength: 10.0/10 ⭐⭐⭐⭐⭐

Current price $50,000 is 0.36% away → AT LOCATION ✓

Location Score: 40 × (10/10) = 40 points
```

#### Step 4: Order Flow Confirmation (Read the Tape)
```python
SIMULATED ORDERBOOK:
Bid volume (top 10): $1,500,000
Ask volume (top 10): $800,000
Imbalance: 65% bids (below 70% threshold) ✗

SIMULATED TRADES (last 200):
Buy volume:  120 BTC
Sell volume: 60 BTC
Cumulative Delta: +33% (below 60% threshold) ✗

ABSORPTION DETECTED: ✓✓ (TIER 1)
  • Large bid at $49,995 hit 5× without price drop
  • Someone accumulating
  • +25 points

LARGE MARKET ORDER: ✓✓ (TIER 1)
  • $120,000 market BUY at 14:32:15
  • Above $50k threshold
  • +30 points

SWEEP DETECTED: ✓
  • Price ran 49,980 → 50,010 in 3 seconds
  • +15 points

Confirmation Score: 25 + 30 + 15 = 70 points
Tier 1 Signals: 2 (absorption + large order) ✓✓
```

#### Step 5: Big Orders Analysis
```python
INSTITUTIONAL FLOW:

Large Market Order: $120k BUY ✓
  • Score: +30 points

Iceberg Detected: Bid at $49,990 ✓
  • Refilled 4 times in 20 seconds
  • Score: +30 points

Big Orders Score: 60 points
```

#### Step 6: Calculate Total CLC Score
```python
WEIGHTED SCORING:

Context:      58.5 × 0.25 = 14.6
Location:     40.0 × 0.30 = 12.0
Confirmation: 70.0 × 0.25 = 17.5
Big Orders:   60.0 × 0.20 = 12.0
                           ------
Total (raw):                56.1

BIAS CHECK:
Expected: BULLISH (we want LONG)
Actual:   BULLISH
Penalty:  NONE (1.0×)

Final CLC Score: 56.1
```

#### Step 7: Entry Criteria Check
```python
REQUIREMENTS:

min_entry_score (75):          56.1 ✗ TOO LOW
at_location:                   TRUE ✓
min_confirmation_signals (2):  3 signals ✓
min_tier1_signals (1):         2 signals ✓✓

RESULT: REJECTED (score too low)
```

#### Step 8: ML Override (If Enabled)
```python
ML FEATURE VECTOR:
[56.1, 58.5, 40.0, 70.0, 60.0, 14, 2, 2.5, 1.8,
 150, 0.014, 1, 3, 1, 0.0, 10.0, 1, 1]

ML PREDICTION: 68% win probability

ML REASONING:
"Despite low CLC score, this setup has:
 ✓ Perfect timeframe alignment (1H+15M+1M)
 ✓ At psychological $50k level (strength 10.0)
 ✓ 2× Tier 1 signals (absorption + $120k order)
 ✓ NY session (historically high win rate)
 ✓ High volume (1.8× average)

Historical similar trades: 68% win rate"

ML DECISION: OVERRIDE & APPROVE ✓
```

#### Step 9: Human Feedback Boost (If Available)
```python
CHECKING YOUR FEEDBACK HISTORY...

Found 3 similar setups you rated highly:
  • $50k psychological level LONG → 5 stars
  • Absorption + large order → 4 stars
  • Timeframe aligned → 4 stars

Average rating: 4.3/5 stars

Human Confidence Boost: +13%
Adjusted Score: 56.1 × 1.13 = 63.4

(ML already overrode, so this is confirmatory)
```

#### Step 10: Execute Trade
```python
POSITION DETAILS:

Entry Price: $50,000
Direction:   LONG
Quantity:    0.1 BTC ($5,000 notional @ 50× leverage)
Stop Loss:   $49,850 (150 points risk)
Take Profit: $50,200 (200 points target)
Risk/Reward: 1:1.33

Risk Amount: $15 (15% of $100 balance)
Target Gain: $20

ENTRY CONFIRMED ✓
```

---

## 📈 Understanding Backtest Metrics

### Win Rate
- **Good:** 55-65%
- **Acceptable:** 50-55%
- **Poor:** <50%

**Why:** With 1:1.33 R/R, need 50%+ to be profitable

### Profit Factor
- **Excellent:** >2.0
- **Good:** 1.5-2.0
- **Acceptable:** 1.2-1.5
- **Poor:** <1.2

**Formula:** Total Wins / Total Losses

### Sharpe Ratio
- **Excellent:** >1.5
- **Good:** 1.0-1.5
- **Acceptable:** 0.5-1.0
- **Poor:** <0.5

**Why:** Measures risk-adjusted returns

### Max Drawdown
- **Excellent:** <15%
- **Good:** 15-25%
- **Acceptable:** 25-35%
- **Dangerous:** >35%

**Why:** Shows largest peak-to-trough loss

### Expectancy
- **Good:** >$2 per trade (on $100 balance)
- **Acceptable:** $1-$2
- **Poor:** <$1

**Formula:** (Win% × Avg Win) - (Loss% × Avg Loss)

---

## 🔍 Debugging Poor Performance

### Low Win Rate (<50%)

**Possible Issues:**
1. Entry threshold too low (taking low-quality setups)
2. Not filtering by timeframe alignment
3. Trading during low-liquidity sessions
4. Counter-trend entries not penalized enough

**Solutions:**
```yaml
# Increase min_entry_score
scoring:
  min_entry_score: 80  # from 75

# Require timeframe alignment
clc_strategy:
  context:
    min_timeframe_alignment_score: 70  # from 50

# Add session filter
trading:
  session_filters:
    enabled: true
```

### High Drawdown (>30%)

**Possible Issues:**
1. Position size too large
2. No daily loss limit enforcement
3. Stops too wide
4. No correlation management

**Solutions:**
```yaml
risk:
  per_trade_max_loss_usdt: 10.0  # Reduce from 15
  max_daily_loss_usdt: 25.0      # Reduce from 30
  max_consecutive_losses: 2      # Pause sooner

trading:
  position_size_usdt: 10.0  # Reduce exposure
```

### Low Profit Factor (<1.5)

**Possible Issues:**
1. Winners not big enough (early exits)
2. Losers too large (stops too wide)
3. Fee erosion (overtrading)

**Solutions:**
```yaml
# Enable partials (lock in profits)
risk:
  partial_exits:
    enabled: true
    first_exit:
      percentage: 0.5
      trigger_rr: 1.0

# Tighten stops
trading:
  btc_risk_points: 120  # from 150
  eth_risk_points: 8    # from 10

# Reduce trade frequency
trading:
  min_time_between_trades_seconds: 300  # 5 min cooldown
```

---

## 🎓 Next Steps After Backtesting

### If Results Are Good (Win Rate >55%, Profit Factor >1.5)

1. **Run Multiple Backtests**
   ```bash
   # Test different periods
   python run_backtest.py --symbol BTCUSDT --start 2024-12-01 --end 2024-12-07
   python run_backtest.py --symbol BTCUSDT --start 2024-12-15 --end 2024-12-22
   python run_backtest.py --symbol BTCUSDT --start 2025-01-01 --end 2025-01-07
   ```

2. **Test Both Symbols**
   ```bash
   python run_backtest.py --symbol BTCUSDT --days 14
   python run_backtest.py --symbol ETHUSDT --days 14
   ```

3. **Move to Paper Trading**
   - Switch to `paper_trading: true` in config
   - Run bot with real-time data (testnet API)
   - Track performance for 1-2 weeks

4. **Add Human Feedback**
   - Use Streamlit dashboard to rate trades
   - Mark S/R zones manually
   - Bot learns your style

5. **Enable ML Optimizer**
   - After 100+ trades, enable ML
   - Let model filter low-quality setups
   - Monitor for overfitting

### If Results Are Poor

1. **Analyze Trade Log**
   ```bash
   # Check data/backtest_results/trades_[timestamp].json
   # Find common losing patterns
   ```

2. **Adjust Parameters**
   - Increase entry threshold
   - Add time filters
   - Tighten risk management

3. **Retest**
   ```bash
   # Run backtest again with new settings
   python run_backtest.py --symbol BTCUSDT --days 7
   ```

4. **Iterate**
   - Keep tweaking until metrics improve
   - Never go live with poor backtest results

---

## 📁 Output Files

After backtest, find results in `data/backtest_results/`:

```
data/backtest_results/
├── metrics_1736524800.json   # Performance summary
├── trades_1736524800.json    # Full trade log
└── equity_1736524800.csv     # Equity curve data
```

### Metrics File Example
```json
{
  "timestamp": 1736524800,
  "starting_balance": 100.0,
  "ending_balance": 142.5,
  "metrics": {
    "total_trades": 28,
    "win_rate": "60.71%",
    "net_pnl": "$42.50",
    "roi": "+42.50%",
    "profit_factor": "2.15",
    "sharpe_ratio": "1.82"
  }
}
```

### Trades File Example
```json
[
  {
    "symbol": "BTCUSDT",
    "direction": "LONG",
    "entry_price": 50000.0,
    "exit_price": 50200.0,
    "quantity": 0.1,
    "pnl": 20.0,
    "fees": 2.0,
    "net_pnl": 18.0,
    "exit_reason": "take_profit",
    "duration_minutes": 23.5,
    "clc_score": {
      "total_score": 82.5,
      "context_score": 58.5,
      "location_score": 40.0,
      "confirmation_score": 70.0
    }
  }
]
```

---

## 🤝 How Systems Work Together

### 1. Multi-Method S/R Detection
- **During Backtest:** All 6 methods scan each candle for zones
- **Confluence Scoring:** Zones detected by multiple methods get higher strength
- **Human Marks:** Your manual zones get 50% boost automatically

### 2. Human Feedback Integration
- **After Backtest:** Review trade log in Streamlit dashboard
- **Rate Trades:** Mark good/bad trades (1-5 stars)
- **Bot Learns:** Next backtest adjusts weights based on your feedback
- **Example:** If you consistently rate "psychological level + absorption" as 5 stars, bot increases weight for those combinations

### 3. ML Optimizer
- **After 100 Trades:** Model trains on historical performance
- **Feature Learning:** Discovers which factors predict wins
- **Next Backtest:** ML filters entries (requires 55%+ win probability)
- **Continuous:** Retrains every 100 trades, adapts to patterns

---

## 🎯 Target Metrics for $10/Day Goal

With $100 starting capital and $10/day target:

```
Required Performance:
  • Win Rate: 55-60%
  • Trades per Day: 4-5
  • Expectancy: $2-2.50 per trade
  • Max Drawdown: <25%

Acceptable Performance:
  • Daily P&L: $8-$15
  • Weekly ROI: 50-100%
  • Monthly ROI: 200-400%

Red Flags:
  • Win Rate < 50%
  • Profit Factor < 1.3
  • Max Drawdown > 35%
  • Trades per Day < 2
```

---

## 💡 Tips for Success

1. **Start Conservative**
   - Run 7-day backtest first
   - Gradually extend to 14, 30 days
   - Don't overtune to one period

2. **Test Different Market Conditions**
   - Trending markets
   - Range-bound markets
   - High volatility vs low volatility

3. **Track Metrics Over Time**
   ```bash
   # Compare multiple backtest runs
   ls -la data/backtest_results/
   ```

4. **Use Human Feedback Early**
   - Start marking zones after first backtest
   - Rate trades you agree/disagree with
   - Bot adapts faster with your input

5. **Enable ML After Sufficient Data**
   - Wait for 100+ trades before enabling
   - Monitor for overfitting (train vs test performance)
   - Disable if performance degrades

---

## 🚨 Common Pitfalls

1. **Curve Fitting**: Optimizing only for one period
   - **Solution:** Test on multiple time periods

2. **Ignoring Drawdown**: Focusing only on ROI
   - **Solution:** Max drawdown must be <25%

3. **Overtrading**: Too many low-quality trades
   - **Solution:** Increase entry threshold

4. **Under-trading**: Too few trades to validate
   - **Solution:** Lower threshold slightly or extend backtest period

5. **Ignoring Fees**: Not accounting for 0.2% taker fees
   - **Solution:** Backtest engine includes fees automatically

---

## 📞 Support

If backtest results are unclear or system isn't working:
1. Check logs in `logs/bot.log`
2. Review trade log in `data/backtest_results/`
3. Verify config in `config/bot_config.yaml`

**Remember:** Backtesting is your safety net. Never go live without positive backtest results!
