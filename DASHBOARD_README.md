# VWAP + S/R Strategy Dashboard

Interactive web dashboard for analyzing backtest results and ML performance.

![Dashboard Preview](https://img.shields.io/badge/Status-Active-green) ![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)

## Features

### 📊 Core Analytics
- **Header Metrics**: Win rate, total trades, net P&L, ML approval rate
- **Day of Week Analysis**: Identify which days perform best
- **Equity Curve**: Track account balance over time
- **Drawdown Chart**: Visualize maximum drawdown periods
- **Daily P&L Table**: Clickable rows to filter trades by day

### 🤖 ML Performance
- **ML Confidence Scores**: Average confidence for winning vs losing trades
- **Success Probability**: ML model's predicted success rate
- **Confidence Distribution**: Histogram showing ML confidence patterns
- **ML Approval Rate**: Percentage of trades approved by ML filter

### 🔍 Trade Analysis
- **Trade Filtering**: Filter by outcome (win/loss) and direction (LONG/SHORT)
- **Trade List**: Detailed trade table with entry/exit prices
- **VWAP Features**: Distance from VWAP, band position, zone strength
- **Zone Metadata**: Bounces, touches, liquidity grabs

### 📈 Charts (Optional)
- **Candlestick Charts**: View price action around each trade entry
- **VWAP Bands**: See VWAP lines and standard deviation bands
- **Entry/Exit Markers**: Visual indicators on the chart

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements_dashboard.txt
```

This installs:
- `dash` - Web framework
- `dash-bootstrap-components` - UI components
- `pandas` & `numpy` - Data processing
- `plotly` - Interactive charts
- `python-binance` - For fetching candle data
- `scikit-learn` - ML support

### 2. Prepare Data

The dashboard loads data from:
- `outputs/latest_backtest_results.json` (preferred)
- `outputs/trade_history.json` (fallback)
- `data/training_data.csv` (ML training data)

**Option A: Run ML training data collector (recommended)**
```bash
python ml_training_data_collector.py --days 7 --output data/training_data.csv
```

**Option B: Run backtest**
```bash
python run_backtest.py --days 7
```

### 3. Launch Dashboard

```bash
python dashboard_app.py
```

The dashboard will start at: **http://localhost:8050**

## Usage

### Analyzing Performance

1. **Overview**: Check header metrics for quick summary
2. **Day Analysis**: Identify best/worst days of the week
3. **Equity Curve**: See overall profitability trend
4. **Daily Table**: Click rows to filter trades by date

### ML Analysis

1. **ML Performance**: Review confidence scores and success probability
2. **Confidence Distribution**: Check if ML is well-calibrated
3. **Approval Rate**: See what % of trades passed ML filter

### Trade Details

1. **Filter Trades**: Use dropdowns to filter by outcome/direction
2. **Trade List**: Click a row to see detailed information
3. **Trade Card**: View VWAP features, zone metadata, ML prediction

### Candlestick Charts (Optional)

If Binance API is accessible:
- Click any trade in the trade list
- Chart will show 50 candles before entry, 10 after
- Entry/exit points marked with arrows

If offline:
- Charts won't load (requires internet)
- All other dashboard features work normally

## Data Format

### Required Columns

The dashboard expects trades with these columns:

**Basic Info:**
- `timestamp` or `entry_time` - Trade entry time
- `entry_price` - Entry price
- `exit_price` - Exit price
- `pnl_pct` or `pnl_percent` - P&L as decimal (0.05 = 5%)
- `signal_type` or `direction` - LONG or SHORT

**VWAP Features (optional):**
- `vwap_distance` - Distance from VWAP as decimal
- `vwap_band_position` - Position in VWAP bands (0-1)
- `zone_strength` - S/R zone strength score
- `zone_bounces` - Number of bounces
- `zone_touches` - Number of touches
- `zone_liquidity_grabs` - Number of liquidity grabs

**ML Features (optional):**
- `ml_confidence` - Model confidence (0-1)
- `success_probability` - Predicted success rate (0-1)
- `ml_approved` - Whether ML approved the trade (boolean)

### Example Trade JSON

```json
{
  "timestamp": "2025-01-10 14:30:00",
  "entry_price": 45000.50,
  "exit_price": 45100.25,
  "pnl_pct": 0.0022,
  "signal_type": "LONG",
  "vwap_distance": -0.0015,
  "vwap_band_position": 0.25,
  "zone_strength": 8.5,
  "zone_bounces": 3,
  "zone_touches": 5,
  "zone_liquidity_grabs": 1,
  "ml_confidence": 0.72,
  "success_probability": 0.65,
  "ml_approved": true
}
```

## Troubleshooting

### "No Backtest Data Found"

**Problem**: Dashboard can't find data files

**Solution**:
```bash
# Option 1: Collect ML training data
python ml_training_data_collector.py --days 7 --output data/training_data.csv

# Option 2: Check if files exist
ls -lh outputs/
ls -lh data/
```

### "ML Data Not Available"

**Problem**: No ML metrics in trade data

**Solution**: This is normal if you haven't integrated ML yet. Follow these steps:
1. Collect training data: `python ml_training_data_collector.py --days 30`
2. Train model: `python train_ml_model.py --input data.csv --output model.pkl`
3. Integrate `MLFilter` into your strategy
4. Run backtest with ML enabled

### Port Already in Use

**Problem**: Port 8050 is already taken

**Solution**:
```bash
# Change port in dashboard_app.py (last line):
app.run(debug=True, host='127.0.0.1', port=8051)  # Use different port
```

### Charts Not Loading

**Problem**: Candlestick charts show error

**Solution**: Charts require:
1. Internet connection (to fetch from Binance)
2. Correct symbol in `fetch_candles_for_trade()` function
3. Valid timestamp in trade data

If offline, all other dashboard features work fine.

## Customization

### Change Theme

Edit the Bootstrap theme in `dashboard_app.py`:

```python
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])  # Dark theme
# Options: FLATLY, DARKLY, COSMO, JOURNAL, LITERA, LUMEN, LUX, MATERIA, MINTY, PULSE, SANDSTONE, SIMPLEX, SKETCHY, SLATE, SOLAR, SPACELAB, SUPERHERO, UNITED, YETI
```

### Add Custom Metrics

Add new metrics in `create_header_metrics()`:

```python
dbc.Col([
    html.Div([
        html.Span("Your Metric: ", style={'fontSize': '18px'}),
        html.Span(f"{value}", className="text-info", style={'fontSize': '18px', 'fontWeight': 'bold'})
    ])
], width=3, className="text-center")
```

### Change Chart Interval

Modify `fetch_candles_for_trade()` call:

```python
candles_df = fetch_candles_for_trade(
    symbol='BTCUSDT',
    timestamp=trade.get('timestamp'),
    bars_before=100,   # More history
    bars_after=20,     # More future
    interval='5m'      # 5-minute candles
)
```

## Performance Tips

### Large Datasets

If you have 1000+ trades:

1. **Limit rows**: Add pagination to trade table
```python
page_size=20  # In create_trade_table()
```

2. **Reduce candle history**: Fetch fewer candles
```python
bars_before=30  # Instead of 50
```

3. **Disable auto-refresh**: Remove `dcc.Interval` if added

### Slow Loading

If dashboard loads slowly:

1. **Preprocess data**: Cache computed metrics
2. **Use smaller date range**: Filter to last 7 days
3. **Disable charts**: Comment out candlestick chart code

## Architecture

```
dashboard_app.py
├── Data Loading
│   └── load_backtest_data() - Loads JSON/CSV
├── Data Processing
│   ├── prepare_daily_data() - Aggregates by day
│   └── fetch_candles_for_trade() - Gets OHLCV from Binance
├── Visualization Components
│   ├── create_header_metrics() - Top metrics
│   ├── create_day_of_week_charts() - Day analysis
│   ├── create_equity_drawdown_chart() - Equity curve
│   ├── create_daily_pnl_table() - Daily table
│   ├── create_trade_table() - Trade list
│   └── create_ml_analysis() - ML metrics
├── Layout
│   └── app.layout - Dash components
└── Callbacks
    ├── load_initial_data() - Initial data load
    ├── handle_date_selection() - Date filter
    ├── update_trade_table() - Filter trades
    └── show_trade_details() - Trade details card
```

## Next Steps

1. ✅ Install dependencies
2. ✅ Collect training data or run backtest
3. ✅ Launch dashboard
4. 🔲 Analyze performance by day of week
5. 🔲 Review ML confidence scores
6. 🔲 Identify losing patterns
7. 🔲 Refine strategy based on insights
8. 🔲 Retrain ML model with fresh data
9. 🔲 Compare before/after performance

## Screenshots

### Dashboard Overview
- Header with key metrics
- Day of week analysis (stacked bars)
- Win rate by day (bar chart)

### Equity & Drawdown
- Equity curve with max profit marker
- Drawdown chart with max drawdown marker
- Visual representation of account growth

### Trade Analysis
- Filterable trade list
- Detailed trade information
- VWAP and zone features
- ML prediction scores

## Support

For issues or questions:
1. Check this README
2. Review `ML_SYSTEM_README.md` for ML integration
3. Verify data format matches expected structure
4. Check console for error messages

## Updates

**v1.0** - Initial release
- Core analytics (equity, drawdown, day analysis)
- ML performance metrics
- Trade filtering and details
- Candlestick charts (optional)
