# VWAP Strategy Improvements

This document describes the two major improvements added to the VWAP backtest strategy.

---

## 1. Range-Bound Market Detection

### Overview
The strategy now automatically detects whether the market is in a **ranging** (consolidation) or **trending** state and adjusts its behavior accordingly.

### How It Works

The `_detect_market_regime()` method analyzes the last 60 bars (1 hour) to determine market state using three factors:

1. **Price Range**: Distance between high and low as percentage of price
2. **Trend Slope**: Linear regression slope of closing prices
3. **Candle Volatility**: Average candle size (high-low range)

### Detection Criteria

**Ranging Market** (like 13 Nov 0:45-5:45):
- Tight range: < 2.5% total range
- Minimal slope: < 1.5% directional movement
- Small candles: < 0.8% average candle size

**Trending Market**:
- Wider range: > 3% total range
- Significant slope: > 2% directional movement

### Strategy Adjustments

| Market Regime | Behavior |
|--------------|----------|
| **Ranging** | Only use **mean reversion** setups at S/R zones. Skip trend continuation signals. |
| **Trending Up** | Use **full strategy**: mean reversion + trend continuation setups |
| **Trending Down** | Use **full strategy**: mean reversion + trend continuation setups |

### Logs Example

```
[REGIME] Market is ranging
[REGIME] Market switched from ranging to trending_up
```

### Benefits

- **Better risk management**: Avoids chasing breakouts in choppy ranges
- **Higher quality setups**: Focuses on S/R bounces during consolidation
- **Fewer false signals**: Re-enables trend strategies only when market shows clear direction

---

## 2. Interactive Dashboard with Trade Filtering

### Overview
The new interactive dashboard allows you to **filter trades** and **inspect individual trades** with only their relevant decision-making context, eliminating the clutter of showing all trades simultaneously.

### Features

#### A. Trade Filtering
Filter the trade list by:
- **Outcome**: All / Wins Only / Losses Only
- **Direction**: All / LONG Only / SHORT Only
- **Signal Type**: All / Mean Reversion / Trend Continuation

#### B. Clickable Trade List
- Shows all trades matching your filter criteria
- Displays: Entry/Exit prices, P&L, P&L%, Direction, Type, Reason
- Color-coded rows: Green for wins, Red for losses
- Click any trade to load its specific chart

#### C. Individual Trade Charts
When you click a trade, the chart shows:
- **Time window**: ±30 minutes around the trade
- **Only the S/R zone** that contributed to that trade's decision
- **VWAP bands** at that specific time
- **Entry/Exit markers** for that trade only
- **Trade details panel** with duration, reason, P&L

#### D. No Clutter
Unlike the static dashboard that shows all trades at once, this shows one trade at a time with its specific context.

---

## How to Use

### Step 1: Install New Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `dash` - Interactive web framework
- `pyarrow` - Parquet file support for data storage
- `tqdm` - Progress bar for backtests

### Step 2: Run a Backtest

```bash
python run_vwap_backtest.py --symbol BTCUSDT --days 7
```

This now generates:
1. **Static HTML dashboard** - saved to `data/vwap_backtest/dashboard.html`
2. **OHLCV data** - saved to `data/vwap_backtest/ohlcv_data.parquet`
3. **Backtest results** - saved to `data/vwap_backtest/backtest_YYYYMMDD_HHMMSS.json`

### Step 3: Launch Interactive Dashboard

```bash
python launch_interactive_dashboard.py
```

This will:
1. Load the most recent backtest results
2. Launch a web server on `http://127.0.0.1:8050`
3. Automatically open your browser

### Step 4: Filter and Inspect Trades

1. **Use the dropdowns** to filter trades (e.g., "Losses Only" + "LONG Only")
2. **Click any trade** in the table to see its chart
3. **Review the S/R zone and VWAP bands** that triggered that specific trade
4. **Check the trade details panel** for full context

---

## Example Workflow

### Analyzing Losing Trades

1. Set **Outcome** filter to "Losses Only"
2. Click the first losing trade
3. Review the chart to see:
   - Was the S/R zone too weak?
   - Was the VWAP distance too far?
   - Did price break through the zone immediately?
4. Use insights to adjust strategy parameters

### Comparing LONG vs SHORT Performance

1. Filter by "LONG Only", note win rate
2. Filter by "SHORT Only", note win rate
3. Compare if one direction performs significantly better
4. Consider if market regime affects directional bias

### Reviewing Mean Reversion vs Trend Continuation

1. Filter by "Mean Reversion" only
2. Check if these trades cluster during ranging periods
3. Filter by "Trend Continuation" only
4. Check if these trades cluster during trending periods

---

## Technical Details

### Files Modified

1. **src/strategy/vwap_strategy.py**
   - Added `_detect_market_regime()` method
   - Modified `analyze()` to check regime before generating signals
   - Skip trend continuation in ranging markets

2. **src/backtesting/vwap_backtest_engine.py**
   - Import `InteractiveDashboard`
   - Save OHLCV data as parquet after backtest
   - Display instructions for launching interactive dashboard

3. **src/visualization/interactive_dashboard.py** (NEW)
   - Complete Dash web application
   - Filter controls and trade table
   - Dynamic chart generation for selected trades

4. **launch_interactive_dashboard.py** (NEW)
   - Convenience script to launch dashboard
   - Automatically finds most recent backtest
   - Opens browser to dashboard

### Data Flow

```
Backtest Run
    |
    ├─> backtest_YYYYMMDD_HHMMSS.json  (trade data)
    ├─> ohlcv_data.parquet              (price data)
    └─> dashboard.html                   (static viz)

Interactive Dashboard
    |
    ├─> Loads backtest JSON
    ├─> Loads OHLCV parquet
    └─> Generates filtered charts on-demand
```

---

## Configuration

### Adjusting Range Detection Sensitivity

Edit `src/strategy/vwap_strategy.py`, method `_detect_market_regime()`:

```python
# More sensitive (detect ranges more often)
if range_pct < 0.03 and abs(slope_pct) < 0.02:  # Increased thresholds
    return 'ranging'

# Less sensitive (detect ranges less often)
if range_pct < 0.02 and abs(slope_pct) < 0.01:  # Decreased thresholds
    return 'ranging'
```

### Dashboard Port

Default port is 8050. To change:

```python
# In launch_interactive_dashboard.py
dashboard.run(port=8888, debug=False, open_browser=True)  # Use port 8888
```

---

## Troubleshooting

### Dashboard doesn't open

1. Check if port 8050 is already in use:
   ```bash
   netstat -an | grep 8050
   ```

2. Manually open browser to: http://127.0.0.1:8050

### No trades appear in filter

- Check if the backtest had any trades
- Try "All Trades" filter first to see everything
- Review backtest logs for regime changes

### Chart shows empty data

- Ensure OHLCV data was saved during backtest
- Check `data/vwap_backtest/ohlcv_data.parquet` exists
- Re-run backtest if data is missing

---

## Performance Notes

### Static Dashboard
- Generated once, loads instantly
- Shows all trades at once
- Good for: Quick overview, presentation

### Interactive Dashboard
- Generates charts on-demand
- Filters trades dynamically
- Good for: Detailed analysis, debugging specific trades

**Recommendation**: Use static dashboard for quick reviews, interactive dashboard for deep analysis.

---

## Next Steps

### Potential Enhancements

1. **Export filtered trades** to CSV
2. **Add date range filter** for time-based analysis
3. **Show HTF confluence** indicators on individual charts
4. **Regime timeline** visualization showing when market was ranging vs trending
5. **Parameter optimization** based on filtered trade performance

---

## Questions?

If you encounter issues or have suggestions for improvements, please create an issue with:
1. The command you ran
2. The error message or unexpected behavior
3. Backtest results file (if applicable)
