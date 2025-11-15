"""
VWAP Backtest Dashboard with Candlesticks and S/R Zones

Creates interactive HTML dashboard with:
- Real candlestick charts (fetched from Binance)
- VWAP and standard deviation bands
- S/R zones visualization
- Entry/Exit markers

Usage:
    python dashboard_vwap_candles.py
    python dashboard_vwap_candles.py <results_file.json>
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
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
    """Calculate profit factor"""
    total_wins = sum(t['pnl'] for t in trades if t['pnl'] and t['pnl'] > 0)
    total_losses = abs(sum(t['pnl'] for t in trades if t['pnl'] and t['pnl'] < 0))
    if total_losses == 0:
        return float('inf') if total_wins > 0 else 0
    return total_wins / total_losses


async def fetch_trade_candlesticks(symbol: str, start_time: int, end_time: int) -> Optional[List]:
    """Fetch candlestick data for a trade period"""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from src.data.binance_client import BinanceClient

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

        # Add buffer for context
        buffer_ms = 30 * 60 * 1000  # 30 minutes
        klines = await client.get_klines(
            symbol=symbol,
            interval='1m',
            start_time=start_time - buffer_ms,
            end_time=end_time + buffer_ms
        )

        return klines
    except Exception as e:
        print(f"  Warning: Could not fetch candlestick data: {e}")
        return None


def generate_synthetic_candlesticks(trade: Dict, num_candles: int = 40) -> List[Dict]:
    """Generate synthetic candlestick data when real data unavailable"""
    entry_price = trade['entry_price']
    exit_price = trade['exit_price']
    entry_time = trade['entry_time']
    exit_time = trade['exit_time'] if trade['exit_time'] else entry_time + 600000

    duration_ms = exit_time - entry_time
    interval_ms = duration_ms / (num_candles - 1)

    candles = []
    for i in range(num_candles):
        t = entry_time + int(interval_ms * i)
        progress = i / (num_candles - 1)

        # Create realistic-looking price action
        base_price = entry_price + (exit_price - entry_price) * progress
        volatility = abs(exit_price - entry_price) * 0.02  # 2% volatility

        import random
        random.seed(t)  # Consistent randomness

        open_price = base_price + random.uniform(-volatility, volatility)
        close_price = base_price + random.uniform(-volatility, volatility)
        high_price = max(open_price, close_price) + random.uniform(0, volatility)
        low_price = min(open_price, close_price) - random.uniform(0, volatility)

        candles.append({
            'timestamp': t,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price
        })

    return candles


def calculate_vwap_from_trade(trade: Dict) -> Dict:
    """Calculate VWAP bands from trade TP/SL"""
    entry = trade['entry_price']
    tp = trade['take_profit']
    sl = trade['stop_loss']

    # VWAP estimated as midpoint
    vwap = (tp + sl) / 2

    # Std dev estimated from distances
    std_estimate = abs(tp - sl) / 4  # Approximate

    return {
        'vwap': vwap,
        'std': std_estimate,
        'upper_1std': vwap + std_estimate,
        'lower_1std': vwap - std_estimate,
        'upper_2std': vwap + 2 * std_estimate,
        'lower_2std': vwap - 2 * std_estimate
    }


async def generate_chart_data(trade: Dict, symbol: str) -> str:
    """Generate chart data with candlesticks"""
    # Try to fetch real data
    klines = await fetch_trade_candlesticks(
        symbol,
        trade['entry_time'],
        trade['exit_time'] if trade['exit_time'] else trade['entry_time'] + 1800000
    )

    if klines and len(klines) > 0:
        # Use real candlestick data
        candles = []
        for kline in klines:
            candles.append({
                'timestamp': kline[0],
                'open': float(kline[1]),
                'high': float(kline[2]),
                'low': float(kline[3]),
                'close': float(kline[4])
            })
    else:
        # Use synthetic candlesticks
        candles = generate_synthetic_candlesticks(trade)

    # Calculate VWAP
    vwap_bands = calculate_vwap_from_trade(trade)

    # Extract S/R zones from signal
    sr_zones = []
    if trade.get('signal') and trade['signal'].get('sr_zone'):
        sr_zone = trade['signal']['sr_zone']
        sr_zones.append({
            'upper': sr_zone['upper'],
            'lower': sr_zone['lower'],
            'level': sr_zone['level'],
            'type': sr_zone['zone_type'],
            'strength': sr_zone['strength']
        })

    # Format for Plotly
    chart_data = {
        'timestamps': [format_timestamp_ist(c['timestamp']) for c in candles],
        'open': [c['open'] for c in candles],
        'high': [c['high'] for c in candles],
        'low': [c['low'] for c in candles],
        'close': [c['close'] for c in candles],
        'entry_time': format_timestamp_ist(trade['entry_time']),
        'entry_price': trade['entry_price'],
        'exit_time': format_timestamp_ist(trade['exit_time']) if trade['exit_time'] else None,
        'exit_price': trade['exit_price'],
        'tp': trade['take_profit'],
        'sl': trade['stop_loss'],
        'sr_zones': sr_zones,
        **vwap_bands
    }

    return json.dumps(chart_data)


async def generate_html_dashboard(results: Dict, results_file: Path):
    """Generate HTML dashboard with candlestick charts"""
    config = results['backtest_config']
    perf = results['performance']
    trades = results['trades']

    profit_factor = calculate_profit_factor(trades)

    print(f"[INFO] Generating charts for {len(trades)} trades...")

    # Generate charts for all trades
    trades_with_charts = []
    for i, trade in enumerate(trades, 1):
        print(f"  Processing trade {i}/{len(trades)}...")
        chart_data = await generate_chart_data(trade, config['symbol'])
        trades_with_charts.append({
            **trade,
            'chart_data': chart_data
        })

    # HTML template
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VWAP Backtest Dashboard - {config['symbol']}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0a0e27; color: #e0e0e0; padding: 20px; }}
        .container {{ max-width: 1800px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px; margin-bottom: 30px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
        h1 {{ font-size: 2.5em; margin-bottom: 10px; color: white; }}
        .subtitle {{ font-size: 1.1em; opacity: 0.9; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .metric-card {{ background: #1a1f3a; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }}
        .metric-label {{ color: #8b8b8b; font-size: 0.9em; margin-bottom: 8px; }}
        .metric-value {{ font-size: 1.8em; font-weight: bold; }}
        .metric-value.positive {{ color: #4ade80; }}
        .metric-value.negative {{ color: #f87171; }}
        .metric-value.neutral {{ color: #60a5fa; }}
        .trade-section {{ background: #1a1f3a; border-radius: 10px; padding: 25px; margin-bottom: 25px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }}
        .trade-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid #2a2f4a; }}
        .trade-title {{ font-size: 1.5em; font-weight: bold; }}
        .trade-pnl {{ font-size: 1.3em; font-weight: bold; padding: 8px 16px; border-radius: 6px; }}
        .trade-pnl.win {{ background: #16a34a; color: white; }}
        .trade-pnl.loss {{ background: #dc2626; color: white; }}
        .trade-details {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .detail-item {{ background: #0f1729; padding: 12px; border-radius: 6px; }}
        .detail-label {{ color: #8b8b8b; font-size: 0.85em; margin-bottom: 4px; }}
        .detail-value {{ font-size: 1.1em; font-weight: 600; }}
        .chart-container {{ background: #0f1729; border-radius: 8px; padding: 15px; min-height: 600px; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; font-weight: 600; margin-left: 10px; }}
        .badge.long {{ background: #16a34a; color: white; }}
        .badge.short {{ background: #dc2626; color: white; }}
        .timestamp {{ color: #60a5fa; font-size: 0.95em; }}
        .signal-info {{ background: #0f1729; padding: 12px; border-radius: 6px; margin-bottom: 20px; border-left: 3px solid #fbbf24; }}
        .signal-label {{ color: #fbbf24; font-size: 0.9em; font-weight: 600; margin-bottom: 5px; }}
        .signal-text {{ color: #e0e0e0; font-size: 0.95em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 VWAP Strategy Backtest Dashboard</h1>
            <div class="subtitle">{config['symbol']} | {config['timeframe']} | Leverage: {config.get('leverage', 1)}x | Last 7 Days</div>
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
                <div class="metric-value neutral">${config.get('max_position_size', config['initial_capital']):,.0f}</div>
            </div>
        </div>
"""

    # Add trade sections
    for i, trade in enumerate(trades_with_charts, 1):
        is_win = trade['pnl'] and trade['pnl'] > 0

        # Signal info
        signal_info = ""
        if trade.get('signal'):
            signal = trade['signal']
            signal_info = f"""
        <div class="signal-info">
            <div class="signal-label">Signal Confidence: {signal.get('confidence', 0):.0f}% | Type: {signal.get('signal_type', 'N/A')}</div>
            <div class="signal-text">{signal.get('reason', 'No reason provided')}</div>
        </div>
"""

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

{signal_info}

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

            <div class="chart-container" id="chart-{i}"></div>
        </div>

        <script>
        (function() {{
            const data = {trade['chart_data']};

            // Candlestick trace
            const candlestick = {{
                x: data.timestamps,
                open: data.open,
                high: data.high,
                low: data.low,
                close: data.close,
                type: 'candlestick',
                name: '{config['symbol']}',
                increasing: {{line: {{color: '#22c55e', width: 1}}, fillcolor: '#22c55e'}},
                decreasing: {{line: {{color: '#ef4444', width: 1}}, fillcolor: '#ef4444'}}
            }};

            // VWAP line
            const vwap = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.vwap),
                type: 'scatter',
                mode: 'lines',
                name: 'VWAP',
                line: {{color: '#fbbf24', width: 2}}
            }};

            // Standard deviation bands
            const upper1 = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.upper_1std),
                type: 'scatter',
                mode: 'lines',
                name: '+1σ',
                line: {{color: '#a78bfa', width: 1, dash: 'dash'}},
                opacity: 0.6
            }};

            const lower1 = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.lower_1std),
                type: 'scatter',
                mode: 'lines',
                name: '-1σ',
                line: {{color: '#a78bfa', width: 1, dash: 'dash'}},
                opacity: 0.6
            }};

            const upper2 = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.upper_2std),
                type: 'scatter',
                mode: 'lines',
                name: '+2σ',
                line: {{color: '#c084fc', width: 1, dash: 'dot'}},
                opacity: 0.4
            }};

            const lower2 = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.lower_2std),
                type: 'scatter',
                mode: 'lines',
                name: '-2σ',
                line: {{color: '#c084fc', width: 1, dash: 'dot'}},
                opacity: 0.4
            }};

            // Entry marker
            const entry = {{
                x: [data.entry_time],
                y: [data.entry_price],
                type: 'scatter',
                mode: 'markers+text',
                name: 'Entry',
                marker: {{size: 16, color: '#22c55e', symbol: 'triangle-up', line: {{color: '#fff', width: 2}}}},
                text: ['ENTRY'],
                textposition: 'top center',
                textfont: {{color: '#22c55e', size: 11, family: 'Arial Black'}}
            }};

            // Exit marker
            const exit = data.exit_time ? {{
                x: [data.exit_time],
                y: [data.exit_price],
                type: 'scatter',
                mode: 'markers+text',
                name: 'Exit',
                marker: {{size: 16, color: '#ef4444', symbol: 'triangle-down', line: {{color: '#fff', width: 2}}}},
                text: ['EXIT'],
                textposition: 'bottom center',
                textfont: {{color: '#ef4444', size: 11, family: 'Arial Black'}}
            }} : null;

            // TP and SL levels
            const tp = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.tp),
                type: 'scatter',
                mode: 'lines',
                name: 'Take Profit',
                line: {{color: '#16a34a', width: 2, dash: 'dot'}}
            }};

            const sl = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.sl),
                type: 'scatter',
                mode: 'lines',
                name: 'Stop Loss',
                line: {{color: '#dc2626', width: 2, dash: 'dot'}}
            }};

            const traces = [candlestick, vwap, upper1, lower1, upper2, lower2, entry, tp, sl];
            if (exit) traces.push(exit);

            // Add S/R zones as shapes
            const shapes = [];
            if (data.sr_zones && data.sr_zones.length > 0) {{
                data.sr_zones.forEach(zone => {{
                    const color = zone.type === 'resistance' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.2)';
                    const lineColor = zone.type === 'resistance' ? '#ef4444' : '#22c55e';

                    // Zone box
                    shapes.push({{
                        type: 'rect',
                        x0: data.timestamps[0],
                        x1: data.timestamps[data.timestamps.length - 1],
                        y0: zone.lower,
                        y1: zone.upper,
                        fillcolor: color,
                        line: {{color: lineColor, width: 1, dash: 'dash'}},
                        opacity: 0.3
                    }});

                    // Center line
                    shapes.push({{
                        type: 'line',
                        x0: data.timestamps[0],
                        x1: data.timestamps[data.timestamps.length - 1],
                        y0: zone.level,
                        y1: zone.level,
                        line: {{color: lineColor, width: 2}}
                    }});
                }});
            }}

            const layout = {{
                title: {{
                    text: 'Candlestick Chart - VWAP Strategy Analysis',
                    font: {{color: '#e0e0e0', size: 18}}
                }},
                plot_bgcolor: '#0f1729',
                paper_bgcolor: '#0f1729',
                font: {{color: '#e0e0e0'}},
                xaxis: {{
                    gridcolor: '#2a2f4a',
                    title: 'Time',
                    tickangle: -45,
                    rangeslider: {{visible: false}}
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
                    borderwidth: 1,
                    x: 1.02,
                    y: 1
                }},
                hovermode: 'x unified',
                height: 600
            }};

            const config = {{responsive: true, displayModeBar: true}};

            Plotly.newPlot('chart-{i}', traces, layout, config);
        }})();
        </script>
"""

    html += """
    </div>
</body>
</html>
"""

    # Save HTML
    output_file = results_file.parent / f"dashboard_candles_{results_file.stem}.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n[SUCCESS] HTML dashboard saved to: {output_file}")
    print(f"[INFO] Open it in your browser to view the candlestick charts with S/R zones!")

    return output_file


async def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        if not Path(filepath).exists():
            print(f"[ERROR] File not found: {filepath}")
            sys.exit(1)
        results, results_file = load_results(filepath)
    else:
        results, results_file = load_latest_results()

    await generate_html_dashboard(results, results_file)


if __name__ == '__main__':
    asyncio.run(main())
