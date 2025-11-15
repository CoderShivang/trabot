# VWAP Strategy Backtest Guide

## Overview

This is a **VWAP + S/R** trading strategy backtest engine for 1-minute scalping on Binance.

### Key Features

✅ **Session-based VWAP** with ±1σ and ±2σ bands
✅ **S/R Zone Detection** from consolidation periods (matches manual trading style)
✅ **All Limit Orders** - Entry, TP, and SL (lowest fees: 0.02% maker)
✅ **Live Binance Mainnet Data** - No synthetic testnet data
✅ **Detailed Trade Logging** - Full analysis and statistics
✅ **Realistic Order Fill Simulation** - Limit orders with timeouts

---

## Strategy Logic

### Entry Types

#### 1. Mean Reversion LONG
- **Condition**: Price near **-1σ** + at **support zone**
- **Entry**: Limit order at support level
- **Bias**: Bullish mean reversion or neutral

#### 2. Mean Reversion SHORT
- **Condition**: Price near **+1σ** + at **resistance zone**
- **Entry**: Limit order at resistance level
- **Bias**: Bearish mean reversion or neutral

#### 3. Trend Continuation LONG
- **Condition**: Price > all VWAP bands (strong uptrend) + pullback to **+1σ**
- **Entry**: Limit order on pullback
- **Bias**: Strong bullish

#### 4. Trend Continuation SHORT
- **Condition**: Price < all VWAP bands (strong downtrend) + pullback to **-1σ**
- **Entry**: Limit order on pullback
- **Bias**: Strong bearish

### S/R Zone Detection

Zones are detected from **consolidation periods**:
- Price ranges with <1.5% movement
- Minimum 20 bars consolidation
- Multiple touches at similar levels
- Avoids choppy/trending areas

---

## Quick Start

### 1. Basic Backtest (7 days)

```bash
python run_vwap_backtest.py --symbol BTCUSDT --days 7
```

### 2. Custom Date Range

```bash
python run_vwap_backtest.py --symbol BTCUSDT --start 2025-01-01 --end 2025-01-07
```

### 3. Custom Parameters

```bash
python run_vwap_backtest.py \
  --symbol ETHUSDT \
  --days 14 \
  --capital 20000 \
  --risk 0.015 \
  --target 250 \
  --stop 180 \
  --min-zone-strength 70
```

---

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--symbol` | Trading pair | BTCUSDT |
| `--timeframe` | Candle timeframe | 1m |
| `--days` | Days to backtest | 7 |
| `--start` | Start date (YYYY-MM-DD) | - |
| `--end` | End date (YYYY-MM-DD) | - |
| `--capital` | Initial capital (USDT) | 10000 |
| `--risk` | Risk per trade (decimal) | 0.02 (2%) |
| `--target` | Take profit ($) | 200 |
| `--stop` | Stop loss ($) | 150 |
| `--band-proximity` | Distance to VWAP band ($) | 75 |
| `--zone-proximity` | Distance to S/R zone ($) | 150 |
| `--min-zone-strength` | Min S/R quality (0-100) | 60 |

---

## Output

### Console Output

The backtest prints:
- Data fetching progress
- Trade signals with reasons
- Position open/close events
- Final statistics

Example:
```
[SIGNAL] LONG mean_reversion
  Entry (Limit): $95,420.00
  Stop Loss: $95,270.00
  Take Profit: $95,620.00
  Confidence: 78%
  Reason: LONG Mean Reversion: -1σ ($95,450) + Support $95,400 (str:75)

[POSITION] Opened LONG at $95,420.00 (qty: 0.2500)
[CLOSE] LONG | TP | P&L: $48.50 (1.28%) | Duration: 12.5m
```

### JSON Results

Results are saved to `data/vwap_backtest/vwap_backtest_{symbol}_{timestamp}.json`:

```json
{
  "backtest_config": {
    "symbol": "BTCUSDT",
    "timeframe": "1m",
    "initial_capital": 10000,
    "final_capital": 10250.50,
    "risk_per_trade": 0.02,
    "maker_fee": 0.0002
  },
  "performance": {
    "total_trades": 15,
    "winning_trades": 9,
    "losing_trades": 6,
    "win_rate": 60.0,
    "total_pnl": 275.50,
    "total_fees": 25.00,
    "net_pnl": 250.50,
    "return_pct": 2.51,
    "avg_win": 45.50,
    "avg_loss": -28.30,
    "largest_win": 92.00,
    "largest_loss": -48.00,
    "avg_trade_duration_minutes": 18.5
  },
  "order_stats": {
    "entry_fills": 15,
    "entry_timeouts": 3,
    "tp_fills": 9,
    "sl_fills": 6
  },
  "trades": [...]
}
```

---

## Understanding the Results

### Key Metrics

- **Win Rate**: Percentage of profitable trades (target: >55%)
- **Net P&L**: Total profit after fees
- **Return %**: (Final Capital - Initial) / Initial × 100
- **Avg Win/Loss**: Average profit/loss per winning/losing trade
- **Fill Stats**: How many orders filled vs timed out

### What to Look For

✅ **Good Performance**:
- Win rate 55-70%
- Positive net P&L
- More TP fills than SL fills
- Low entry timeout rate

❌ **Poor Performance**:
- Win rate <50%
- Negative net P&L
- High entry timeout rate (signals not getting filled)
- Large drawdowns

---

## Strategy Configuration

### For Scalping (Current)

```python
{
    'target_points': 200,      # Quick $200 profits
    'stop_points': 150,        # Tight $150 stops
    'band_proximity': 75,      # Close to VWAP bands
    'zone_proximity': 150,     # Close to S/R zones
    'min_zone_strength': 60    # Medium-strong zones
}
```

### For Swing Trading

```python
{
    'target_points': 500,      # Larger profits
    'stop_points': 350,        # Wider stops
    'band_proximity': 150,     # More lenient entry
    'zone_proximity': 250,     # More lenient S/R
    'min_zone_strength': 70    # Stronger zones only
}
```

---

## Order Types (All Limit Orders)

### Entry Order
- **Type**: Limit order
- **Timeout**: 3 minutes
- **Fill Logic**: Fills if price touches limit price
- **Benefit**: 0.02% maker fee (vs 0.04% taker)

### Take Profit
- **Type**: Limit order
- **No Timeout**: Stays active until filled
- **Fill Logic**: Sells/Buys at TP price when hit

### Stop Loss
- **Type**: Limit order (simulated stop-limit)
- **No Timeout**: Stays active until filled
- **Fill Logic**: Triggers when price hits SL

---

## Optimization Tips

### 1. Tune S/R Detection

Adjust consolidation parameters in `src/strategy/vwap_strategy.py`:
```python
SimpleConsolidationDetector(
    min_bars=20,           # Increase for longer consolidations
    max_range_pct=0.015    # Decrease for tighter consolidations
)
```

### 2. Adjust Risk/Reward

Balance your TP/SL ratio:
- **Conservative**: target=200, stop=150 (1.33:1)
- **Aggressive**: target=300, stop=150 (2:1)

### 3. Filter Trade Quality

Increase `min_zone_strength` to only trade the best S/R zones:
- **60**: Medium zones (more trades)
- **70**: Strong zones (fewer, better trades)
- **80**: Only excellent zones (very selective)

### 4. Adjust Entry Proximity

- **Tight** (band=50, zone=100): Fewer but higher-quality entries
- **Loose** (band=100, zone=200): More entries but lower quality

---

## Troubleshooting

### Problem: No trades taken

**Causes**:
- `min_zone_strength` too high (no zones meet criteria)
- `band_proximity` / `zone_proximity` too tight
- Insufficient data (use more days)

**Solution**: Lower thresholds or check zone detection

### Problem: High entry timeout rate

**Causes**:
- Limit prices too aggressive (not touching price)
- Market moving too fast

**Solution**: Adjust entry logic or increase timeout

### Problem: All trades hit stop loss

**Causes**:
- Stop loss too tight
- Poor entry timing
- Wrong market conditions

**Solution**: Widen stops, improve entry filters

---

## File Structure

```
trabot/
├── run_vwap_backtest.py              # Runner script
├── src/
│   ├── strategy/
│   │   └── vwap_strategy.py          # VWAP + S/R strategy
│   └── backtesting/
│       └── vwap_backtest_engine.py   # Backtest engine
└── data/
    └── vwap_backtest/                # Results stored here
        └── vwap_backtest_BTCUSDT_*.json
```

---

## Next Steps

1. **Run Initial Backtest**: Test with default parameters
2. **Analyze Results**: Check win rate, P&L, and trade quality
3. **Tune Parameters**: Optimize based on results
4. **Test Different Timeframes**: Try 3m, 5m, 15m
5. **Forward Test**: Paper trade before going live

---

## Notes

- Data fetched from **Binance mainnet** (not testnet)
- All orders are **limit orders** for lowest fees (0.02%)
- Backtest simulates realistic fills (no perfect execution)
- Strategy works best in **range-bound markets** with clear S/R

---

## Questions?

Check the code comments in:
- `src/strategy/vwap_strategy.py` - Strategy logic
- `src/backtesting/vwap_backtest_engine.py` - Backtest mechanics
