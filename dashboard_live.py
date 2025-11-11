#!/usr/bin/env python3
"""
Live Dashboard - Real-time monitoring for forward testing and live trading.

This dashboard shows trades as they happen in real-time. It auto-refreshes
every 2 seconds to display:
- Current open positions
- Recently closed trades
- Running P&L
- Performance metrics
- Trade explanations

Usage:
    # Start forward test in one terminal:
    python run_forward_test.py

    # Start live dashboard in another terminal:
    streamlit run dashboard_live.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
from pathlib import Path
from datetime import datetime, timedelta
import time

# Page config
st.set_page_config(
    page_title="Live Trading Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Auto-refresh every 2 seconds
st_autorefresh = st.empty()

# Custom CSS
st.markdown("""
<style>
    .big-metric {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
    }
    .positive {
        color: #00ff00;
    }
    .negative {
        color: #ff0000;
    }
    .position-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .trade-row {
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 5px;
        border-left: 4px solid;
    }
    .trade-win {
        background-color: #d4edda;
        border-color: #28a745;
    }
    .trade-loss {
        background-color: #f8d7da;
        border-color: #dc3545;
    }
    .status-running {
        color: #28a745;
        font-weight: bold;
    }
    .status-stopped {
        color: #dc3545;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


def load_forward_test_results():
    """Load forward test results from JSON file"""
    results_file = Path("data/forward_test_results.json")

    if not results_file.exists():
        return None

    try:
        with open(results_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading results: {e}")
        return None


def is_session_running(results):
    """Check if forward test session is currently running"""
    if not results or 'session_end' not in results:
        return False

    # If session_end is None, session is running
    return results['session_end'] is None


def display_header():
    """Display dashboard header with status"""
    results = load_forward_test_results()

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        st.title("📊 Live Trading Monitor")

    with col2:
        if results and is_session_running(results):
            st.markdown('<p class="status-running">🟢 ACTIVE</p>', unsafe_allow_html=True)
            st.caption("Forward test running")
        else:
            st.markdown('<p class="status-stopped">🔴 STOPPED</p>', unsafe_allow_html=True)
            st.caption("No active session")

    with col3:
        st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
        if st.button("🔄 Refresh Now"):
            st.rerun()


def display_current_position(results):
    """Display current open position if any"""
    if not results or 'trades' not in results:
        return

    # Find unclosed trades (positions)
    open_trades = [t for t in results['trades'] if t.get('exit_price') is None]

    if not open_trades:
        st.info("📭 No open positions")
        return

    st.subheader("📍 Current Position")

    for pos in open_trades:
        direction = pos['direction']
        symbol = pos['symbol']
        entry_price = pos['entry_price']
        stop_loss = pos['stop_loss']
        take_profit = pos['take_profit']
        current_price = pos.get('current_price', entry_price)
        entry_time = datetime.fromtimestamp(pos['entry_time'] / 1000)

        # Calculate unrealized P&L
        quantity = pos['quantity']
        if direction == "LONG":
            unrealized_pnl = (current_price - entry_price) * quantity
        else:
            unrealized_pnl = (entry_price - current_price) * quantity

        pnl_pct = (unrealized_pnl / (entry_price * quantity)) * 100

        # Duration
        duration = datetime.now() - entry_time
        duration_str = f"{int(duration.total_seconds() / 60)}m"

        # Display position card
        st.markdown(f"""
        <div class="position-card">
            <h3>{'🟢' if direction == 'LONG' else '🔴'} {symbol} {direction}</h3>
            <p><strong>Entry:</strong> ${entry_price:,.2f} | <strong>Current:</strong> ${current_price:,.2f}</p>
            <p><strong>Stop Loss:</strong> ${stop_loss:,.2f} | <strong>Take Profit:</strong> ${take_profit:,.2f}</p>
            <p><strong>Unrealized P&L:</strong> <span class="{'positive' if unrealized_pnl > 0 else 'negative'}">${unrealized_pnl:+.2f} ({pnl_pct:+.2f}%)</span></p>
            <p><strong>Duration:</strong> {duration_str} | <strong>Opened:</strong> {entry_time.strftime('%H:%M:%S')}</p>
        </div>
        """, unsafe_allow_html=True)


def display_metrics(results):
    """Display key performance metrics"""
    if not results or 'metrics' not in results:
        return

    metrics = results['metrics']

    st.subheader("📈 Session Metrics")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        total_trades = metrics.get('total_trades', 0)
        st.metric("Total Trades", total_trades)

    with col2:
        win_rate = metrics.get('win_rate', 0)
        st.metric("Win Rate", f"{win_rate:.1f}%",
                  delta="Good" if win_rate >= 50 else "Improve")

    with col3:
        net_pnl = metrics.get('net_pnl', 0)
        st.metric("Net P&L", f"${net_pnl:+.2f}",
                  delta=f"{metrics.get('roi_pct', 0):+.2f}%")

    with col4:
        profit_factor = metrics.get('profit_factor', 0)
        st.metric("Profit Factor", f"{profit_factor:.2f}",
                  delta="Good" if profit_factor >= 1.5 else "Low")

    with col5:
        current_balance = metrics.get('current_balance', 0)
        st.metric("Balance", f"${current_balance:.2f}")


def display_recent_trades(results, limit=10):
    """Display recent closed trades"""
    if not results or 'trades' not in results:
        return

    # Filter closed trades
    closed_trades = [t for t in results['trades'] if t.get('exit_price') is not None]

    if not closed_trades:
        st.info("📭 No closed trades yet")
        return

    st.subheader(f"📋 Recent Trades (Last {limit})")

    # Sort by exit time, most recent first
    closed_trades.sort(key=lambda x: x.get('exit_time', 0), reverse=True)

    # Display last N trades
    for trade in closed_trades[:limit]:
        symbol = trade['symbol']
        direction = trade['direction']
        entry_price = trade['entry_price']
        exit_price = trade['exit_price']
        pnl = trade.get('pnl', 0)
        exit_reason = trade.get('exit_reason', 'unknown')
        duration_min = trade.get('duration_minutes', 0)

        # Calculate P&L percentage
        quantity = trade['quantity']
        pnl_pct = (pnl / (entry_price * quantity)) * 100

        # Format times
        entry_time = datetime.fromtimestamp(trade['entry_time'] / 1000).strftime('%H:%M:%S')
        exit_time = datetime.fromtimestamp(trade['exit_time'] / 1000).strftime('%H:%M:%S')

        # Determine win/loss
        is_win = pnl > 0
        trade_class = "trade-win" if is_win else "trade-loss"
        emoji = "✅" if is_win else "❌"

        # Display trade row
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 1, 1])

            with col1:
                st.markdown(f"**{emoji} {symbol} {direction}**")
                st.caption(f"{entry_time} → {exit_time}")

            with col2:
                st.markdown(f"Entry: ${entry_price:,.2f}")
                st.markdown(f"Exit: ${exit_price:,.2f}")

            with col3:
                pnl_color = "positive" if is_win else "negative"
                st.markdown(f'<span class="{pnl_color}">${pnl:+.2f} ({pnl_pct:+.2f}%)</span>',
                          unsafe_allow_html=True)

            with col4:
                st.caption(f"{duration_min}m")

            with col5:
                reason_map = {
                    'stop_loss': '🛑 SL',
                    'take_profit': '🎯 TP',
                    'manual': '✋ Manual',
                    'session_end': '⏹️ End'
                }
                st.caption(reason_map.get(exit_reason, exit_reason))

            st.divider()


def display_equity_curve(results):
    """Display equity curve chart"""
    if not results or 'trades' not in results:
        return

    closed_trades = [t for t in results['trades'] if t.get('exit_price') is not None]

    if not closed_trades:
        return

    st.subheader("💰 Equity Curve")

    # Calculate cumulative P&L
    starting_balance = results['metrics'].get('starting_balance', 100)
    balance = starting_balance
    equity = [starting_balance]
    timestamps = [results['session_start']]

    for trade in sorted(closed_trades, key=lambda x: x.get('exit_time', 0)):
        balance += trade.get('net_pnl', trade.get('pnl', 0))
        equity.append(balance)
        timestamps.append(datetime.fromtimestamp(trade['exit_time'] / 1000).isoformat())

    # Create chart
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=timestamps,
        y=equity,
        mode='lines',
        name='Equity',
        line=dict(color='#667eea', width=3),
        fill='tozeroy',
        fillcolor='rgba(102, 126, 234, 0.1)'
    ))

    # Add starting balance line
    fig.add_hline(y=starting_balance, line_dash="dash",
                  line_color="gray", annotation_text="Starting Balance")

    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Balance (USDT)",
        hovermode='x unified',
        showlegend=False,
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)


def display_trade_distribution(results):
    """Display trade distribution charts"""
    if not results or 'trades' not in results:
        return

    closed_trades = [t for t in results['trades'] if t.get('exit_price') is not None]

    if len(closed_trades) < 3:
        return

    st.subheader("📊 Trade Distribution")

    col1, col2 = st.columns(2)

    with col1:
        # Win/Loss distribution
        wins = len([t for t in closed_trades if t.get('pnl', 0) > 0])
        losses = len(closed_trades) - wins

        fig = go.Figure(data=[go.Pie(
            labels=['Wins', 'Losses'],
            values=[wins, losses],
            marker=dict(colors=['#28a745', '#dc3545']),
            hole=0.4
        )])

        fig.update_layout(
            title="Win/Loss Ratio",
            showlegend=True,
            height=300
        )

        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # P&L distribution
        pnls = [t.get('pnl', 0) for t in closed_trades]

        fig = go.Figure(data=[go.Histogram(
            x=pnls,
            nbinsx=20,
            marker=dict(
                color=pnls,
                colorscale='RdYlGn',
                showscale=False
            )
        )])

        fig.update_layout(
            title="P&L Distribution",
            xaxis_title="P&L (USDT)",
            yaxis_title="Frequency",
            height=300
        )

        st.plotly_chart(fig, use_container_width=True)


def main():
    """Main dashboard function"""

    # Display header with status
    display_header()

    # Load results
    results = load_forward_test_results()

    if not results:
        st.warning("⚠️ No forward test session found")
        st.info("""
        **To start monitoring:**

        1. Open a terminal and run: `python run_forward_test.py`
        2. This dashboard will automatically show trades as they happen
        3. Refreshes every 2 seconds
        """)
        return

    # Session info
    session_start = datetime.fromisoformat(results['session_start'])
    if results.get('session_end'):
        session_end = datetime.fromisoformat(results['session_end'])
        duration = session_end - session_start
        st.caption(f"Session: {session_start.strftime('%Y-%m-%d %H:%M')} to {session_end.strftime('%H:%M')} ({duration})")
    else:
        duration = datetime.now() - session_start
        hours = int(duration.total_seconds() / 3600)
        minutes = int((duration.total_seconds() % 3600) / 60)
        st.caption(f"Session started: {session_start.strftime('%Y-%m-%d %H:%M')} (Running for {hours}h {minutes}m)")

    st.markdown("---")

    # Display current position
    display_current_position(results)

    st.markdown("---")

    # Display metrics
    display_metrics(results)

    st.markdown("---")

    # Two columns: Recent trades and charts
    col1, col2 = st.columns([1, 1])

    with col1:
        display_recent_trades(results, limit=10)

    with col2:
        display_equity_curve(results)
        st.markdown("")
        display_trade_distribution(results)

    # Auto-refresh footer
    st.markdown("---")
    st.caption("🔄 Dashboard auto-refreshes every 2 seconds")

    # Auto-refresh every 2 seconds
    time.sleep(2)
    st.rerun()


if __name__ == "__main__":
    main()
