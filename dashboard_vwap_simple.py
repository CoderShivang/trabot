"""
Simplified VWAP Backtest HTML Dashboard

Creates interactive dashboard without requiring live Binance data fetch.
Uses trade information to generate estimated VWAP visualization.

Usage:
    python dashboard_vwap_simple.py
    python dashboard_vwap_simple.py <results_file.json>
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import statistics


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


def estimate_vwap_from_trade(trade: Dict) -> Dict:
    """Estimate VWAP bands based on trade entry/TP/SL"""
    entry = trade['entry_price']
    tp = trade['take_profit']
    sl = trade['stop_loss']

    # Estimate VWAP as midpoint between TP and SL
    vwap = (tp + sl) / 2

    # Estimate std dev based on TP/SL distance
    if trade['direction'] == 'LONG':
        std_estimate = abs(entry - vwap) / 1.5  # Approximate
    else:
        std_estimate = abs(entry - vwap) / 1.5

    return {
        'vwap': vwap,
        'std': std_estimate,
        'upper_1std': vwap + std_estimate,
        'lower_1std': vwap - std_estimate,
        'upper_2std': vwap + 2 * std_estimate,
        'lower_2std': vwap - 2 * std_estimate
    }


def generate_trade_chart_data(trade: Dict) -> str:
    """Generate simplified chart data for a trade"""
    vwap_bands = estimate_vwap_from_trade(trade)

    # Create time points for visualization
    entry_time = format_timestamp_ist(trade['entry_time'])
    exit_time = format_timestamp_ist(trade['exit_time']) if trade['exit_time'] else entry_time

    # Generate price path (simplified)
    entry_price = trade['entry_price']
    exit_price = trade['exit_price']

    # Create 20 time points for smoother chart
    duration_ms = (trade['exit_time'] - trade['entry_time']) if trade['exit_time'] else 600000  # 10 min default
    timestamps = []
    prices = []

    for i in range(20):
        t = trade['entry_time'] + (duration_ms * i / 19)
        timestamps.append(format_timestamp_ist(int(t)))

        # Linear interpolation with some variation
        progress = i / 19
        price = entry_price + (exit_price - entry_price) * progress
        prices.append(price)

    chart_data = {
        'timestamps': timestamps,
        'prices': prices,
        'entry_time': entry_time,
        'entry_price': entry_price,
        'exit_time': exit_time,
        'exit_price': exit_price,
        'tp': trade['take_profit'],
        'sl': trade['stop_loss'],
        **vwap_bands
    }

    return json.dumps(chart_data)


def generate_html_dashboard(results: Dict, results_file: Path):
    """Generate HTML dashboard"""
    config = results['backtest_config']
    perf = results['performance']
    trades = results['trades']

    profit_factor = calculate_profit_factor(trades)

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
        .container {{ max-width: 1600px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px; margin-bottom: 30px; text-align: center; }}
        h1 {{ font-size: 2.5em; margin-bottom: 10px; color: white; }}
        .subtitle {{ font-size: 1.1em; opacity: 0.9; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .metric-card {{ background: #1a1f3a; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea; }}
        .metric-label {{ color: #8b8b8b; font-size: 0.9em; margin-bottom: 8px; }}
        .metric-value {{ font-size: 1.8em; font-weight: bold; }}
        .metric-value.positive {{ color: #4ade80; }}
        .metric-value.negative {{ color: #f87171; }}
        .metric-value.neutral {{ color: #60a5fa; }}
        .trade-section {{ background: #1a1f3a; border-radius: 10px; padding: 25px; margin-bottom: 25px; }}
        .trade-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid #2a2f4a; }}
        .trade-title {{ font-size: 1.5em; font-weight: bold; }}
        .trade-pnl {{ font-size: 1.3em; font-weight: bold; padding: 8px 16px; border-radius: 6px; }}
        .trade-pnl.win {{ background: #16a34a; color: white; }}
        .trade-pnl.loss {{ background: #dc2626; color: white; }}
        .trade-details {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .detail-item {{ background: #0f1729; padding: 12px; border-radius: 6px; }}
        .detail-label {{ color: #8b8b8b; font-size: 0.85em; margin-bottom: 4px; }}
        .detail-value {{ font-size: 1.1em; font-weight: 600; }}
        .chart-container {{ background: #0f1729; border-radius: 8px; padding: 15px; min-height: 500px; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; font-weight: 600; }}
        .badge.long {{ background: #16a34a; color: white; }}
        .badge.short {{ background: #dc2626; color: white; }}
        .timestamp {{ color: #60a5fa; font-size: 0.95em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 VWAP Backtest Dashboard</h1>
            <div class="subtitle">{config['symbol']} | {config['timeframe']} | Leverage: {config.get('leverage', 1)}x | Period: Last 7 Days</div>
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
    for i, trade in enumerate(trades, 1):
        is_win = trade['pnl'] and trade['pnl'] > 0
        chart_data = generate_trade_chart_data(trade)

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

            <div class="chart-container" id="chart-{i}"></div>
        </div>

        <script>
        (function() {{
            const data = {chart_data};

            const priceLine = {{
                x: data.timestamps,
                y: data.prices,
                type: 'scatter',
                mode: 'lines',
                name: 'Price Path',
                line: {{color: '#60a5fa', width: 2}}
            }};

            const vwap = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.vwap),
                type: 'scatter',
                mode: 'lines',
                name: 'VWAP',
                line: {{color: '#fbbf24', width: 3}}
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
                mode: 'markers+text',
                name: 'Entry',
                marker: {{size: 15, color: '#22c55e', symbol: 'triangle-up'}},
                text: ['ENTRY'],
                textposition: 'top center',
                textfont: {{color: '#22c55e', size: 12}}
            }};

            const exit = {{
                x: [data.exit_time],
                y: [data.exit_price],
                type: 'scatter',
                mode: 'markers+text',
                name: 'Exit',
                marker: {{size: 15, color: '#ef4444', symbol: 'triangle-down'}},
                text: ['EXIT'],
                textposition: 'bottom center',
                textfont: {{color: '#ef4444', size: 12}}
            }};

            const tp = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.tp),
                type: 'scatter',
                mode: 'lines',
                name: 'TP',
                line: {{color: '#16a34a', width: 2, dash: 'dot'}}
            }};

            const sl = {{
                x: data.timestamps,
                y: Array(data.timestamps.length).fill(data.sl),
                type: 'scatter',
                mode: 'lines',
                name: 'SL',
                line: {{color: '#dc2626', width: 2, dash: 'dot'}}
            }};

            const traces = [priceLine, vwap, upper1, lower1, upper2, lower2, entry, exit, tp, sl];

            const layout = {{
                title: {{
                    text: 'Trade Chart - VWAP Strategy Visualization',
                    font: {{color: '#e0e0e0', size: 18}}
                }},
                plot_bgcolor: '#0f1729',
                paper_bgcolor: '#0f1729',
                font: {{color: '#e0e0e0'}},
                xaxis: {{
                    gridcolor: '#2a2f4a',
                    title: 'Time',
                    tickangle: -45
                }},
                yaxis: {{
                    gridcolor: '#2a2f4a',
                    title: 'Price (USDT)'
                }},
                showlegend: true,
                legend: {{
                    bgcolor: '#1a1f3a',
                    bordercolor: '#2a2f4a',
                    borderwidth: 1,
                    x: 1.02,
                    y: 1
                }},
                hovermode: 'x unified',
                height: 500
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
    output_file = results_file.parent / f"dashboard_simple_{results_file.stem}.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n[SUCCESS] HTML dashboard saved to: {output_file}")
    print(f"[INFO] Open it in your browser to view the charts!")

    return output_file


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        if not Path(filepath).exists():
            print(f"[ERROR] File not found: {filepath}")
            sys.exit(1)
        results, results_file = load_results(filepath)
    else:
        results, results_file = load_latest_results()

    generate_html_dashboard(results, results_file)


if __name__ == '__main__':
    main()
