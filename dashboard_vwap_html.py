"""
VWAP Backtest HTML Dashboard Generator

Creates an interactive HTML dashboard with:
- Performance metrics and trade statistics
- Individual trade analysis with entry/exit details
- Candlestick charts for each trade showing:
  * VWAP line
  * Standard deviation bands (±1σ, ±2σ)
  * Support/Resistance zones
  * Entry/Exit markers
  * TP/SL levels

Usage:
    python dashboard_vwap_html.py <results_file.json>
    python dashboard_vwap_html.py  # Will use latest results file
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import statistics
import asyncio


def load_latest_results() -> tuple[Dict, Path]:
    """Load the most recent backtest results"""
    results_dir = Path('data/vwap_backtest')

    if not results_dir.exists():
        print("[ERROR] No results directory found. Run backtest first.")
        sys.exit(1)

    json_files = list(results_dir.glob('vwap_backtest_*.json'))

    if not json_files:
        print("[ERROR] No backtest results found. Run backtest first.")
        sys.exit(1)

    # Get most recent file
    latest_file = max(json_files, key=lambda p: p.stat().st_mtime)

    print(f"[INFO] Loading results from: {latest_file.name}")

    with open(latest_file, 'r') as f:
        return json.load(f), latest_file


def load_results(filepath: str) -> tuple[Dict, Path]:
    """Load backtest results from file"""
    path = Path(filepath)
    with open(path, 'r') as f:
        return json.load(f), path


def format_timestamp_ist(timestamp_ms: int) -> str:
    """Convert UTC timestamp to IST format"""
    utc = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    ist = utc + timedelta(hours=5, minutes=30)
    return ist.strftime('%Y-%m-%d %H:%M:%S')


def calculate_profit_factor(trades: List[Dict]) -> float:
    """Calculate profit factor (gross wins / gross losses)"""
    total_wins = sum(t['pnl'] for t in trades if t['pnl'] and t['pnl'] > 0)
    total_losses = abs(sum(t['pnl'] for t in trades if t['pnl'] and t['pnl'] < 0))

    if total_losses == 0:
        return float('inf') if total_wins > 0 else 0

    return total_wins / total_losses


async def fetch_trade_data(symbol: str, start_time: int, end_time: int) -> List[List]:
    """Fetch klines for a specific trade period"""
    # Import here to avoid circular dependency issues
    sys.path.insert(0, str(Path(__file__).parent))
    from src.data.binance_client import BinanceClient
    from src.config import Config

    # Create minimal config
    class TradingConfig:
        def __init__(self):
            self.symbols = [symbol]
            self.paper_trading = False

    class MinimalConfig:
        def __init__(self):
            self.trading = TradingConfig()
            self.api_key = ""
            self.api_secret = ""

    client = BinanceClient(MinimalConfig())
    await client.connect()

    # Add buffer before/after trade for context
    buffer_ms = 30 * 60 * 1000  # 30 minutes
    klines = await client.get_klines(
        symbol=symbol,
        interval='1m',
        start_time=start_time - buffer_ms,
        end_time=end_time + buffer_ms
    )

    return klines


def calculate_vwap_bands(klines: List[List], session_start_idx: int = 0) -> Dict:
    """Calculate VWAP and bands from klines"""
    import pandas as pd
    import numpy as np

    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['volume'] = df['volume'].astype(float)

    # Session-based VWAP calculation
    session_df = df.iloc[session_start_idx:]

    typical_price = (session_df['high'] + session_df['low'] + session_df['close']) / 3
    vwap = (typical_price * session_df['volume']).sum() / session_df['volume'].sum()

    squared_diff = (typical_price - vwap) ** 2
    variance = (squared_diff * session_df['volume']).sum() / session_df['volume'].sum()
    std = np.sqrt(variance)

    return {
        'vwap': float(vwap),
        'std': float(std),
        'upper_1std': float(vwap + std),
        'lower_1std': float(vwap - std),
        'upper_2std': float(vwap + 2 * std),
        'lower_2std': float(vwap - 2 * std)
    }


def detect_sr_zones(klines: List[List], lookback: int = 100) -> List[Dict]:
    """Detect S/R zones from klines"""
    import pandas as pd
    import numpy as np

    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)

    zones = []

    # Simple pivot-based zone detection
    for i in range(10, len(df) - 10):
        # Check for resistance (local high)
        if df['high'].iloc[i] == df['high'].iloc[i-5:i+5].max():
            zones.append({
                'level': float(df['high'].iloc[i]),
                'type': 'resistance',
                'touches': 1
            })

        # Check for support (local low)
        if df['low'].iloc[i] == df['low'].iloc[i-5:i+5].min():
            zones.append({
                'level': float(df['low'].iloc[i]),
                'type': 'support',
                'touches': 1
            })

    # Merge nearby zones (within 50 points)
    merged_zones = []
    for zone in zones:
        found = False
        for mz in merged_zones:
            if abs(zone['level'] - mz['level']) < 50 and zone['type'] == mz['type']:
                mz['touches'] += 1
                found = True
                break
        if not found:
            merged_zones.append(zone)

    # Filter zones with at least 2 touches
    return [z for z in merged_zones if z['touches'] >= 2][:10]  # Top 10 zones


def generate_candlestick_chart(trade: Dict, klines: List[List], vwap_bands: Dict, sr_zones: List[Dict]) -> str:
    """Generate Plotly candlestick chart for a trade"""
    import pandas as pd

    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)

    # Build Plotly chart data
    chart_data = {
        'timestamps': df['timestamp'].dt.strftime('%Y-%m-%d %H:%M').tolist(),
        'open': df['open'].tolist(),
        'high': df['high'].tolist(),
        'low': df['low'].tolist(),
        'close': df['close'].tolist(),
        'vwap': vwap_bands['vwap'],
        'upper_1std': vwap_bands['upper_1std'],
        'lower_1std': vwap_bands['lower_1std'],
        'upper_2std': vwap_bands['upper_2std'],
        'lower_2std': vwap_bands['lower_2std'],
        'entry_time': format_timestamp_ist(trade['entry_time']),
        'entry_price': trade['entry_price'],
        'exit_time': format_timestamp_ist(trade['exit_time']) if trade['exit_time'] else None,
        'exit_price': trade['exit_price'],
        'tp': trade['take_profit'],
        'sl': trade['stop_loss'],
        'sr_zones': sr_zones
    }

    return json.dumps(chart_data)


async def generate_html_dashboard(results: Dict, results_file: Path):
    """Generate interactive HTML dashboard"""
    config = results['backtest_config']
    perf = results['performance']
    trades = results['trades']

    profit_factor = calculate_profit_factor(trades)

    # Prepare trade charts data
    print(f"[INFO] Fetching market data for {len(trades)} trades...")
    trades_with_charts = []

    for i, trade in enumerate(trades[:10], 1):  # Limit to first 10 trades for performance
        print(f"  Processing trade {i}/{min(len(trades), 10)}...")

        try:
            klines = await fetch_trade_data(
                config['symbol'],
                trade['entry_time'],
                trade['exit_time'] if trade['exit_time'] else trade['entry_time'] + 3600000
            )

            vwap_bands = calculate_vwap_bands(klines)
            sr_zones = detect_sr_zones(klines)
            chart_data = generate_candlestick_chart(trade, klines, vwap_bands, sr_zones)

            trades_with_charts.append({
                **trade,
                'chart_data': chart_data
            })
        except Exception as e:
            print(f"  Warning: Could not fetch data for trade {i}: {e}")
            trades_with_charts.append({
                **trade,
                'chart_data': None
            })

    # Generate HTML
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VWAP Backtest Dashboard - {config['symbol']}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0e27;
            color: #e0e0e0;
            padding: 20px;
        }}

        .container {{
            max-width: 1600px;
            margin: 0 auto;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            text-align: center;
        }}

        h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}

        .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .metric-card {{
            background: #1a1f3a;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}

        .metric-label {{
            color: #8b8b8b;
            font-size: 0.9em;
            margin-bottom: 8px;
        }}

        .metric-value {{
            font-size: 1.8em;
            font-weight: bold;
        }}

        .metric-value.positive {{
            color: #4ade80;
        }}

        .metric-value.negative {{
            color: #f87171;
        }}

        .metric-value.neutral {{
            color: #60a5fa;
        }}

        .trade-section {{
            background: #1a1f3a;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 25px;
        }}

        .trade-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #2a2f4a;
        }}

        .trade-title {{
            font-size: 1.5em;
            font-weight: bold;
        }}

        .trade-pnl {{
            font-size: 1.3em;
            font-weight: bold;
            padding: 8px 16px;
            border-radius: 6px;
        }}

        .trade-pnl.win {{
            background: #16a34a;
            color: white;
        }}

        .trade-pnl.loss {{
            background: #dc2626;
            color: white;
        }}

        .trade-details {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}

        .detail-item {{
            background: #0f1729;
            padding: 12px;
            border-radius: 6px;
        }}

        .detail-label {{
            color: #8b8b8b;
            font-size: 0.85em;
            margin-bottom: 4px;
        }}

        .detail-value {{
            font-size: 1.1em;
            font-weight: 600;
        }}

        .chart-container {{
            background: #0f1729;
            border-radius: 8px;
            padding: 15px;
            min-height: 500px;
        }}

        .no-chart {{
            text-align: center;
            padding: 60px;
            color: #8b8b8b;
            font-size: 1.1em;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }}

        .badge.long {{
            background: #16a34a;
            color: white;
        }}

        .badge.short {{
            background: #dc2626;
            color: white;
        }}

        .timestamp {{
            color: #60a5fa;
            font-size: 0.95em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 VWAP Backtest Dashboard</h1>
            <div class="subtitle">{config['symbol']} | {config['timeframe']} | Leverage: {config['leverage']}x</div>
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Initial Margin</div>
                <div class="metric-value neutral">${config['initial_capital']:,.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Final Capital</div>
                <div class="metric-value {'positive' if config['final_capital'] >= config['initial_capital'] else 'negative'}">${config['final_capital']:,.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Return</div>
                <div class="metric-value {'positive' if perf['return_pct'] >= 0 else 'negative'}">{perf['return_pct']:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Net P&L</div>
                <div class="metric-value {'positive' if perf['net_pnl'] >= 0 else 'negative'}">${perf['net_pnl']:,.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value neutral">{perf['total_trades']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value {'positive' if perf['win_rate'] >= 50 else 'negative'}">{perf['win_rate']:.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Profit Factor</div>
                <div class="metric-value {'positive' if profit_factor >= 1.5 else 'neutral' if profit_factor >= 1 else 'negative'}">{profit_factor:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg Win</div>
                <div class="metric-value positive">${perf['avg_win']:,.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg Loss</div>
                <div class="metric-value negative">${perf['avg_loss']:,.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Fees</div>
                <div class="metric-value neutral">${perf['total_fees']:,.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg Duration</div>
                <div class="metric-value neutral">{perf['avg_trade_duration_minutes']:.1f}m</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Max Position</div>
                <div class="metric-value neutral">${config['max_position_size']:,.0f}</div>
            </div>
        </div>
"""

    # Add individual trade sections
    for i, trade in enumerate(trades_with_charts, 1):
        is_win = trade['pnl'] and trade['pnl'] > 0

        html += f"""
        <div class="trade-section">
            <div class="trade-header">
                <div>
                    <span class="trade-title">Trade #{i}</span>
                    <span class="badge {trade['direction'].lower()}">{trade['direction']}</span>
                </div>
                <div class="trade-pnl {'win' if is_win else 'loss'}">
                    ${trade['pnl']:,.2f} ({trade['pnl_pct']:.2f}%)
                </div>
            </div>

            <div class="trade-details">
                <div class="detail-item">
                    <div class="detail-label">Entry Time (IST)</div>
                    <div class="detail-value timestamp">{format_timestamp_ist(trade['entry_time'])}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Entry Price</div>
                    <div class="detail-value">${trade['entry_price']:,.2f}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Exit Price</div>
                    <div class="detail-value">${trade['exit_price']:,.2f}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Exit Reason</div>
                    <div class="detail-value">{trade['exit_reason']}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Duration</div>
                    <div class="detail-value">{trade['duration_minutes']:.1f} min</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Take Profit</div>
                    <div class="detail-value">${trade['take_profit']:,.2f}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Stop Loss</div>
                    <div class="detail-value">${trade['stop_loss']:,.2f}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Exit Time (IST)</div>
                    <div class="detail-value timestamp">{format_timestamp_ist(trade['exit_time']) if trade['exit_time'] else 'N/A'}</div>
                </div>
            </div>

            <div class="chart-container" id="chart-{i}">
"""

        if trade['chart_data']:
            html += f"""
                <script>
                (function() {{
                    const data = {trade['chart_data']};

                    const candlestick = {{
                        x: data.timestamps,
                        open: data.open,
                        high: data.high,
                        low: data.low,
                        close: data.close,
                        type: 'candlestick',
                        name: 'Price',
                        increasing: {{line: {{color: '#4ade80'}}}},
                        decreasing: {{line: {{color: '#f87171'}}}}
                    }};

                    const vwap = {{
                        x: data.timestamps,
                        y: Array(data.timestamps.length).fill(data.vwap),
                        type: 'scatter',
                        mode: 'lines',
                        name: 'VWAP',
                        line: {{color: '#60a5fa', width: 2}}
                    }};

                    const upper1 = {{
                        x: data.timestamps,
                        y: Array(data.timestamps.length).fill(data.upper_1std),
                        type: 'scatter',
                        mode: 'lines',
                        name: '+1σ',
                        line: {{color: '#a78bfa', width: 1, dash: 'dash'}}
                    }};

                    const lower1 = {{
                        x: data.timestamps,
                        y: Array(data.timestamps.length).fill(data.lower_1std),
                        type: 'scatter',
                        mode: 'lines',
                        name: '-1σ',
                        line: {{color: '#a78bfa', width: 1, dash: 'dash'}}
                    }};

                    const upper2 = {{
                        x: data.timestamps,
                        y: Array(data.timestamps.length).fill(data.upper_2std),
                        type: 'scatter',
                        mode: 'lines',
                        name: '+2σ',
                        line: {{color: '#c084fc', width: 1, dash: 'dot'}}
                    }};

                    const lower2 = {{
                        x: data.timestamps,
                        y: Array(data.timestamps.length).fill(data.lower_2std),
                        type: 'scatter',
                        mode: 'lines',
                        name: '-2σ',
                        line: {{color: '#c084fc', width: 1, dash: 'dot'}}
                    }};

                    const entry = {{
                        x: [data.entry_time],
                        y: [data.entry_price],
                        type: 'scatter',
                        mode: 'markers',
                        name: 'Entry',
                        marker: {{size: 12, color: '#fbbf24', symbol: 'triangle-up'}}
                    }};

                    const exit = data.exit_time ? {{
                        x: [data.exit_time],
                        y: [data.exit_price],
                        type: 'scatter',
                        mode: 'markers',
                        name: 'Exit',
                        marker: {{size: 12, color: '#f97316', symbol: 'triangle-down'}}
                    }} : null;

                    const tp = {{
                        x: data.timestamps,
                        y: Array(data.timestamps.length).fill(data.tp),
                        type: 'scatter',
                        mode: 'lines',
                        name: 'TP',
                        line: {{color: '#16a34a', width: 1, dash: 'dot'}}
                    }};

                    const sl = {{
                        x: data.timestamps,
                        y: Array(data.timestamps.length).fill(data.sl),
                        type: 'scatter',
                        mode: 'lines',
                        name: 'SL',
                        line: {{color: '#dc2626', width: 1, dash: 'dot'}}
                    }};

                    const traces = [candlestick, vwap, upper1, lower1, upper2, lower2, entry, tp, sl];
                    if (exit) traces.push(exit);

                    // Add SR zones as shapes
                    const shapes = data.sr_zones.map(zone => ({{
                        type: 'line',
                        x0: data.timestamps[0],
                        x1: data.timestamps[data.timestamps.length - 1],
                        y0: zone.level,
                        y1: zone.level,
                        line: {{
                            color: zone.type === 'resistance' ? '#ef4444' : '#22c55e',
                            width: 1,
                            dash: 'dashdot'
                        }}
                    }})));

                    const layout = {{
                        title: 'Trade Chart - VWAP, Bands & SR Zones',
                        plot_bgcolor: '#0f1729',
                        paper_bgcolor: '#0f1729',
                        font: {{color: '#e0e0e0'}},
                        xaxis: {{
                            gridcolor: '#2a2f4a',
                            title: 'Time'
                        }},
                        yaxis: {{
                            gridcolor: '#2a2f4a',
                            title: 'Price (USDT)'
                        }},
                        shapes: shapes,
                        showlegend: true,
                        legend: {{
                            bgcolor: '#1a1f3a',
                            bordercolor: '#2a2f4a',
                            borderwidth: 1
                        }},
                        hovermode: 'x unified'
                    }};

                    const config = {{responsive: true}};

                    Plotly.newPlot('chart-{i}', traces, layout, config);
                }})();
                </script>
"""
        else:
            html += """
                <div class="no-chart">⚠️ Chart data not available for this trade</div>
"""

        html += """
            </div>
        </div>
"""

    html += """
    </div>
</body>
</html>
"""

    # Save HTML file
    output_file = results_file.parent / f"dashboard_{results_file.stem}.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n[SUCCESS] HTML dashboard saved to: {output_file}")
    print(f"[INFO] Open it in your browser to view the interactive charts!")

    return output_file


async def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        # Load specified file
        filepath = sys.argv[1]
        if not Path(filepath).exists():
            print(f"[ERROR] File not found: {filepath}")
            sys.exit(1)
        results, results_file = load_results(filepath)
    else:
        # Load latest results
        results, results_file = load_latest_results()

    await generate_html_dashboard(results, results_file)


if __name__ == '__main__':
    asyncio.run(main())
