"""
VWAP Backtest Dashboard Generator

Creates interactive HTML dashboard with:
- Candlestick charts
- VWAP bands (±1σ, ±2σ)
- S/R zones
- Trade entry/exit markers
- Performance metrics
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime


class VWAPDashboard:
    """Generate interactive HTML dashboard for VWAP backtest results"""

    def __init__(self, results_path: str, ohlcv_data: pd.DataFrame):
        """
        Args:
            results_path: Path to backtest JSON results
            ohlcv_data: DataFrame with OHLCV data (timestamp, open, high, low, close, volume)
        """
        self.results_path = Path(results_path)
        self.df = ohlcv_data.copy()

        # Load backtest results
        with open(results_path, 'r') as f:
            self.results = json.load(f)

        self.trades = self.results['trades']
        self.performance = self.results['performance']
        self.config = self.results['backtest_config']

    def generate(self, output_path: str = None):
        """Generate and save interactive HTML dashboard"""
        if output_path is None:
            output_path = self.results_path.parent / 'dashboard.html'

        # Create figure with subplots
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            subplot_titles=('Price Chart with VWAP & Trades', 'Volume'),
            row_heights=[0.7, 0.3]
        )

        # Add candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=self.df['timestamp'],
                open=self.df['open'],
                high=self.df['high'],
                low=self.df['low'],
                close=self.df['close'],
                name='Price',
                increasing_line_color='#26a69a',
                decreasing_line_color='#ef5350'
            ),
            row=1, col=1
        )

        # Add VWAP and bands (calculated from session data)
        self._add_vwap_bands(fig)

        # Add S/R zones
        self._add_sr_zones(fig)

        # Add trade markers
        self._add_trade_markers(fig)

        # Add volume bars
        colors = ['#26a69a' if close >= open else '#ef5350'
                  for close, open in zip(self.df['close'], self.df['open'])]

        fig.add_trace(
            go.Bar(
                x=self.df['timestamp'],
                y=self.df['volume'],
                name='Volume',
                marker_color=colors,
                showlegend=False
            ),
            row=2, col=1
        )

        # Update layout
        fig.update_layout(
            title=dict(
                text=f"VWAP Backtest Dashboard - {self.config['symbol']}<br>" +
                     f"<sub>Win Rate: {self.performance['win_rate']:.1f}% | " +
                     f"Total Trades: {self.performance['total_trades']} | " +
                     f"Net P&L: ${self.performance['net_pnl']:.2f} ({self.performance['return_pct']:.2f}%)</sub>",
                x=0.5,
                xanchor='center'
            ),
            xaxis_rangeslider_visible=False,
            xaxis2_title='Time',
            yaxis_title='Price (USDT)',
            yaxis2_title='Volume',
            hovermode='x unified',
            height=900,
            template='plotly_dark',
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            )
        )

        # Save to HTML
        fig.write_html(str(output_path))
        print(f"\n[DASHBOARD] Saved to: {output_path}")
        return str(output_path)

    def _add_vwap_bands(self, fig):
        """Add VWAP and standard deviation bands"""
        # Calculate session-based VWAP (resets daily)
        df = self.df.copy()
        df['date'] = pd.to_datetime(df['timestamp']).dt.date

        vwap_data = []
        upper_1std_data = []
        lower_1std_data = []
        upper_2std_data = []
        lower_2std_data = []

        for date in df['date'].unique():
            session_df = df[df['date'] == date].copy()

            # Calculate typical price
            typical_price = (session_df['high'] + session_df['low'] + session_df['close']) / 3

            # Calculate VWAP
            cumulative_pv = (typical_price * session_df['volume']).cumsum()
            cumulative_volume = session_df['volume'].cumsum()
            running_vwap = cumulative_pv / cumulative_volume

            # Calculate standard deviation
            squared_diff = (typical_price - running_vwap) ** 2
            cumulative_variance = (squared_diff * session_df['volume']).cumsum() / cumulative_volume
            std = cumulative_variance.apply(lambda x: x ** 0.5)

            vwap_data.extend(running_vwap.tolist())
            upper_1std_data.extend((running_vwap + std).tolist())
            lower_1std_data.extend((running_vwap - std).tolist())
            upper_2std_data.extend((running_vwap + 2*std).tolist())
            lower_2std_data.extend((running_vwap - 2*std).tolist())

        # Add VWAP line
        fig.add_trace(
            go.Scatter(
                x=self.df['timestamp'],
                y=vwap_data,
                name='VWAP',
                line=dict(color='#ffa726', width=2),
                mode='lines'
            ),
            row=1, col=1
        )

        # Add ±1σ bands
        fig.add_trace(
            go.Scatter(
                x=self.df['timestamp'],
                y=upper_1std_data,
                name='+1σ',
                line=dict(color='#42a5f5', width=1, dash='dash'),
                mode='lines'
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=self.df['timestamp'],
                y=lower_1std_data,
                name='-1σ',
                line=dict(color='#42a5f5', width=1, dash='dash'),
                mode='lines',
                fill='tonexty',
                fillcolor='rgba(66, 165, 245, 0.1)'
            ),
            row=1, col=1
        )

        # Add ±2σ bands
        fig.add_trace(
            go.Scatter(
                x=self.df['timestamp'],
                y=upper_2std_data,
                name='+2σ',
                line=dict(color='#66bb6a', width=1, dash='dot'),
                mode='lines'
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=self.df['timestamp'],
                y=lower_2std_data,
                name='-2σ',
                line=dict(color='#66bb6a', width=1, dash='dot'),
                mode='lines'
            ),
            row=1, col=1
        )

    def _add_sr_zones(self, fig):
        """Add S/R zones as horizontal rectangles"""
        # Extract unique zones from trades
        zones = {}
        for trade in self.trades:
            if 'sr_zone' in trade.get('signal', {}):
                zone = trade['signal']['sr_zone']
                zone_key = f"{zone['level']:.2f}_{zone['timeframe']}"
                if zone_key not in zones:
                    zones[zone_key] = zone

        # Add zones to chart (limit to most significant ones)
        for i, (zone_key, zone) in enumerate(list(zones.items())[:10]):  # Limit to 10 zones
            color = 'rgba(76, 175, 80, 0.15)' if zone['zone_type'] in ['support', 'both'] else 'rgba(244, 67, 54, 0.15)'

            fig.add_hrect(
                y0=zone['lower'],
                y1=zone['upper'],
                fillcolor=color,
                line_width=0,
                layer='below',
                row=1, col=1
            )

            # Add zone label
            fig.add_annotation(
                x=self.df['timestamp'].iloc[len(self.df)//2],
                y=zone['level'],
                text=f"S/R {zone['timeframe']} (str:{zone['strength']})",
                showarrow=False,
                font=dict(size=8, color='white'),
                bgcolor=color.replace('0.15', '0.5'),
                row=1, col=1
            )

    def _add_trade_markers(self, fig):
        """Add entry and exit markers for trades"""
        entry_longs = []
        entry_shorts = []
        exit_wins = []
        exit_losses = []

        for trade in self.trades:
            entry_time = pd.to_datetime(trade['entry_time'], unit='ms')
            exit_time = pd.to_datetime(trade['exit_time'], unit='ms')

            entry_data = {
                'x': entry_time,
                'y': trade['entry_price'],
                'text': f"{trade['direction']} Entry<br>Price: ${trade['entry_price']:,.2f}<br>Reason: {trade['signal']['reason'][:50]}...",
                'confidence': trade['signal']['confidence']
            }

            exit_data = {
                'x': exit_time,
                'y': trade['exit_price'],
                'text': f"{trade['exit_reason']}<br>P&L: ${trade['pnl']:.2f} ({trade['pnl_pct']:.2f}%)",
                'pnl': trade['pnl']
            }

            if trade['direction'] == 'LONG':
                entry_longs.append(entry_data)
            else:
                entry_shorts.append(entry_data)

            if trade['pnl'] > 0:
                exit_wins.append(exit_data)
            else:
                exit_losses.append(exit_data)

        # Add LONG entries (green triangles up)
        if entry_longs:
            fig.add_trace(
                go.Scatter(
                    x=[e['x'] for e in entry_longs],
                    y=[e['y'] for e in entry_longs],
                    mode='markers',
                    name='LONG Entry',
                    marker=dict(
                        symbol='triangle-up',
                        size=12,
                        color='#26a69a',
                        line=dict(color='white', width=1)
                    ),
                    text=[e['text'] for e in entry_longs],
                    hovertemplate='%{text}<extra></extra>'
                ),
                row=1, col=1
            )

        # Add SHORT entries (red triangles down)
        if entry_shorts:
            fig.add_trace(
                go.Scatter(
                    x=[e['x'] for e in entry_shorts],
                    y=[e['y'] for e in entry_shorts],
                    mode='markers',
                    name='SHORT Entry',
                    marker=dict(
                        symbol='triangle-down',
                        size=12,
                        color='#ef5350',
                        line=dict(color='white', width=1)
                    ),
                    text=[e['text'] for e in entry_shorts],
                    hovertemplate='%{text}<extra></extra>'
                ),
                row=1, col=1
            )

        # Add winning exits (green X)
        if exit_wins:
            fig.add_trace(
                go.Scatter(
                    x=[e['x'] for e in exit_wins],
                    y=[e['y'] for e in exit_wins],
                    mode='markers',
                    name='Win Exit',
                    marker=dict(
                        symbol='x',
                        size=10,
                        color='#66bb6a',
                        line=dict(width=2)
                    ),
                    text=[e['text'] for e in exit_wins],
                    hovertemplate='%{text}<extra></extra>'
                ),
                row=1, col=1
            )

        # Add losing exits (red X)
        if exit_losses:
            fig.add_trace(
                go.Scatter(
                    x=[e['x'] for e in exit_losses],
                    y=[e['y'] for e in exit_losses],
                    mode='markers',
                    name='Loss Exit',
                    marker=dict(
                        symbol='x',
                        size=10,
                        color='#ff7043',
                        line=dict(width=2)
                    ),
                    text=[e['text'] for e in exit_losses],
                    hovertemplate='%{text}<extra></extra>'
                ),
                row=1, col=1
            )
