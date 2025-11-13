"""
Interactive VWAP Backtest Dashboard with Filtering

Creates interactive web app with:
- Trade filtering (WIN/LOSS, LONG/SHORT, date range, etc.)
- Clickable trade list
- Individual trade charts showing only relevant context
- VWAP bands and S/R zones specific to each trade
"""

import dash
from dash import dcc, html, Input, Output, State, dash_table
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta
import webbrowser
from threading import Timer


class InteractiveDashboard:
    """Interactive HTML dashboard for filtering and inspecting trades"""

    def __init__(self, results_path: str, ohlcv_data: pd.DataFrame):
        """
        Args:
            results_path: Path to backtest JSON results
            ohlcv_data: DataFrame with OHLCV data (timestamp, open, high, low, close, volume)
        """
        self.results_path = Path(results_path)
        self.df = ohlcv_data.copy()

        # Ensure timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(self.df['timestamp']):
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])

        # Load backtest results
        with open(results_path, 'r') as f:
            self.results = json.load(f)

        self.trades = self.results['trades']
        self.performance = self.results['performance']
        self.config = self.results['backtest_config']

        # Initialize Dash app
        self.app = dash.Dash(__name__)
        self.app.layout = self._create_layout()
        self._setup_callbacks()

    def _create_layout(self):
        """Create dashboard layout with filters and charts"""
        return html.Div([
            html.H1(f"VWAP Backtest Dashboard - {self.config['symbol']}",
                    style={'textAlign': 'center', 'color': '#2c3e50'}),

            # Performance summary
            html.Div([
                html.Div([
                    html.H3(f"Win Rate: {self.performance['win_rate']:.1f}%",
                           style={'color': '#27ae60' if self.performance['win_rate'] > 50 else '#e74c3c'}),
                ], style={'display': 'inline-block', 'margin': '20px'}),
                html.Div([
                    html.H3(f"Total Trades: {self.performance['total_trades']}",
                           style={'color': '#2980b9'}),
                ], style={'display': 'inline-block', 'margin': '20px'}),
                html.Div([
                    html.H3(f"Net P&L: ${self.performance['net_pnl']:.2f} ({self.performance['return_pct']:.2f}%)",
                           style={'color': '#27ae60' if self.performance['net_pnl'] > 0 else '#e74c3c'}),
                ], style={'display': 'inline-block', 'margin': '20px'}),
            ], style={'textAlign': 'center', 'backgroundColor': '#ecf0f1', 'padding': '10px', 'borderRadius': '5px'}),

            html.Hr(),

            # Filters
            html.Div([
                html.H3("Filter Trades", style={'color': '#34495e'}),
                html.Div([
                    # Outcome filter
                    html.Div([
                        html.Label("Outcome:", style={'fontWeight': 'bold'}),
                        dcc.Dropdown(
                            id='outcome-filter',
                            options=[
                                {'label': 'All Trades', 'value': 'all'},
                                {'label': 'Wins Only', 'value': 'win'},
                                {'label': 'Losses Only', 'value': 'loss'}
                            ],
                            value='all',
                            style={'width': '200px'}
                        )
                    ], style={'display': 'inline-block', 'margin': '10px'}),

                    # Direction filter
                    html.Div([
                        html.Label("Direction:", style={'fontWeight': 'bold'}),
                        dcc.Dropdown(
                            id='direction-filter',
                            options=[
                                {'label': 'All Directions', 'value': 'all'},
                                {'label': 'LONG Only', 'value': 'LONG'},
                                {'label': 'SHORT Only', 'value': 'SHORT'}
                            ],
                            value='all',
                            style={'width': '200px'}
                        )
                    ], style={'display': 'inline-block', 'margin': '10px'}),

                    # Signal type filter
                    html.Div([
                        html.Label("Signal Type:", style={'fontWeight': 'bold'}),
                        dcc.Dropdown(
                            id='signal-filter',
                            options=[
                                {'label': 'All Types', 'value': 'all'},
                                {'label': 'Mean Reversion', 'value': 'mean_reversion'},
                                {'label': 'Trend Continuation', 'value': 'trend_continuation'}
                            ],
                            value='all',
                            style={'width': '200px'}
                        )
                    ], style={'display': 'inline-block', 'margin': '10px'}),
                ]),
            ], style={'backgroundColor': '#ecf0f1', 'padding': '15px', 'borderRadius': '5px', 'margin': '20px 0'}),

            # Trade list
            html.Div([
                html.H3("Trade List (Click to View Chart)", style={'color': '#34495e'}),
                html.Div(id='trade-count', style={'marginBottom': '10px', 'fontWeight': 'bold'}),
                dash_table.DataTable(
                    id='trade-table',
                    columns=[
                        {'name': '#', 'id': 'trade_num'},
                        {'name': 'Direction', 'id': 'direction'},
                        {'name': 'Type', 'id': 'signal_type'},
                        {'name': 'Entry Time', 'id': 'entry_time_str'},
                        {'name': 'Entry Price', 'id': 'entry_price_str'},
                        {'name': 'Exit Price', 'id': 'exit_price_str'},
                        {'name': 'P&L', 'id': 'pnl_str'},
                        {'name': 'P&L %', 'id': 'pnl_pct_str'},
                        {'name': 'Reason', 'id': 'reason_short'},
                    ],
                    style_data_conditional=[
                        {
                            'if': {'filter_query': '{pnl} > 0'},
                            'backgroundColor': '#d4edda',
                            'color': '#155724'
                        },
                        {
                            'if': {'filter_query': '{pnl} <= 0'},
                            'backgroundColor': '#f8d7da',
                            'color': '#721c24'
                        }
                    ],
                    style_header={
                        'backgroundColor': '#2c3e50',
                        'color': 'white',
                        'fontWeight': 'bold'
                    },
                    style_cell={
                        'textAlign': 'left',
                        'padding': '10px'
                    },
                    row_selectable='single',
                    selected_rows=[],
                    page_size=10
                )
            ], style={'margin': '20px 0'}),

            # Selected trade info
            html.Div(id='selected-trade-info', style={'margin': '20px 0'}),

            # Chart for selected trade
            html.Div([
                html.H3("Trade Chart", style={'color': '#34495e'}),
                dcc.Graph(id='trade-chart', style={'height': '800px'})
            ])
        ], style={'padding': '20px', 'fontFamily': 'Arial, sans-serif'})

    def _setup_callbacks(self):
        """Setup Dash callbacks for interactivity"""

        @self.app.callback(
            [Output('trade-table', 'data'),
             Output('trade-count', 'children')],
            [Input('outcome-filter', 'value'),
             Input('direction-filter', 'value'),
             Input('signal-filter', 'value')]
        )
        def update_trade_table(outcome, direction, signal_type):
            """Filter trade list based on selections"""
            filtered = self._filter_trades(outcome, direction, signal_type)

            # Format trades for table
            table_data = []
            for i, trade in enumerate(filtered, 1):
                table_data.append({
                    'trade_num': i,
                    'direction': trade['direction'],
                    'signal_type': trade['signal']['signal_type'],
                    'entry_time_str': pd.to_datetime(trade['entry_time'], unit='ms').strftime('%Y-%m-%d %H:%M'),
                    'entry_price_str': f"${trade['entry_price']:,.2f}",
                    'exit_price_str': f"${trade['exit_price']:,.2f}",
                    'pnl_str': f"${trade['pnl']:,.2f}",
                    'pnl_pct_str': f"{trade['pnl_pct']:+.2f}%",
                    'reason_short': trade['signal']['reason'][:60] + '...' if len(trade['signal']['reason']) > 60 else trade['signal']['reason'],
                    'pnl': trade['pnl'],  # Hidden field for conditional formatting
                    'trade_index': self.trades.index(trade)  # Store original index
                })

            count_text = f"Showing {len(filtered)} trades"
            return table_data, count_text

        @self.app.callback(
            [Output('trade-chart', 'figure'),
             Output('selected-trade-info', 'children')],
            [Input('trade-table', 'selected_rows'),
             Input('trade-table', 'data')]
        )
        def update_trade_chart(selected_rows, table_data):
            """Update chart when trade is selected"""
            if not selected_rows or not table_data:
                # Show empty chart with message
                fig = go.Figure()
                fig.add_annotation(
                    text="Select a trade from the table to view its chart",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(size=20, color="#7f8c8d")
                )
                fig.update_layout(
                    template='plotly_white',
                    height=800
                )
                return fig, ""

            # Get selected trade
            selected_idx = selected_rows[0]
            row_data = table_data[selected_idx]
            trade_idx = row_data['trade_index']
            trade = self.trades[trade_idx]

            # Create chart for this specific trade
            fig = self._create_single_trade_chart(trade)

            # Create trade info panel
            entry_time = pd.to_datetime(trade['entry_time'], unit='ms')
            exit_time = pd.to_datetime(trade['exit_time'], unit='ms')
            duration = exit_time - entry_time

            info_panel = html.Div([
                html.H4(f"Trade #{selected_idx + 1} Details", style={'color': '#2c3e50'}),
                html.P([
                    html.Strong("Direction: "), f"{trade['direction']} ({trade['signal']['signal_type']})", html.Br(),
                    html.Strong("Entry: "), f"${trade['entry_price']:,.2f} at {entry_time.strftime('%Y-%m-%d %H:%M')}", html.Br(),
                    html.Strong("Exit: "), f"${trade['exit_price']:,.2f} at {exit_time.strftime('%Y-%m-%d %H:%M')} ({trade['exit_reason']})", html.Br(),
                    html.Strong("Duration: "), f"{duration}", html.Br(),
                    html.Strong("P&L: "), f"${trade['pnl']:,.2f} ({trade['pnl_pct']:+.2f}%)", html.Br(),
                    html.Strong("Reason: "), trade['signal']['reason'], html.Br(),
                ], style={'fontSize': '14px'})
            ], style={'backgroundColor': '#ecf0f1', 'padding': '15px', 'borderRadius': '5px'})

            return fig, info_panel

    def _filter_trades(self, outcome: str, direction: str, signal_type: str) -> List[Dict]:
        """Filter trades based on criteria"""
        filtered = self.trades.copy()

        if outcome != 'all':
            filtered = [t for t in filtered if (t['pnl'] > 0) == (outcome == 'win')]

        if direction != 'all':
            filtered = [t for t in filtered if t['direction'] == direction]

        if signal_type != 'all':
            filtered = [t for t in filtered if t['signal']['signal_type'] == signal_type]

        return filtered

    def _create_single_trade_chart(self, trade: Dict) -> go.Figure:
        """
        Create chart showing only context for this specific trade

        Shows:
        - Candlesticks for ±30 minutes around trade
        - VWAP bands at trade time
        - Only S/R zones that contributed to this trade's decision
        - Entry/exit markers for this trade only
        """
        entry_time = pd.to_datetime(trade['entry_time'], unit='ms')
        exit_time = pd.to_datetime(trade['exit_time'], unit='ms')

        # Get time window: 30 min before entry to 30 min after exit
        start_time = entry_time - timedelta(minutes=30)
        end_time = exit_time + timedelta(minutes=30)

        # Filter data to window
        mask = (self.df['timestamp'] >= start_time) & (self.df['timestamp'] <= end_time)
        window_df = self.df[mask].copy()

        if len(window_df) == 0:
            # Fallback to wider window
            mask = (self.df['timestamp'] >= entry_time - timedelta(hours=1)) & \
                   (self.df['timestamp'] <= exit_time + timedelta(hours=1))
            window_df = self.df[mask].copy()

        # Create figure with subplots
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            subplot_titles=(f'{trade["direction"]} Trade - {entry_time.strftime("%Y-%m-%d %H:%M")}', 'Volume'),
            row_heights=[0.75, 0.25]
        )

        # Add candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=window_df['timestamp'],
                open=window_df['open'],
                high=window_df['high'],
                low=window_df['low'],
                close=window_df['close'],
                name='Price',
                increasing_line_color='#26a69a',
                decreasing_line_color='#ef5350'
            ),
            row=1, col=1
        )

        # Add VWAP bands for this session
        self._add_vwap_bands_to_chart(fig, window_df)

        # Add S/R zone that contributed to this trade
        if 'sr_zone' in trade['signal'] and trade['signal']['sr_zone']:
            zone = trade['signal']['sr_zone']
            color = 'rgba(76, 175, 80, 0.2)' if zone['zone_type'] in ['support', 'both'] else 'rgba(244, 67, 54, 0.2)'

            fig.add_hrect(
                y0=zone['lower'],
                y1=zone['upper'],
                fillcolor=color,
                line=dict(color=color.replace('0.2', '0.8'), width=2, dash='dash'),
                row=1, col=1
            )

            # Add zone label
            fig.add_annotation(
                x=window_df['timestamp'].iloc[len(window_df)//2],
                y=zone['level'],
                text=f"S/R {zone['timeframe']}<br>Strength: {zone['strength']}",
                showarrow=False,
                font=dict(size=10, color='white'),
                bgcolor=color.replace('0.2', '0.7'),
                bordercolor=color.replace('0.2', '1.0'),
                borderwidth=2,
                row=1, col=1
            )

        # Add entry marker
        marker_color = '#26a69a' if trade['direction'] == 'LONG' else '#ef5350'
        marker_symbol = 'triangle-up' if trade['direction'] == 'LONG' else 'triangle-down'

        fig.add_trace(
            go.Scatter(
                x=[entry_time],
                y=[trade['entry_price']],
                mode='markers+text',
                name='Entry',
                marker=dict(
                    symbol=marker_symbol,
                    size=15,
                    color=marker_color,
                    line=dict(color='white', width=2)
                ),
                text=['ENTRY'],
                textposition='top center',
                textfont=dict(size=12, color=marker_color)
            ),
            row=1, col=1
        )

        # Add exit marker
        exit_color = '#66bb6a' if trade['pnl'] > 0 else '#ff7043'

        fig.add_trace(
            go.Scatter(
                x=[exit_time],
                y=[trade['exit_price']],
                mode='markers+text',
                name='Exit',
                marker=dict(
                    symbol='x',
                    size=15,
                    color=exit_color,
                    line=dict(width=3)
                ),
                text=[f"EXIT<br>{trade['exit_reason']}"],
                textposition='top center',
                textfont=dict(size=12, color=exit_color)
            ),
            row=1, col=1
        )

        # Add volume bars
        colors = ['#26a69a' if close >= open_price else '#ef5350'
                  for close, open_price in zip(window_df['close'], window_df['open'])]

        fig.add_trace(
            go.Bar(
                x=window_df['timestamp'],
                y=window_df['volume'],
                name='Volume',
                marker_color=colors,
                showlegend=False
            ),
            row=2, col=1
        )

        # Update layout
        pnl_color = '#27ae60' if trade['pnl'] > 0 else '#e74c3c'
        fig.update_layout(
            title=dict(
                text=f"{trade['direction']} {trade['signal']['signal_type'].replace('_', ' ').title()}<br>" +
                     f"<sub>P&L: ${trade['pnl']:,.2f} ({trade['pnl_pct']:+.2f}%) | " +
                     f"Confidence: {trade['signal']['confidence']:.0f}</sub>",
                x=0.5,
                xanchor='center'
            ),
            xaxis_rangeslider_visible=False,
            xaxis2_title='Time',
            yaxis_title='Price (USDT)',
            yaxis2_title='Volume',
            hovermode='x unified',
            height=800,
            template='plotly_white',
            showlegend=True
        )

        return fig

    def _add_vwap_bands_to_chart(self, fig, df):
        """Add VWAP bands to the chart"""
        if len(df) == 0:
            return

        # Calculate session-based VWAP for the window
        df_copy = df.copy()
        df_copy['date'] = df_copy['timestamp'].dt.date

        vwap_data = []
        upper_1std_data = []
        lower_1std_data = []

        for date in df_copy['date'].unique():
            session_df = df_copy[df_copy['date'] == date].copy()

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

        # Add VWAP line
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
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
                x=df['timestamp'],
                y=upper_1std_data,
                name='+1σ',
                line=dict(color='#42a5f5', width=1, dash='dash'),
                mode='lines',
                showlegend=True
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=lower_1std_data,
                name='-1σ',
                line=dict(color='#42a5f5', width=1, dash='dash'),
                mode='lines',
                fill='tonexty',
                fillcolor='rgba(66, 165, 245, 0.1)',
                showlegend=True
            ),
            row=1, col=1
        )

    def run(self, port: int = 8050, debug: bool = False, open_browser: bool = True):
        """Run the dashboard server"""
        def open_browser_delayed():
            webbrowser.open(f'http://127.0.0.1:{port}/')

        if open_browser:
            Timer(1.5, open_browser_delayed).start()

        print(f"\n[DASHBOARD] Starting interactive dashboard...")
        print(f"[DASHBOARD] Open in browser: http://127.0.0.1:{port}/")
        print(f"[DASHBOARD] Press Ctrl+C to stop the server\n")

        self.app.run_server(debug=debug, port=port, host='127.0.0.1')
