"""
VWAP + S/R Strategy - Interactive Dashboard
============================================

Comprehensive dashboard for analyzing VWAP + S/R strategy backtest results with:
- Day of Week Analysis (stacked bars + win rates)
- Equity Curve & Drawdown charts
- Daily P&L Table (clickable for filtering)
- Trade Filtering (Outcome, Direction, Signal Type)
- Trade List (clickable to view candlestick chart with VWAP bands)
- ML Performance Metrics (confidence, success probability)
- Zone Quality Analysis
- VWAP Band Analysis

Runs on: http://localhost:8050
"""

import dash
from dash import dcc, html, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from pathlib import Path
from binance.client import Client

# Initialize Dash app with Bootstrap theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY], suppress_callback_exceptions=True)
app.title = "VWAP + S/R Strategy Dashboard"

# Global data storage
TRADES_DATA = None
DAILY_DATA = None

# Initialize Binance client for fetching candle data
try:
    binance_client = Client()  # Public API, no keys needed for historical data
except Exception as e:
    print(f"Warning: Could not initialize Binance client: {e}")
    binance_client = None

def fetch_candles_for_trade(symbol, timestamp, bars_before=50, bars_after=10, interval='1m'):
    """
    Fetch candlestick data around a trade entry point

    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        timestamp: Trade entry timestamp
        bars_before: Number of candles before entry
        bars_after: Number of candles after entry
        interval: Candle interval (default: 1m)

    Returns:
        DataFrame with OHLCV data or None if fetch fails
    """
    if not binance_client:
        return None

    try:
        # Parse timestamp
        if isinstance(timestamp, str):
            entry_time = pd.to_datetime(timestamp)
        else:
            entry_time = timestamp

        # Calculate time range
        if interval == '1m':
            time_per_candle = timedelta(minutes=1)
        elif interval == '5m':
            time_per_candle = timedelta(minutes=5)
        elif interval == '15m':
            time_per_candle = timedelta(minutes=15)
        else:
            time_per_candle = timedelta(minutes=1)

        start_time = entry_time - (bars_before * time_per_candle)
        end_time = entry_time + (bars_after * time_per_candle)

        # Fetch candles from Binance
        klines = binance_client.get_historical_klines(
            symbol,
            interval,
            start_str=start_time.strftime('%Y-%m-%d %H:%M:%S'),
            end_str=end_time.strftime('%Y-%m-%d %H:%M:%S')
        )

        # Convert to DataFrame
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

    except Exception as e:
        print(f"Error fetching candles: {e}")
        return None

def load_backtest_data():
    """Load backtest results from outputs directory"""
    try:
        script_dir = Path(__file__).parent
        outputs_dir = script_dir / 'outputs'

        # Try latest detailed results first
        latest_results_path = outputs_dir / 'latest_backtest_results.json'
        if latest_results_path.exists():
            with open(latest_results_path, 'r') as f:
                data = json.load(f)
            print(f"✓ Loaded backtest data from: {latest_results_path}")
            return data

        # Fallback to trade_history.json
        trade_history_path = outputs_dir / 'trade_history.json'
        if trade_history_path.exists():
            with open(trade_history_path, 'r') as f:
                trades = json.load(f)
            print(f"✓ Loaded trade history from: {trade_history_path}")
            return {'trades': trades, 'results': None}

        # Try ML training data as fallback
        ml_data_path = script_dir / 'data' / 'training_data.csv'
        if ml_data_path.exists():
            df = pd.read_csv(ml_data_path)
            trades = df.to_dict('records')
            print(f"✓ Loaded ML training data from: {ml_data_path}")
            return {'trades': trades, 'results': None}

        print(f"❌ No backtest data found in: {outputs_dir}")
        return None
    except Exception as e:
        print(f"Error loading data: {e}")
        return None

def prepare_daily_data(trades):
    """Prepare daily summary data"""
    if not trades:
        return pd.DataFrame()

    df = pd.DataFrame(trades)

    # Normalize column names
    pnl_col = 'pnl_pct' if 'pnl_pct' in df.columns else 'pnl_percent'
    if pnl_col not in df.columns:
        return pd.DataFrame()

    # Parse timestamps
    timestamp_col = 'timestamp' if 'timestamp' in df.columns else 'entry_time'
    df['datetime'] = pd.to_datetime(df[timestamp_col])
    df['date'] = df['datetime'].dt.date

    # Calculate daily stats
    daily = df.groupby('date').agg({
        pnl_col: ['sum', 'count']
    }).reset_index()

    daily.columns = ['date', 'total_pnl', 'trades']

    # Calculate wins and losses per day
    wins_per_day = df[df[pnl_col] > 0].groupby('date').size().reset_index(name='wins')
    losses_per_day = df[df[pnl_col] <= 0].groupby('date').size().reset_index(name='losses')

    daily = daily.merge(wins_per_day, on='date', how='left')
    daily = daily.merge(losses_per_day, on='date', how='left')

    daily['wins'] = daily['wins'].fillna(0).astype(int)
    daily['losses'] = daily['losses'].fillna(0).astype(int)
    daily['win_rate'] = (daily['wins'] / daily['trades'] * 100).round(1)

    # Convert total_pnl to percentage for display
    daily['total_pnl'] = daily['total_pnl'] * 100

    return daily

def create_header_metrics(trades):
    """Create header with key metrics"""
    if not trades:
        return html.Div("No data", className="text-center p-5")

    total_trades = len(trades)

    # Determine P&L column
    pnl_col = 'pnl_pct' if 'pnl_pct' in trades[0] else 'pnl_percent'
    is_win_col = 'is_win' if 'is_win' in trades[0] else None

    # Calculate wins
    if is_win_col:
        wins = len([t for t in trades if t.get(is_win_col, False)])
    else:
        wins = len([t for t in trades if t.get(pnl_col, 0) > 0])

    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    # Calculate P&L
    total_pnl_pct = sum([t.get(pnl_col, 0) for t in trades]) * 100

    # Color code
    pnl_color = "text-success" if total_pnl_pct > 0 else "text-danger"
    wr_color = "text-success" if win_rate >= 60 else "text-warning" if win_rate >= 50 else "text-danger"

    # ML stats (if available)
    ml_approved = len([t for t in trades if t.get('ml_approved', True)])  # Default to True if not present
    ml_confidence_avg = np.mean([t.get('ml_confidence', 0) for t in trades if 'ml_confidence' in t])

    return dbc.Row([
        dbc.Col([
            html.Div([
                html.Span("Win Rate: ", style={'fontSize': '18px'}),
                html.Span(f"{win_rate:.1f}%", className=wr_color, style={'fontSize': '18px', 'fontWeight': 'bold'})
            ])
        ], width=3, className="text-center"),
        dbc.Col([
            html.Div([
                html.Span("Total Trades: ", style={'fontSize': '18px'}),
                html.Span(f"{total_trades}", className="text-primary", style={'fontSize': '18px', 'fontWeight': 'bold'})
            ])
        ], width=3, className="text-center"),
        dbc.Col([
            html.Div([
                html.Span("Net P&L: ", style={'fontSize': '18px'}),
                html.Span(f"{total_pnl_pct:+.2f}%",
                         className=pnl_color, style={'fontSize': '18px', 'fontWeight': 'bold'})
            ])
        ], width=3, className="text-center"),
        dbc.Col([
            html.Div([
                html.Span("ML Approved: ", style={'fontSize': '18px'}),
                html.Span(f"{ml_approved}/{total_trades} ({ml_approved/total_trades*100:.0f}%)",
                         className="text-info", style={'fontSize': '18px', 'fontWeight': 'bold'})
            ])
        ], width=3, className="text-center")
    ], className="p-3", style={'backgroundColor': '#f8f9fa', 'borderRadius': '5px'})

def create_day_of_week_charts(trades):
    """Create day of week analysis charts"""
    if not trades:
        return html.Div("No data")

    df = pd.DataFrame(trades)

    # Normalize column names
    pnl_col = 'pnl_pct' if 'pnl_pct' in df.columns else 'pnl_percent'
    timestamp_col = 'timestamp' if 'timestamp' in df.columns else 'entry_time'

    df['datetime'] = pd.to_datetime(df[timestamp_col])
    df['dayofweek'] = df['datetime'].dt.dayofweek
    df['dayname'] = df['datetime'].dt.day_name()
    df['is_win'] = df[pnl_col] > 0

    # Day order
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Trades by day (stacked)
    day_stats = []
    for day in day_order:
        day_trades = df[df['dayname'] == day]
        wins = len(day_trades[day_trades['is_win']])
        losses = len(day_trades) - wins
        day_stats.append({'day': day, 'wins': wins, 'losses': losses})

    day_df = pd.DataFrame(day_stats)

    fig_trades = go.Figure()
    fig_trades.add_trace(go.Bar(
        name='Wins',
        x=day_df['day'],
        y=day_df['wins'],
        marker_color='#28a745',
        text=day_df['wins'],
        textposition='inside'
    ))
    fig_trades.add_trace(go.Bar(
        name='Losses',
        x=day_df['day'],
        y=day_df['losses'],
        marker_color='#dc3545',
        text=day_df['losses'],
        textposition='inside'
    ))

    fig_trades.update_layout(
        title='Trades by Day of Week',
        xaxis_title='Day',
        yaxis_title='Number of Trades',
        barmode='stack',
        height=350,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        template='simple_white'
    )

    # Win rate by day
    day_wr = []
    for day in day_order:
        day_trades = df[df['dayname'] == day]
        if len(day_trades) > 0:
            wr = (day_trades['is_win'].sum() / len(day_trades)) * 100
        else:
            wr = 0
        day_wr.append({'day': day, 'win_rate': wr})

    wr_df = pd.DataFrame(day_wr)

    # Color bars based on win rate
    colors = ['#28a745' if wr >= 50 else '#dc3545' for wr in wr_df['win_rate']]

    fig_wr = go.Figure()
    fig_wr.add_trace(go.Bar(
        x=wr_df['day'],
        y=wr_df['win_rate'],
        marker_color=colors,
        text=[f"{wr:.1f}%" for wr in wr_df['win_rate']],
        textposition='inside'
    ))

    # Add 50% breakeven line
    fig_wr.add_hline(y=50, line_dash="dash", line_color="gray",
                     annotation_text="50% Breakeven", annotation_position="top right")

    fig_wr.update_layout(
        title='Win Rate by Day of Week',
        xaxis_title='Day',
        yaxis_title='Win Rate (%)',
        height=350,
        template='simple_white',
        yaxis=dict(range=[0, 105])
    )

    return dbc.Row([
        dbc.Col([dcc.Graph(figure=fig_trades)], width=6),
        dbc.Col([dcc.Graph(figure=fig_wr)], width=6)
    ])

def create_equity_drawdown_chart(trades):
    """Create equity curve and drawdown chart"""
    if not trades:
        return html.Div("No data")

    df = pd.DataFrame(trades)

    # Normalize column names
    pnl_col = 'pnl_pct' if 'pnl_pct' in df.columns else 'pnl_percent'

    df['cumulative_pnl'] = df[pnl_col].cumsum()
    df['equity'] = 100 * (1 + df['cumulative_pnl'])

    # Calculate drawdown
    df['running_max'] = df['equity'].cummax()
    df['drawdown'] = ((df['equity'] - df['running_max']) / df['running_max']) * 100

    # Find max drawdown point
    max_dd_idx = df['drawdown'].idxmin()
    max_dd_value = df.loc[max_dd_idx, 'drawdown']

    # Find max profit point
    max_profit_idx = df['equity'].idxmax()
    max_profit_value = df.loc[max_profit_idx, 'equity']

    # Create subplot
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('Equity Curve', 'Drawdown'),
        vertical_spacing=0.15,
        row_heights=[0.6, 0.4]
    )

    # Equity curve
    fig.add_trace(
        go.Scatter(
            x=list(range(len(df))),
            y=df['equity'],
            mode='lines',
            name='Equity',
            line=dict(color='#17a2b8', width=2),
            fill='tozeroy',
            fillcolor='rgba(23, 162, 184, 0.2)'
        ),
        row=1, col=1
    )

    # Add initial capital line
    fig.add_hline(y=100, line_dash="dash", line_color="gray", row=1, col=1,
                  annotation_text=f"Initial: $100", annotation_position="right")

    # Mark max drawdown
    fig.add_trace(
        go.Scatter(
            x=[max_dd_idx],
            y=[df.loc[max_dd_idx, 'equity']],
            mode='markers+text',
            name='Max Drawdown',
            marker=dict(color='red', size=12, symbol='diamond'),
            text=["Max DD"],
            textposition="top center",
            showlegend=True
        ),
        row=1, col=1
    )

    # Mark max profit
    fig.add_trace(
        go.Scatter(
            x=[max_profit_idx],
            y=[max_profit_value],
            mode='markers+text',
            name='Max Profit',
            marker=dict(color='green', size=12, symbol='star'),
            text=["Max Profit"],
            textposition="top center",
            showlegend=True
        ),
        row=1, col=1
    )

    # Drawdown
    fig.add_trace(
        go.Scatter(
            x=list(range(len(df))),
            y=df['drawdown'],
            mode='lines',
            name='Drawdown',
            line=dict(color='#dc3545', width=2),
            fill='tozeroy',
            fillcolor='rgba(220, 53, 69, 0.2)'
        ),
        row=2, col=1
    )

    # Mark max drawdown point
    fig.add_trace(
        go.Scatter(
            x=[max_dd_idx],
            y=[max_dd_value],
            mode='markers+text',
            marker=dict(color='darkred', size=12, symbol='diamond'),
            text=[f"Max DD: {max_dd_value:.2f}%"],
            textposition="bottom center",
            showlegend=False
        ),
        row=2, col=1
    )

    fig.update_xaxes(title_text="Trade Number", row=2, col=1)
    fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)

    fig.update_layout(
        height=600,
        template='simple_white',
        legend=dict(orientation='h', yanchor='top', y=-0.15, xanchor='center', x=0.5)
    )

    return dcc.Graph(figure=fig)

def create_daily_pnl_table(daily_df):
    """Create daily P&L table"""
    if daily_df.empty:
        return html.Div("No data")

    # Format for display
    daily_display = daily_df.copy()
    daily_display['date'] = daily_display['date'].astype(str)
    daily_display['total_pnl'] = daily_display['total_pnl'].round(2)

    return dash_table.DataTable(
        id='daily-pnl-table',
        columns=[
            {'name': 'Date', 'id': 'date'},
            {'name': 'Total P&L (%)', 'id': 'total_pnl', 'type': 'numeric'},
            {'name': 'Trades', 'id': 'trades'},
            {'name': 'Wins', 'id': 'wins'},
            {'name': 'Losses', 'id': 'losses'},
            {'name': 'Win Rate (%)', 'id': 'win_rate', 'type': 'numeric'}
        ],
        data=daily_display.to_dict('records'),
        style_cell={
            'textAlign': 'center',
            'padding': '10px',
            'fontSize': '14px'
        },
        style_header={
            'backgroundColor': '#343a40',
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign': 'center'
        },
        style_data_conditional=[
            {
                'if': {'filter_query': '{total_pnl} > 0'},
                'backgroundColor': '#d4edda',
                'color': '#155724'
            },
            {
                'if': {'filter_query': '{total_pnl} < 0'},
                'backgroundColor': '#f8d7da',
                'color': '#721c24'
            }
        ],
        row_selectable='single',
        selected_rows=[],
        page_action='none',
        style_table={'height': '400px', 'overflowY': 'auto'}
    )

def create_trade_table(trades, outcome_filter='all', direction_filter='all'):
    """Create trade list table"""
    if not trades:
        return html.Div("No trades")

    df = pd.DataFrame(trades)

    # Normalize column names
    pnl_col = 'pnl_pct' if 'pnl_pct' in df.columns else 'pnl_percent'
    timestamp_col = 'timestamp' if 'timestamp' in df.columns else 'entry_time'
    signal_col = 'signal_type' if 'signal_type' in df.columns else 'direction'

    # Apply filters
    if outcome_filter == 'win':
        df = df[df[pnl_col] > 0]
    elif outcome_filter == 'loss':
        df = df[df[pnl_col] <= 0]

    if direction_filter != 'all':
        df = df[df[signal_col] == direction_filter]

    if df.empty:
        return html.Div("No trades match filters")

    # Prepare display data
    df['trade_num'] = range(1, len(df) + 1)
    df['pnl_display'] = (df[pnl_col] * 100).round(2)

    # Format entry time
    df['entry_time_fmt'] = pd.to_datetime(df[timestamp_col]).dt.strftime('%Y-%m-%d %H:%M')

    # Create reason string
    df['reason'] = df.apply(lambda row:
        f"{row.get(signal_col, 'N/A')} | VWAP Dist: {row.get('vwap_distance', 0)*100:.2f}% | Zone: {row.get('zone_strength', 'N/A')}",
        axis=1
    )

    display_df = df[['trade_num', signal_col, 'entry_time_fmt', 'entry_price',
                      'exit_price', 'pnl_display', 'reason']].copy()

    display_df.columns = ['#', 'Type', 'Entry Time', 'Entry Price',
                          'Exit Price', 'P&L %', 'Reason']

    return dash_table.DataTable(
        id='trade-list-table',
        columns=[{'name': col, 'id': col} for col in display_df.columns],
        data=display_df.to_dict('records'),
        style_cell={
            'textAlign': 'left',
            'padding': '8px',
            'fontSize': '13px',
            'whiteSpace': 'normal',
            'height': 'auto'
        },
        style_header={
            'backgroundColor': '#343a40',
            'color': 'white',
            'fontWeight': 'bold'
        },
        style_data_conditional=[
            {
                'if': {'filter_query': '{P&L %} > 0', 'column_id': 'P&L %'},
                'color': '#28a745',
                'fontWeight': 'bold'
            },
            {
                'if': {'filter_query': '{P&L %} < 0', 'column_id': 'P&L %'},
                'color': '#dc3545',
                'fontWeight': 'bold'
            },
            {
                'if': {'column_id': '#'},
                'width': '50px'
            }
        ],
        row_selectable='single',
        selected_rows=[],
        page_size=10,
        style_table={'overflowX': 'auto'}
    )

def create_ml_analysis(trades):
    """Create ML performance analysis"""
    if not trades:
        return html.Div("No data")

    # Check if ML data is available
    ml_trades = [t for t in trades if 'ml_confidence' in t or 'success_probability' in t]

    if not ml_trades:
        return dbc.Alert([
            html.H5("ℹ️ ML Data Not Available"),
            html.P("ML metrics will be shown here after training and running the ML-enhanced strategy."),
            html.P("To enable ML:"),
            html.Ol([
                html.Li("Collect training data: python ml_training_data_collector.py --days 30"),
                html.Li("Train model: python train_ml_model.py --input data.csv --output model.pkl"),
                html.Li("Run backtest with ML enabled")
            ])
        ], color="info")

    # ML stats
    df = pd.DataFrame(ml_trades)
    pnl_col = 'pnl_pct' if 'pnl_pct' in df.columns else 'pnl_percent'

    wins = df[df[pnl_col] > 0]
    losses = df[df[pnl_col] <= 0]

    # Average confidence scores
    avg_win_conf = wins['ml_confidence'].mean() if 'ml_confidence' in wins.columns and len(wins) > 0 else 0
    avg_loss_conf = losses['ml_confidence'].mean() if 'ml_confidence' in losses.columns and len(losses) > 0 else 0

    # Average success probability
    avg_win_prob = wins['success_probability'].mean() if 'success_probability' in wins.columns and len(wins) > 0 else 0
    avg_loss_prob = losses['success_probability'].mean() if 'success_probability' in losses.columns and len(losses) > 0 else 0

    # Stats cards
    stats_cards = dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("Avg ML Confidence (Wins)", className="card-subtitle text-muted"),
                    html.H3(f"{avg_win_conf:.1%}", className="card-title text-success")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("Avg ML Confidence (Losses)", className="card-subtitle text-muted"),
                    html.H3(f"{avg_loss_conf:.1%}", className="card-title text-danger")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("Avg Success Prob (Wins)", className="card-subtitle text-muted"),
                    html.H3(f"{avg_win_prob:.1%}", className="card-title text-success")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("Avg Success Prob (Losses)", className="card-subtitle text-muted"),
                    html.H3(f"{avg_loss_prob:.1%}", className="card-title text-danger")
                ])
            ])
        ], width=3)
    ], className="mb-4")

    # ML Confidence Distribution
    if 'ml_confidence' in df.columns:
        win_confidences = wins['ml_confidence'].tolist() if len(wins) > 0 else []
        loss_confidences = losses['ml_confidence'].tolist() if len(losses) > 0 else []

        fig_confidence = go.Figure()

        fig_confidence.add_trace(go.Histogram(
            x=win_confidences,
            name='Winning Trades',
            marker_color='#28a745',
            opacity=0.7,
            nbinsx=20
        ))

        fig_confidence.add_trace(go.Histogram(
            x=loss_confidences,
            name='Losing Trades',
            marker_color='#dc3545',
            opacity=0.7,
            nbinsx=20
        ))

        fig_confidence.update_layout(
            title="ML Confidence Score Distribution",
            xaxis_title="Confidence Score",
            yaxis_title="Number of Trades",
            barmode='overlay',
            height=350,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        return html.Div([stats_cards, dcc.Graph(figure=fig_confidence)])
    else:
        return stats_cards

# Layout
app.layout = dbc.Container([
    html.H2("VWAP + S/R Strategy - Backtest Dashboard",
            className="text-center mt-3 mb-4", style={'color': '#343a40'}),

    # Hidden stores
    dcc.Store(id='trades-store'),
    dcc.Store(id='selected-date-store'),

    # Header metrics
    html.Div(id='header-metrics', className="mb-4"),

    html.Hr(),

    # Day of Week Analysis
    html.Div([
        html.H4("Day of Week Analysis", className="mb-3"),
        html.P("Performance breakdown by day of the week", className="text-muted"),
        html.Div(id='day-of-week-charts')
    ], className="mb-4 p-3", style={'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),

    html.Hr(),

    # Equity & Drawdown
    html.Div([
        html.H4("Equity Curve & Drawdown", className="mb-3"),
        html.P("Track account balance progression and maximum drawdown over time", className="text-muted"),
        html.Div(id='equity-drawdown-chart')
    ], className="mb-4 p-3", style={'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),

    html.Hr(),

    # Daily P&L Analysis
    html.Div([
        html.H4("Daily P&L Analysis", className="mb-3"),
        html.P("Click a row to filter trades to that day.", className="text-muted"),
        html.Div(id='daily-pnl-table-container')
    ], className="mb-4 p-3", style={'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),

    html.Div(id='date-filter-info', className="mb-3"),

    html.Hr(),

    # ML Analysis
    html.Div([
        html.H4("🤖 ML Performance Analysis", className="mb-3"),
        html.P("ML model confidence and success probability metrics", className="text-muted"),
        html.Div(id='ml-analysis')
    ], className="mb-4 p-3", style={'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),

    html.Hr(),

    # Filter Trades
    html.Div([
        html.H4("Filter Trades", className="mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Outcome:", className="font-weight-bold"),
                dcc.Dropdown(
                    id='outcome-filter',
                    options=[
                        {'label': 'All Trades', 'value': 'all'},
                        {'label': 'Winners', 'value': 'win'},
                        {'label': 'Losers', 'value': 'loss'}
                    ],
                    value='all',
                    clearable=False
                )
            ], width=6),
            dbc.Col([
                html.Label("Direction:", className="font-weight-bold"),
                dcc.Dropdown(
                    id='direction-filter',
                    options=[
                        {'label': 'All', 'value': 'all'},
                        {'label': 'LONG', 'value': 'LONG'},
                        {'label': 'SHORT', 'value': 'SHORT'}
                    ],
                    value='all',
                    clearable=False
                )
            ], width=6)
        ])
    ], className="mb-4 p-3", style={'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),

    html.Hr(),

    # Trade List
    html.Div([
        html.H4("Trade List (Click to View Chart)", className="mb-3"),
        html.P(id='trade-count-text'),
        html.Div(id='trade-table-container')
    ], className="mb-4 p-3", style={'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),

    # Trade Details (shown when trade selected)
    html.Div(id='trade-details-container', className="mb-4")

], fluid=True, style={'backgroundColor': '#ffffff'})

# Callbacks
@app.callback(
    [Output('trades-store', 'data'),
     Output('header-metrics', 'children'),
     Output('day-of-week-charts', 'children'),
     Output('equity-drawdown-chart', 'children'),
     Output('daily-pnl-table-container', 'children'),
     Output('ml-analysis', 'children')],
    Input('trades-store', 'data')
)
def load_initial_data(_):
    """Load data on startup"""
    data = load_backtest_data()

    if not data:
        no_data = html.Div([
            html.H4("No Backtest Data Found", className="text-center text-danger mt-5"),
            html.P("Please run a backtest or collect ML training data first:", className="text-center"),
            html.Code("python ml_training_data_collector.py --days 7", className="d-block text-center mb-2"),
            html.P("Then refresh this page.", className="text-center text-muted")
        ])
        return None, no_data, no_data, no_data, no_data, no_data

    # Extract trades
    trades = data.get('trades', data) if isinstance(data, dict) else data

    # Prepare daily data
    daily_df = prepare_daily_data(trades)

    return (
        trades,
        create_header_metrics(trades),
        create_day_of_week_charts(trades),
        create_equity_drawdown_chart(trades),
        create_daily_pnl_table(daily_df),
        create_ml_analysis(trades)
    )

@app.callback(
    [Output('selected-date-store', 'data'),
     Output('date-filter-info', 'children')],
    Input('daily-pnl-table', 'selected_rows'),
    State('daily-pnl-table', 'data')
)
def handle_date_selection(selected_rows, table_data):
    """Handle daily table row selection"""
    if not selected_rows or not table_data:
        return None, ""

    selected_date = table_data[selected_rows[0]]['date']

    info = dbc.Alert([
        html.Strong("📅 Filtering trades for: "),
        html.Span(selected_date),
        html.Button("Clear Filter", id='clear-date-filter',
                   className="btn btn-sm btn-outline-secondary ml-3", n_clicks=0)
    ], color="info", className="d-flex align-items-center justify-content-between")

    return selected_date, info

@app.callback(
    Output('selected-date-store', 'data', allow_duplicate=True),
    Input('clear-date-filter', 'n_clicks'),
    prevent_initial_call=True
)
def clear_date_filter(n_clicks):
    """Clear date filter"""
    if n_clicks:
        return None
    return None

@app.callback(
    [Output('trade-table-container', 'children'),
     Output('trade-count-text', 'children')],
    [Input('trades-store', 'data'),
     Input('outcome-filter', 'value'),
     Input('direction-filter', 'value'),
     Input('selected-date-store', 'data')]
)
def update_trade_table(trades, outcome, direction, selected_date):
    """Update trade table based on filters"""
    if not trades:
        return html.Div("No trades"), "0 trades"

    # Apply date filter
    if selected_date:
        df = pd.DataFrame(trades)
        timestamp_col = 'timestamp' if 'timestamp' in df.columns else 'entry_time'
        df['date'] = pd.to_datetime(df[timestamp_col]).dt.date.astype(str)
        trades = df[df['date'] == selected_date].to_dict('records')

    table = create_trade_table(trades, outcome, direction)

    # Count trades after filtering
    count_text = f"Showing {len(trades)} trades"

    return table, count_text

@app.callback(
    Output('trade-details-container', 'children'),
    [Input('trade-list-table', 'selected_rows'),
     Input('trades-store', 'data')],
    [State('outcome-filter', 'value'),
     State('direction-filter', 'value'),
     State('selected-date-store', 'data')]
)
def show_trade_details(selected_rows, trades, outcome, direction, selected_date):
    """Show trade details when selected"""
    if not selected_rows or not trades:
        return html.Div()

    # Apply same filters
    df = pd.DataFrame(trades)
    pnl_col = 'pnl_pct' if 'pnl_pct' in df.columns else 'pnl_percent'
    timestamp_col = 'timestamp' if 'timestamp' in df.columns else 'entry_time'

    if selected_date:
        df['date'] = pd.to_datetime(df[timestamp_col]).dt.date.astype(str)
        df = df[df['date'] == selected_date]

    if outcome == 'win':
        df = df[df[pnl_col] > 0]
    elif outcome == 'loss':
        df = df[df[pnl_col] <= 0]

    signal_col = 'signal_type' if 'signal_type' in df.columns else 'direction'
    if direction != 'all':
        df = df[df[signal_col] == direction]

    if df.empty or selected_rows[0] >= len(df):
        return html.Div()

    trade = df.iloc[selected_rows[0]].to_dict()

    # Trade details card
    details_card = dbc.Card([
        dbc.CardHeader(html.H4(f"Trade #{selected_rows[0] + 1} Details")),
        dbc.CardBody([
            html.P([
                html.Strong("Type: "),
                html.Span(f"{trade.get(signal_col, 'N/A')}", className="text-primary")
            ]),
            html.P([
                html.Strong("Entry: "),
                f"${trade['entry_price']:,.2f} at ",
                pd.to_datetime(trade.get(timestamp_col, pd.Timestamp.now())).strftime('%Y-%m-%d %H:%M')
            ]),
            html.P([
                html.Strong("Exit: "),
                f"${trade.get('exit_price', 0):,.2f}"
            ]),
            html.P([
                html.Strong("P&L: "),
                html.Span(f"{trade.get(pnl_col, 0)*100:.2f}%",
                         className="text-success" if trade.get(pnl_col, 0) > 0 else "text-danger",
                         style={'fontSize': '16px', 'fontWeight': 'bold'})
            ]),
            html.Hr(),
            html.H6("VWAP & Zone Features:", className="text-muted"),
            html.P([
                html.Strong("VWAP Distance: "), f"{trade.get('vwap_distance', 0)*100:.2f}% | ",
                html.Strong("Band Position: "), f"{trade.get('vwap_band_position', 0):.2f} | ",
                html.Strong("Zone Strength: "), f"{trade.get('zone_strength', 0):.1f}"
            ]),
            html.P([
                html.Strong("Zone Bounces: "), f"{trade.get('zone_bounces', 0)} | ",
                html.Strong("Zone Touches: "), f"{trade.get('zone_touches', 0)} | ",
                html.Strong("Liquidity Grabs: "), f"{trade.get('zone_liquidity_grabs', 0)}"
            ]),
            html.Hr(),
            html.H6("ML Prediction:", className="text-muted"),
            html.P([
                html.Strong("Confidence: "), f"{trade.get('ml_confidence', 0):.1%} | ",
                html.Strong("Success Probability: "), f"{trade.get('success_probability', 0):.1%} | ",
                html.Strong("ML Approved: "), "Yes" if trade.get('ml_approved', True) else "No"
            ])
        ])
    ], className="mb-3")

    return details_card

if __name__ == '__main__':
    print("="*80)
    print("🚀 VWAP + S/R Strategy Dashboard Starting...")
    print("="*80)
    print("\n📊 Dashboard URL: http://localhost:8050")
    print("\n💡 Make sure you've collected training data or run a backtest:")
    print("   python ml_training_data_collector.py --days 7")

    script_dir = Path(__file__).parent
    print(f"\n📁 Dashboard loads from:")
    print(f"   - {script_dir / 'outputs' / 'latest_backtest_results.json'}")
    print(f"   - {script_dir / 'data' / 'training_data.csv'}")
    print("\n🔄 Loading dashboard...\n")

    app.run(debug=True, host='127.0.0.1', port=8050)
