# 📊 Live Dashboard Guide

Real-time monitoring dashboard for forward testing and live trading.

---

## 🎯 What is the Live Dashboard?

The Live Dashboard shows your bot's trades **in real-time** as they happen. It auto-refreshes every 2 seconds to display:

- ✅ Current open positions (with unrealized P&L)
- ✅ Recently closed trades
- ✅ Running performance metrics
- ✅ Equity curve
- ✅ Trade distribution charts

**Perfect for:**
- Monitoring forward tests as they run
- Watching your bot trade live
- Quick performance overview
- Understanding bot behavior in real-time

---

## 🚀 Quick Start

### Step 1: Start Forward Test

```bash
# Terminal 1 - Start forward testing
python run_forward_test.py
```

The bot will:
- Connect to live market data
- Analyze in real-time
- Simulate trades (no real orders)
- Save results to `data/forward_test_results.json` every 10 seconds

### Step 2: Open Live Dashboard

```bash
# Terminal 2 - Open dashboard
streamlit run dashboard_live.py
```

Your browser will open at `http://localhost:8501`

### Step 3: Watch in Real-Time!

The dashboard will auto-refresh every 2 seconds showing:
- Current positions
- Latest trades
- Running P&L
- Performance metrics

**That's it!** Keep both terminals running and watch your bot trade.

---

## 📺 Dashboard Sections

### 🔴/🟢 Status Indicator

Top right corner shows:
- **🟢 ACTIVE** - Forward test is running
- **🔴 STOPPED** - No active session

### 📍 Current Position

When bot has an open position, you'll see:

```
📍 Current Position
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 BTCUSDT LONG
Entry: $47,850.00 | Current: $47,920.00
Stop Loss: $47,650.00 | Take Profit: $48,050.00
Unrealized P&L: +$0.07 (+0.15%)
Duration: 5m | Opened: 14:35:00
```

This updates every 2 seconds with:
- Current price
- Unrealized P&L (not yet closed)
- Time in position
- Distance to SL/TP

### 📈 Session Metrics

5 key metrics at a glance:

| Metric | Description |
|--------|-------------|
| **Total Trades** | How many trades taken |
| **Win Rate** | Percentage of winning trades |
| **Net P&L** | Total profit/loss including fees |
| **Profit Factor** | Gross wins / Gross losses |
| **Balance** | Current virtual balance |

**Deltas** show if metric is good or needs improvement:
- Win Rate: Green if ≥50%, otherwise red
- Profit Factor: Green if ≥1.5, otherwise red

### 📋 Recent Trades

Last 10 closed trades with:
- Symbol and direction
- Entry and exit prices
- P&L with percentage
- Duration
- Exit reason (SL/TP/Manual)

**Color coded:**
- ✅ Green background = Win
- ❌ Red background = Loss

### 💰 Equity Curve

Line chart showing balance over time:
- Starting balance marked with dashed line
- Shaded area under curve
- Hover to see balance at any point
- Shows cumulative P&L

### 📊 Trade Distribution

**Win/Loss Pie Chart:**
- Visual ratio of wins to losses
- Green = wins, Red = losses
- Shows win rate at a glance

**P&L Histogram:**
- Distribution of profit/loss amounts
- Color gradient (red to green)
- Shows consistency
- Identifies if one big win carries results

---

## 💡 Use Cases

### 1. Monitor Forward Test

```bash
# Start forward test for 7 days
python run_forward_test.py

# Open dashboard
streamlit run dashboard_live.py

# Check periodically throughout the week
# See if strategy is working on current market
```

**What to watch:**
- Is bot taking trades?
- Are trades quality setups?
- Win rate consistent?
- Any long losing streaks?

### 2. Watch Paper Trading

```bash
# Start paper trading (testnet orders)
python main.py  # with paper_trading: true

# Open dashboard (works with any trading mode)
streamlit run dashboard_live.py
```

**What to watch:**
- Execution quality
- Slippage on testnet
- Order fill times
- Compare to forward test results

### 3. Monitor Live Trading (Carefully!)

```bash
# Start live trading (REAL MONEY)
python main.py  # with paper_trading: false

# Open dashboard
streamlit run dashboard_live.py
```

**What to watch:**
- Every trade carefully!
- Rapid losses = stop bot immediately
- Check notifications match dashboard
- Monitor balance closely

### 4. Quick Health Check

```bash
# Bot running in background
# Open dashboard for quick check
streamlit run dashboard_live.py

# See at a glance:
# - Is bot alive?
# - Any open positions?
# - Recent performance?
# - Current balance?

# Close dashboard when done (bot keeps running)
```

---

## 🎛️ Dashboard Controls

### Manual Refresh

Click **🔄 Refresh Now** button to force immediate refresh (otherwise auto-refreshes every 2 seconds).

### Stop Dashboard

Just close the browser tab or press `Ctrl+C` in terminal. The bot continues running.

### Restart Dashboard

```bash
streamlit run dashboard_live.py
```

Dashboard picks up where bot left off - shows all trades from current session.

---

## 📊 Understanding the Data

### Open Position P&L

**Unrealized P&L** = What you'd make/lose if position closed now

- Updates every 2 seconds with current price
- Green = currently winning
- Red = currently losing
- Not final until position closes

### Closed Trade P&L

**Realized P&L** = Actual profit/loss after fees

```
Entry: $47,850.00
Exit: $48,050.00
Gross P&L: +$0.20 (quantity * price difference)
Fees: -$0.04 (0.04% on entry + exit)
Net P&L: +$0.16 (final result)
```

### Exit Reasons

| Icon | Reason | What It Means |
|------|--------|---------------|
| 🎯 TP | Take Profit | Target hit - good! |
| 🛑 SL | Stop Loss | Stop hit - manage risk |
| ✋ Manual | Manual Close | You closed it |
| ⏹️ End | Session End | Bot stopped |

### Performance Metrics

**Win Rate**
- Formula: (Wins / Total Trades) × 100
- Target: 50-60%
- Below 45%? Strategy needs work

**Profit Factor**
- Formula: Gross Wins / Gross Losses
- Target: 1.5-2.5
- Below 1.2? Not profitable enough

**ROI %**
- Formula: ((Current - Starting) / Starting) × 100
- Shows overall session performance
- Compounds over time

---

## 🐛 Troubleshooting

### Dashboard Shows "No forward test session found"

**Fix:**
```bash
# Make sure forward test is running
python run_forward_test.py

# Check if results file exists
ls data/forward_test_results.json

# If file exists but dashboard shows nothing, restart dashboard
```

### Dashboard Not Updating

**Possible causes:**

1. **Bot stopped running**
   - Check bot terminal
   - Restart with `python run_forward_test.py`

2. **Browser cache**
   - Hard refresh browser: `Ctrl+Shift+R`
   - Or restart dashboard

3. **Results file corrupted**
   - Stop bot
   - Delete `data/forward_test_results.json`
   - Restart bot

### Dashboard Shows Old Data

**Fix:**
```bash
# Stop bot (Ctrl+C)
# Delete old results
rm data/forward_test_results.json
# Restart bot
python run_forward_test.py
```

### Can't Connect to Dashboard

**Check port:**
```bash
# Default port is 8501
# If busy, Streamlit will use 8502, 8503, etc.

# Manually specify port:
streamlit run dashboard_live.py --server.port 8502
```

---

## 🔥 Pro Tips

### 1. Dual Monitor Setup

**Monitor 1:** Live dashboard (watch trades)
**Monitor 2:** Trading view charts (see price action)

Compare bot entries with your own analysis.

### 2. Screenshot Winners

When bot takes great trades:
1. Screenshot dashboard
2. Note what made setup good
3. Use for manual zone marking

### 3. Multiple Dashboards

```bash
# Terminal 1: Forward test
python run_forward_test.py

# Terminal 2: Live dashboard
streamlit run dashboard_live.py --server.port 8501

# Terminal 3: Static dashboard (for backtests)
streamlit run dashboard.py --server.port 8502
```

Side-by-side comparison!

### 4. Remote Monitoring

```bash
# On VPS:
streamlit run dashboard_live.py --server.address 0.0.0.0 --server.port 8501

# Access from anywhere:
http://your-vps-ip:8501
```

Monitor bot from phone or anywhere with internet.

### 5. Take Notes

Keep a trading journal:
- Good setups bot took
- Bad setups bot took
- Setups bot missed
- Market conditions

Use this to refine parameters.

---

## 📱 Mobile Access

### Access Dashboard on Phone

1. **Find your computer's IP**
   ```bash
   # Mac/Linux
   ifconfig | grep "inet "

   # Windows
   ipconfig
   ```

2. **Start dashboard with network access**
   ```bash
   streamlit run dashboard_live.py --server.address 0.0.0.0
   ```

3. **Open on phone**
   - Go to: `http://YOUR_COMPUTER_IP:8501`
   - Example: `http://192.168.1.100:8501`

4. **Add to home screen**
   - Safari/Chrome: Add to Home Screen
   - Now it's like an app!

---

## 🎓 Learning from the Dashboard

### Spotting Patterns

**Good signs:**
- Consecutive wins in trending market
- Quick target hits
- Small losses, big wins
- Consistent win rate

**Warning signs:**
- Consecutive losses
- Long drawdowns
- Wins taking hours, losses quick
- Win rate dropping

### Adjusting Based on Feedback

**If you see:**
```
Last 10 trades: 3 wins, 7 losses
Win rate: 30%
All losses = stop loss hit quickly
```

**Action:**
- Entry threshold too low
- Entering against trend
- S/R zones not quality
- Raise `entry_threshold` to 80

**Then monitor dashboard to see if improvement!**

---

## 🔗 Related Tools

**Forward Testing:**
```bash
python run_forward_test.py
```
- Simulates trades with live data
- Saves results for dashboard
- No capital risk

**Backtesting:**
```bash
python run_backtest.py --symbol BTCUSDT --days 7
```
- Tests on historical data
- Fast validation
- Use `dashboard.py` (not `dashboard_live.py`) to view

**Paper Trading:**
```bash
python main.py  # with paper_trading: true
```
- Real testnet orders
- Tests execution
- Also works with live dashboard

**Live Trading:**
```bash
python main.py  # with paper_trading: false
```
- Real mainnet orders
- REAL MONEY at risk!
- Critical to monitor with dashboard

---

## ⚡ Quick Reference

```bash
# Start forward test
python run_forward_test.py

# Open live dashboard
streamlit run dashboard_live.py

# Access dashboard
http://localhost:8501

# Stop dashboard
Ctrl+C or close browser

# Refresh dashboard
Click 🔄 Refresh Now
```

**Auto-refresh:** Every 2 seconds
**Results file:** `data/forward_test_results.json`
**Bot keeps running even if dashboard closed:** Yes

---

**Enjoy monitoring your bot in real-time! 📊🚀**
