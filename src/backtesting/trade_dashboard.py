"""
Interactive HTML Dashboard for Backtest Trade Analysis
Generates a single HTML file with all trades, charts, reasoning, and ratings
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TradeDashboard:
    def __init__(self, config, binance_client):
        self.config = config
        self.client = binance_client
        self.output_dir = Path("backtest_results")
        self.output_dir.mkdir(exist_ok=True)

    async def generate_dashboard(
        self,
        trades: List[Dict],
        metrics: Any,
        start_date: datetime,
        end_date: datetime
    ):
        """
        Generate a comprehensive HTML dashboard with all trades and analysis
        """
        logger.info(f"[DASHBOARD] Generating interactive dashboard for {len(trades)} trades...")

        html_content = self._generate_html_header()
        html_content += self._generate_summary_section(metrics, len(trades), start_date, end_date)

        # Generate individual trade cards with charts
        for i, trade in enumerate(trades, 1):
            try:
                trade_html = await self._generate_trade_card(trade, i)
                html_content += trade_html
            except Exception as e:
                logger.error(f"Error generating trade #{i} card: {e}")
                continue

        html_content += self._generate_html_footer()

        # Save dashboard
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"dashboard_{timestamp}.html"

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"[DASHBOARD] Dashboard saved to {filepath}")
        return str(filepath)

    def _generate_html_header(self):
        """Generate HTML header with styles"""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Trade Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            margin-bottom: 30px;
            text-align: center;
        }

        .header h1 {
            color: #667eea;
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .summary {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            margin-bottom: 30px;
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }

        .metric-card {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .metric-label {
            font-size: 0.85em;
            color: #666;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .metric-value {
            font-size: 1.8em;
            font-weight: bold;
            color: #333;
        }

        .metric-value.positive { color: #10b981; }
        .metric-value.negative { color: #ef4444; }

        .trade-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            margin-bottom: 30px;
            border-left: 5px solid #667eea;
        }

        .trade-card.winner { border-left-color: #10b981; }
        .trade-card.loser { border-left-color: #ef4444; }

        .trade-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f0f0f0;
        }

        .trade-title {
            font-size: 1.5em;
            font-weight: bold;
            color: #333;
        }

        .trade-pnl {
            font-size: 1.8em;
            font-weight: bold;
        }

        .trade-pnl.positive { color: #10b981; }
        .trade-pnl.negative { color: #ef4444; }

        .trade-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .detail-item {
            background: #f9fafb;
            padding: 12px 15px;
            border-radius: 8px;
            border-left: 3px solid #667eea;
        }

        .detail-label {
            font-size: 0.8em;
            color: #666;
            margin-bottom: 4px;
            text-transform: uppercase;
        }

        .detail-value {
            font-size: 1.1em;
            font-weight: 600;
            color: #333;
        }

        .reasoning-section {
            background: #fffbeb;
            border: 2px solid #fbbf24;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }

        .reasoning-title {
            font-size: 1.2em;
            font-weight: bold;
            color: #92400e;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
        }

        .reasoning-title::before {
            content: "💡";
            margin-right: 8px;
            font-size: 1.3em;
        }

        .reason-list {
            list-style: none;
            padding-left: 0;
        }

        .reason-item {
            padding: 8px 0;
            padding-left: 25px;
            position: relative;
            color: #78350f;
            line-height: 1.6;
        }

        .reason-item::before {
            content: "→";
            position: absolute;
            left: 0;
            color: #f59e0b;
            font-weight: bold;
        }

        .rating-section {
            display: flex;
            align-items: center;
            gap: 15px;
            background: #f0f9ff;
            padding: 15px 20px;
            border-radius: 10px;
            margin-top: 15px;
        }

        .rating-label {
            font-weight: bold;
            color: #0369a1;
        }

        .stars {
            font-size: 1.5em;
            letter-spacing: 3px;
        }

        .chart-container {
            margin: 20px 0;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .footer {
            text-align: center;
            color: white;
            padding: 20px;
            margin-top: 30px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Backtest Trade Dashboard</h1>
            <p style="color: #666; margin-top: 10px; font-size: 1.1em;">Interactive Analysis & Trade Insights</p>
        </div>
"""

    def _generate_summary_section(self, metrics, num_trades, start_date, end_date):
        """Generate summary metrics section"""

        win_rate = getattr(metrics, 'win_rate', 0)
        net_pnl = getattr(metrics, 'net_pnl', 0)
        total_fees = getattr(metrics, 'total_fees', 0)
        avg_win = getattr(metrics, 'avg_win', 0)
        avg_loss = getattr(metrics, 'avg_loss', 0)
        profit_factor = getattr(metrics, 'profit_factor', 0)
        avg_rr = getattr(metrics, 'avg_risk_reward', 0)

        pnl_class = "positive" if net_pnl > 0 else "negative"

        return f"""
        <div class="summary">
            <h2 style="color: #667eea; margin-bottom: 20px;">📈 Backtest Summary</h2>
            <p style="color: #666; margin-bottom: 20px;">
                <strong>Period:</strong> {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}
                ({(end_date - start_date).days} days)
            </p>

            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">Total Trades</div>
                    <div class="metric-value">{num_trades}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Win Rate</div>
                    <div class="metric-value {'positive' if win_rate >= 50 else 'negative'}">{win_rate:.1f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Net P&L</div>
                    <div class="metric-value {pnl_class}">${net_pnl:+.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Total Fees</div>
                    <div class="metric-value negative">${total_fees:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Avg Win</div>
                    <div class="metric-value positive">${avg_win:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Avg Loss</div>
                    <div class="metric-value negative">${avg_loss:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Profit Factor</div>
                    <div class="metric-value {'positive' if profit_factor > 1 else 'negative'}">{profit_factor:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Avg R:R</div>
                    <div class="metric-value">{avg_rr:.2f}:1</div>
                </div>
            </div>
        </div>
"""

    async def _generate_trade_card(self, trade: Dict, trade_num: int):
        """Generate a single trade card with chart and details"""

        # Extract trade data
        symbol = trade['symbol']
        direction = trade['direction']
        entry_price = trade['entry_price']
        entry_time = trade['entry_time']
        exit_price = trade.get('exit_price', entry_price)
        exit_time = trade.get('exit_time', entry_time)
        net_pnl = trade['net_pnl']
        fees = trade['fees']
        exit_reason = trade.get('exit_reason', 'unknown')
        duration_min = trade.get('duration_minutes', 0)

        # Determine if winner/loser
        is_winner = net_pnl > 0
        card_class = "winner" if is_winner else "loser"
        pnl_class = "positive" if is_winner else "negative"

        # Get market context
        market_ctx = trade.get('market_context', {})
        regime = market_ctx.get('regime', 'unknown').upper()
        adx = market_ctx.get('adx', 0)
        vwap = market_ctx.get('vwap', 0)

        # Get CLC score details
        clc_score = trade.get('clc_score', {})
        total_score = clc_score.get('total_score', 0)

        # Generate reasoning
        reasoning_html = self._generate_reasoning(trade, clc_score, market_ctx)

        # Generate rating
        rating_html = self._generate_rating(trade, clc_score, is_winner)

        # Generate chart
        chart_html = await self._generate_trade_chart(trade, trade_num)

        # Convert timestamps to IST
        entry_dt = datetime.fromtimestamp(entry_time / 1000) + timedelta(hours=5, minutes=30)
        exit_dt = datetime.fromtimestamp(exit_time / 1000) + timedelta(hours=5, minutes=30)

        # Fee breakdown
        used_limit = trade.get('used_limit_order', False)
        entry_fee = trade.get('entry_fee', 0)
        exit_fee = trade.get('exit_fee', 0)
        fee_type = "Limit Entry (0.02%)" if used_limit else "Market Entry (0.04%)"

        return f"""
        <div class="trade-card {card_class}">
            <div class="trade-header">
                <div class="trade-title">
                    Trade #{trade_num} - {direction} {symbol}
                    <span style="font-size: 0.6em; color: #666; font-weight: normal; margin-left: 10px;">
                        {entry_dt.strftime('%Y-%m-%d %H:%M IST')}
                    </span>
                </div>
                <div class="trade-pnl {pnl_class}">${net_pnl:+.2f}</div>
            </div>

            <div class="trade-details">
                <div class="detail-item">
                    <div class="detail-label">Entry Price</div>
                    <div class="detail-value">${entry_price:,.2f}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Exit Price</div>
                    <div class="detail-value">${exit_price:,.2f}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Duration</div>
                    <div class="detail-value">{duration_min:.1f} min</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Exit Reason</div>
                    <div class="detail-value">{exit_reason.replace('_', ' ').title()}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Fees</div>
                    <div class="detail-value">${fees:.2f} ({fee_type})</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Market Regime</div>
                    <div class="detail-value">{regime} (ADX={adx:.1f})</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">CLC Score</div>
                    <div class="detail-value">{total_score:.1f}/100</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">VWAP</div>
                    <div class="detail-value">${vwap:,.2f}</div>
                </div>
            </div>

            {reasoning_html}
            {rating_html}

            <div class="chart-container">
                {chart_html}
            </div>
        </div>
"""

    def _generate_reasoning(self, trade: Dict, clc_score: Dict, market_ctx: Dict):
        """Generate trade reasoning section"""

        reasons = []

        # Context reasoning
        regime = market_ctx.get('regime', 'unknown')
        adx = market_ctx.get('adx', 0)
        if regime == 'trending':
            reasons.append(f"<strong>Trending market</strong> detected (ADX={adx:.1f}) - favorable for directional trades")
        elif regime == 'ranging':
            reasons.append(f"<strong>Ranging market</strong> detected (ADX={adx:.1f}) - mean reversion setup")

        # Location reasoning
        location_type = clc_score.get('location_type', 'unknown')
        if location_type and location_type != 'unknown':
            reasons.append(f"Price at key <strong>{location_type}</strong> level - high probability reversal zone")

        # Confirmation reasoning
        conf_signals = clc_score.get('confirmation_signals', [])
        if conf_signals:
            signal_str = ", ".join(conf_signals[:3])  # Top 3
            reasons.append(f"Multiple confirmations: <strong>{signal_str}</strong>")

        # Big orders
        big_orders = clc_score.get('big_orders_score', 0)
        if big_orders > 0:
            reasons.append(f"<strong>Institutional activity</strong> detected (score: {big_orders:.1f})")

        # S/R proximity
        sr_zones = trade.get('sr_zones', [])
        if sr_zones:
            closest = sr_zones[0]
            zone_type = closest.get('type', 'support/resistance')
            dist = closest.get('distance_pct', 0)
            reasons.append(f"Near <strong>{zone_type}</strong> zone (only {dist:.2f}% away)")

        # Adaptive scoring
        context_score = clc_score.get('context_score', 0)
        location_score = clc_score.get('location_score', 0)
        if context_score > 7 and location_score > 7:
            reasons.append("<strong>High-quality setup</strong> - both context and location scores above threshold")

        if not reasons:
            reasons.append("Standard CLC entry criteria met")

        reasons_html = "\n".join([f'<li class="reason-item">{r}</li>' for r in reasons])

        return f"""
        <div class="reasoning-section">
            <div class="reasoning-title">Why This Trade Was Taken</div>
            <ul class="reason-list">
                {reasons_html}
            </ul>
        </div>
"""

    def _generate_rating(self, trade: Dict, clc_score: Dict, is_winner: bool):
        """Generate trade quality rating (1-5 stars)"""

        # Calculate rating based on:
        # - CLC score (40%)
        # - Win/Loss outcome (30%)
        # - Risk/Reward achieved (30%)

        total_score = clc_score.get('total_score', 0)
        net_pnl = trade['net_pnl']

        # CLC score contribution (0-2 stars)
        score_stars = min(2.0, (total_score / 20) * 2)  # Max 2 stars from score

        # Outcome contribution (0-1.5 stars)
        outcome_stars = 1.5 if is_winner else 0.5

        # P&L magnitude contribution (0-1.5 stars)
        abs_pnl = abs(net_pnl)
        if abs_pnl >= 15:
            pnl_stars = 1.5
        elif abs_pnl >= 10:
            pnl_stars = 1.0
        else:
            pnl_stars = 0.5

        total_stars = score_stars + outcome_stars + pnl_stars
        total_stars = min(5.0, total_stars)  # Cap at 5

        # Generate star display
        full_stars = int(total_stars)
        half_star = (total_stars - full_stars) >= 0.5
        empty_stars = 5 - full_stars - (1 if half_star else 0)

        stars_html = "⭐" * full_stars
        if half_star:
            stars_html += "✨"
        stars_html += "☆" * empty_stars

        quality = "Excellent" if total_stars >= 4.5 else \
                  "Very Good" if total_stars >= 3.5 else \
                  "Good" if total_stars >= 2.5 else \
                  "Fair" if total_stars >= 1.5 else "Poor"

        return f"""
        <div class="rating-section">
            <div class="rating-label">Trade Quality:</div>
            <div class="stars">{stars_html}</div>
            <div style="font-weight: bold; color: #0369a1;">({total_stars:.1f}/5.0 - {quality})</div>
        </div>
"""

    async def _generate_trade_chart(self, trade: Dict, trade_num: int):
        """Generate interactive Plotly chart for a trade"""

        try:
            symbol = trade['symbol']
            entry_time = trade['entry_time']
            entry_price = trade['entry_price']
            exit_price = trade.get('exit_price')
            exit_time = trade.get('exit_time')
            direction = trade['direction']

            # Fetch klines data (4 hours around entry)
            lookback_ms = 2 * 60 * 60 * 1000  # 2 hours
            lookahead_ms = 2 * 60 * 60 * 1000  # 2 hours
            start_time = entry_time - lookback_ms
            end_time = entry_time + lookahead_ms

            klines = await self.client.get_klines(
                symbol=symbol,
                interval='1m',
                limit=240,
                start_time=start_time,
                end_time=end_time
            )

            if not klines or len(klines) < 20:
                return "<p>Insufficient data for chart</p>"

            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'qav', 'num_trades', 'tb_base', 'tb_quote', 'ignore'
            ])

            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            # Calculate indicators
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean() if len(df) >= 200 else df['ema50']

            # VWAP
            df['tp'] = (df['high'] + df['low'] + df['close']) / 3
            df['vwap'] = (df['tp'] * df['volume']).cumsum() / df['volume'].cumsum()

            # Create candlestick chart
            fig = go.Figure()

            # Candlesticks
            fig.add_trace(go.Candlestick(
                x=df['timestamp'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price',
                increasing_line_color='#10b981',
                decreasing_line_color='#ef4444'
            ))

            # EMAs
            fig.add_trace(go.Scatter(
                x=df['timestamp'], y=df['ema20'],
                name='EMA 20', line=dict(color='#3b82f6', width=2)
            ))
            fig.add_trace(go.Scatter(
                x=df['timestamp'], y=df['ema50'],
                name='EMA 50', line=dict(color='#f59e0b', width=2)
            ))
            fig.add_trace(go.Scatter(
                x=df['timestamp'], y=df['ema200'],
                name='EMA 200', line=dict(color='#ef4444', width=2)
            ))

            # VWAP
            fig.add_trace(go.Scatter(
                x=df['timestamp'], y=df['vwap'],
                name='VWAP', line=dict(color='#8b5cf6', width=2, dash='dash')
            ))

            # S/R Zones
            sr_zones = trade.get('sr_zones', [])
            for zone in sr_zones[:5]:  # Top 5 zones
                level = zone.get('level', 0)
                zone_type = zone.get('type', 'unknown')
                color = 'rgba(239, 68, 68, 0.2)' if zone_type == 'resistance' else 'rgba(16, 185, 129, 0.2)'

                fig.add_hline(
                    y=level,
                    line=dict(color=color.replace('0.2', '0.6'), dash='dot'),
                    annotation_text=f"{zone_type[:1].upper()}",
                    annotation_position="right"
                )

            # Entry marker
            entry_dt = pd.to_datetime(entry_time, unit='ms')
            entry_color = '#10b981' if direction == 'LONG' else '#ef4444'
            entry_symbol = 'triangle-up' if direction == 'LONG' else 'triangle-down'

            fig.add_trace(go.Scatter(
                x=[entry_dt],
                y=[entry_price],
                mode='markers',
                name=f'{direction} Entry',
                marker=dict(
                    color=entry_color,
                    size=15,
                    symbol=entry_symbol,
                    line=dict(color='white', width=2)
                )
            ))

            # Exit marker
            if exit_price and exit_time:
                exit_dt = pd.to_datetime(exit_time, unit='ms')
                fig.add_trace(go.Scatter(
                    x=[exit_dt],
                    y=[exit_price],
                    mode='markers',
                    name='Exit',
                    marker=dict(
                        color='#6366f1',
                        size=12,
                        symbol='x',
                        line=dict(color='white', width=2)
                    )
                ))

            # Update layout
            fig.update_layout(
                title=f"Trade #{trade_num} - {direction} {symbol}",
                xaxis_title="Time (UTC+5:30 IST)",
                yaxis_title="Price (USDT)",
                template="plotly_white",
                height=500,
                hovermode='x unified',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )

            # Return HTML div
            return fig.to_html(include_plotlyjs=False, div_id=f"chart_{trade_num}")

        except Exception as e:
            logger.error(f"Error generating chart for trade {trade_num}: {e}")
            return f"<p>Chart unavailable: {str(e)}</p>"

    def _generate_html_footer(self):
        """Generate HTML footer"""
        return """
        <div class="footer">
            <p>Generated by Trabot Backtest Engine | Powered by Claude Code</p>
            <p style="margin-top: 10px; font-size: 0.8em; opacity: 0.8;">
                Dashboard includes interactive charts, trade reasoning, and quality ratings
            </p>
        </div>
    </div>
</body>
</html>
"""
