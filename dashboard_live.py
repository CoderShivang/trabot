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


def calculate_detailed_metrics(results):
    """Calculate detailed metrics from trade data"""
    if not results or 'trades' not in results:
        return None

    closed_trades = [t for t in results['trades'] if t.get('exit_price') is not None]

    if not closed_trades:
        return None

    # Separate wins and losses
    wins = [t for t in closed_trades if t.get('pnl', 0) > 0]
    losses = [t for t in closed_trades if t.get('pnl', 0) <= 0]

    # Long vs Short
    long_trades = [t for t in closed_trades if t['direction'] == 'LONG']
    short_trades = [t for t in closed_trades if t['direction'] == 'SHORT']
    long_wins = [t for t in long_trades if t.get('pnl', 0) > 0]
    short_wins = [t for t in short_trades if t.get('pnl', 0) > 0]

    # Calculate metrics
    total_trades = len(closed_trades)
    total_wins = len(wins)
    total_losses = len(losses)

    avg_win = sum(t.get('pnl', 0) for t in wins) / len(wins) if wins else 0
    avg_loss = sum(abs(t.get('pnl', 0)) for t in losses) / len(losses) if losses else 0

    # Trade expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
    win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
    loss_rate = (total_losses / total_trades) * 100 if total_trades > 0 else 0
    expectancy = (win_rate / 100 * avg_win) - (loss_rate / 100 * avg_loss)

    # Long/Short performance
    long_win_rate = (len(long_wins) / len(long_trades) * 100) if long_trades else 0
    short_win_rate = (len(short_wins) / len(short_trades) * 100) if short_trades else 0

    # Average duration
    durations = [t.get('duration_minutes', 0) for t in closed_trades]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # Consecutive wins/losses
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    current_streak = 0

    for trade in closed_trades:
        is_win = trade.get('pnl', 0) > 0
        if is_win:
            if current_streak > 0:
                current_streak += 1
            else:
                current_streak = 1
            max_consecutive_wins = max(max_consecutive_wins, current_streak)
        else:
            if current_streak < 0:
                current_streak -= 1
            else:
                current_streak = -1
            max_consecutive_losses = max(max_consecutive_losses, abs(current_streak))

    # Best and worst trades
    best_trade = max((t.get('pnl', 0) for t in closed_trades), default=0)
    worst_trade = min((t.get('pnl', 0) for t in closed_trades), default=0)

    # Get leverage from config (if available in trades)
    leverage = closed_trades[0].get('leverage', 'N/A') if closed_trades else 'N/A'

    # Risk/Reward ratio
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    return {
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'long_trades': len(long_trades),
        'short_trades': len(short_trades),
        'long_win_rate': long_win_rate,
        'short_win_rate': short_win_rate,
        'avg_duration': avg_duration,
        'max_consecutive_wins': max_consecutive_wins,
        'max_consecutive_losses': max_consecutive_losses,
        'best_trade': best_trade,
        'worst_trade': worst_trade,
        'leverage': leverage,
        'rr_ratio': rr_ratio
    }


def display_metrics(results):
    """Display comprehensive performance metrics"""
    if not results or 'metrics' not in results:
        return

    metrics = results['metrics']
    detailed = calculate_detailed_metrics(results)

    st.subheader("📈 Performance Overview")

    # Row 1: Core Metrics
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

    if detailed:
        st.markdown("---")

        # Row 2: Win/Loss Analysis
        st.subheader("💰 Win/Loss Analysis")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Avg Win", f"${detailed['avg_win']:.2f}")

        with col2:
            st.metric("Avg Loss", f"${detailed['avg_loss']:.2f}")

        with col3:
            st.metric("Risk/Reward", f"1:{detailed['rr_ratio']:.2f}",
                     delta="Good" if detailed['rr_ratio'] >= 1.5 else "Low")

        with col4:
            expectancy_color = "normal" if detailed['expectancy'] > 0 else "inverse"
            st.metric("Expectancy", f"${detailed['expectancy']:+.2f}",
                     delta="Positive" if detailed['expectancy'] > 0 else "Negative",
                     delta_color=expectancy_color)

        st.markdown("---")

        # Row 3: Direction Bias & Streaks
        st.subheader("📊 Direction Bias & Streaks")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            long_bias = (detailed['long_trades'] / (detailed['long_trades'] + detailed['short_trades']) * 100) if (detailed['long_trades'] + detailed['short_trades']) > 0 else 0
            st.metric("Long Trades", f"{detailed['long_trades']} ({long_bias:.0f}%)")

        with col2:
            st.metric("Long Win Rate", f"{detailed['long_win_rate']:.1f}%",
                     delta="Good" if detailed['long_win_rate'] >= 50 else "Low")

        with col3:
            short_bias = (detailed['short_trades'] / (detailed['long_trades'] + detailed['short_trades']) * 100) if (detailed['long_trades'] + detailed['short_trades']) > 0 else 0
            st.metric("Short Trades", f"{detailed['short_trades']} ({short_bias:.0f}%)")

        with col4:
            st.metric("Short Win Rate", f"{detailed['short_win_rate']:.1f}%",
                     delta="Good" if detailed['short_win_rate'] >= 50 else "Low")

        st.markdown("---")

        # Row 4: Additional Metrics
        st.subheader("📉 Trade Quality Metrics")
        col1, col2, col3, col4, col5, col6 = st.columns(6)

        with col1:
            st.metric("Best Trade", f"${detailed['best_trade']:.2f}")

        with col2:
            st.metric("Worst Trade", f"${detailed['worst_trade']:.2f}")

        with col3:
            st.metric("Avg Duration", f"{int(detailed['avg_duration'])}m")

        with col4:
            st.metric("Max Win Streak", f"{detailed['max_consecutive_wins']}")

        with col5:
            st.metric("Max Loss Streak", f"{detailed['max_consecutive_losses']}",
                     delta="Watch" if detailed['max_consecutive_losses'] >= 3 else None)

        with col6:
            leverage_display = f"{detailed['leverage']}×" if isinstance(detailed['leverage'], (int, float)) else str(detailed['leverage'])
            st.metric("Leverage Used", leverage_display)


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
