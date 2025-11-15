"""
Interactive Streamlit Dashboard for CLC Trading Bot

Features:
- One-click backtesting with date range selection
- Live chart visualization with MA, VWAP, S/R zones
- Trade explainability (why algo took each trade)
- Trade rating system for ML training
- Missed setup marking
- ML performance metrics
- S/R zone management
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config import load_config
from backtesting.backtest_engine import BacktestEngine
from learning.feedback_system import AdaptiveFeedbackSystem
from learning.ml_optimizer import MLParameterOptimizer
from src.utils.trade_explainability import create_trade_explanation, format_trade_summary, format_trade_emoji

# Page config
st.set_page_config(
    page_title="CLC Trading Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .trade-card {
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #ddd;
        margin: 0.5rem 0;
    }
    .trade-card-win {
        background-color: #d4edda;
        border-color: #c3e6cb;
    }
    .trade-card-loss {
        background-color: #f8d7da;
        border-color: #f5c6cb;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'backtest_running' not in st.session_state:
    st.session_state.backtest_running = False
if 'backtest_results' not in st.session_state:
    st.session_state.backtest_results = None
if 'selected_trade_idx' not in st.session_state:
    st.session_state.selected_trade_idx = None
if 'config' not in st.session_state:
    st.session_state.config = load_config()
if 'feedback_system' not in st.session_state:
    st.session_state.feedback_system = AdaptiveFeedbackSystem(st.session_state.config)
if 'ml_optimizer' not in st.session_state:
    st.session_state.ml_optimizer = MLParameterOptimizer(st.session_state.config)


def main():
    """Main dashboard"""

    st.title("🤖 CLC Trading Bot Dashboard")
    st.markdown("**Algorithmic Trading with Context, Location, Confirmation**")

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")

        # Symbol selection
        symbol = st.selectbox(
            "Trading Pair",
            options=["BTCUSDT", "ETHUSDT"],
            index=0
        )

        st.markdown("---")

        # Backtest configuration
        st.subheader("📅 Backtest Setup")

        backtest_mode = st.radio(
            "Date Range",
            options=["Last N Days", "Custom Range"],
            index=0
        )

        if backtest_mode == "Last N Days":
            days = st.slider("Number of Days", min_value=1, max_value=30, value=7)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
        else:
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=7))
            with col2:
                end_date = st.date_input("End Date", value=datetime.now())

            start_date = datetime.combine(start_date, datetime.min.time())
            end_date = datetime.combine(end_date, datetime.max.time())

        timeframe = st.selectbox(
            "Execution Timeframe",
            options=["1m", "5m"],
            index=0
        )

        st.markdown("---")

        # Run backtest button
        if st.button("🚀 Run Backtest", type="primary", disabled=st.session_state.backtest_running):
            st.session_state.backtest_running = True
            st.rerun()

        # ML status
        st.markdown("---")
        st.subheader("🤖 ML Status")

        if st.session_state.ml_optimizer.model is not None:
            st.success("✓ Model Trained")
            st.caption(f"Trained on {st.session_state.ml_optimizer.last_trained_count} trades")
        else:
            st.info("Waiting for 100+ trades to train")

    # Main content area
    if st.session_state.backtest_running:
        run_backtest(symbol, start_date, end_date, timeframe)
    elif st.session_state.backtest_results:
        display_backtest_results(st.session_state.backtest_results)
    else:
        display_welcome_screen()


def display_welcome_screen():
    """Show welcome screen when no backtest has been run"""

    st.markdown("## 👋 Welcome to the CLC Trading Bot Dashboard")

    st.markdown("""
### Getting Started

1. **Select Trading Pair** - Choose BTC/USDT or ETH/USDT in the sidebar
2. **Choose Date Range** - Pick last N days or custom range
3. **Run Backtest** - Click the "Run Backtest" button
4. **Review Trades** - See detailed explanations for each trade
5. **Rate Setups** - Give feedback to improve the algorithm
6. **Mark Missed Trades** - Teach the bot about opportunities it missed

### What You'll See

- **Live Charts** with price action, moving averages, VWAP, and S/R zones
- **Trade Explainability** for every entry (why the algo took the trade)
- **Performance Metrics** including win rate, profit factor, Sharpe ratio
- **ML Predictions** showing which features matter most
- **Feedback System** to train the bot to trade like you

### Current Configuration

""")

    config = st.session_state.config

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Starting Capital", f"${config.trading.position_size_usdt:.0f}")
        st.metric("Leverage", f"{config.trading.leverage}×")

    with col2:
        st.metric("Risk per Trade", f"${config.risk.per_trade_max_loss_usdt:.0f}")
        st.metric("Daily Loss Limit", f"${config.risk.max_daily_loss_usdt:.0f}")

    with col3:
        st.metric("Min Entry Score", f"{config.scoring.min_entry_score:.0f}")
        st.metric("Max Positions", config.trading.max_positions)

    st.info("👆 Click **'Run Backtest'** in the sidebar to get started!")


def run_backtest(symbol: str, start_date: datetime, end_date: datetime, timeframe: str):
    """Run backtest and display progress"""

    st.markdown("## 🔄 Running Backtest...")

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # Run backtest
        status_text.text("Initializing backtest engine...")
        progress_bar.progress(10)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        engine = BacktestEngine(st.session_state.config)

        status_text.text("Initializing components...")
        progress_bar.progress(20)

        loop.run_until_complete(engine.initialize())

        status_text.text(f"Loading historical data for {symbol}...")
        progress_bar.progress(30)

        status_text.text("Running backtest (this may take a few minutes)...")
        progress_bar.progress(40)

        metrics = loop.run_until_complete(
            engine.run_backtest(symbol, start_date, end_date, timeframe)
        )

        progress_bar.progress(90)
        status_text.text("Generating results...")

        # Store results
        st.session_state.backtest_results = {
            'engine': engine,
            'metrics': metrics,
            'symbol': symbol,
            'start_date': start_date,
            'end_date': end_date,
            'timeframe': timeframe
        }

        progress_bar.progress(100)
        status_text.text("Backtest complete!")

        # Train ML model if enough trades
        if engine.ml_optimizer and engine.ml_optimizer.should_retrain(len(engine.closed_trades)):
            status_text.text("Training ML model...")
            engine.ml_optimizer.train_model(engine.closed_trades)

        st.session_state.backtest_running = False
        st.success("✅ Backtest completed successfully!")

        # Small delay before rerun
        import time
        time.sleep(1)

        st.rerun()

    except Exception as e:
        st.error(f"❌ Backtest failed: {str(e)}")
        st.exception(e)
        st.session_state.backtest_running = False


def display_backtest_results(results: dict):
    """Display comprehensive backtest results"""

    engine = results['engine']
    metrics = results['metrics']
    symbol = results['symbol']

    # Header with key metrics
    st.markdown(f"## 📊 Backtest Results: {symbol}")
    st.caption(f"{results['start_date'].strftime('%Y-%m-%d')} to {results['end_date'].strftime('%Y-%m-%d')}")

    # Top-level metrics
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        pnl_color = "normal" if metrics.net_pnl >= 0 else "inverse"
        st.metric(
            "Net P&L",
            f"${metrics.net_pnl:+.2f}",
            delta=f"{metrics.roi_pct:+.1f}%",
            delta_color=pnl_color
        )

    with col2:
        st.metric(
            "Win Rate",
            f"{metrics.win_rate:.1f}%",
            delta=f"{metrics.winning_trades}W / {metrics.losing_trades}L"
        )

    with col3:
        st.metric(
            "Profit Factor",
            f"{metrics.profit_factor:.2f}",
            delta="Good" if metrics.profit_factor > 1.5 else "Poor"
        )

    with col4:
        st.metric(
            "Sharpe Ratio",
            f"{metrics.sharpe_ratio:.2f}",
            delta="Excellent" if metrics.sharpe_ratio > 1.5 else "Fair"
        )

    with col5:
        st.metric(
            "Max Drawdown",
            f"${metrics.max_drawdown:.2f}",
            delta=f"{metrics.max_drawdown_pct:.1f}%",
            delta_color="inverse"
        )

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Chart & Trades",
        "📊 Performance",
        "🤖 ML Insights",
        "⭐ Rate Trades",
        "📝 Missed Setups"
    ])

    with tab1:
        display_chart_and_trades(engine)

    with tab2:
        display_performance_metrics(metrics, engine)

    with tab3:
        display_ml_insights(engine)

    with tab4:
        display_trade_rating(engine)

    with tab5:
        display_missed_setups(engine, symbol)


def display_chart_and_trades(engine):
    """Display price chart with trades and indicators"""

    st.subheader("Price Chart with Trades")

    if not engine.closed_trades:
        st.warning("No trades were executed during backtest period")
        return

    # Get klines data
    symbol = engine.closed_trades[0]['symbol']

    # Create candlestick chart
    # For now, create a simple trade visualization
    # Full chart implementation would require storing candle data during backtest

    # Display trades timeline
    st.subheader("Trades Timeline")

    for idx, trade in enumerate(engine.closed_trades):
        explanation = create_trade_explanation(
            symbol=trade['symbol'],
            direction=trade['direction'],
            entry_price=trade['entry_price'],
            timestamp=trade['entry_time'],
            clc_score=type('obj', (object,), trade.get('clc_score', {}))(),
            ml_prediction=None,
            human_context=None
        )

        emoji = format_trade_emoji(explanation)
        summary = format_trade_summary(explanation)

        pnl_color = "🟢" if trade['net_pnl'] > 0 else "🔴"

        with st.expander(f"{emoji} Trade #{idx+1}: {summary} | P&L: {pnl_color} ${trade['net_pnl']:+.2f}"):
            col1, col2 = st.columns([2, 1])

            with col1:
                # Trade explanation
                st.markdown(explanation.to_markdown())

            with col2:
                # Trade details
                st.markdown("### Trade Details")
                st.write(f"**Entry:** ${trade['entry_price']:,.2f}")
                st.write(f"**Exit:** ${trade['exit_price']:,.2f}")
                st.write(f"**Quantity:** {trade['quantity']:.6f}")
                st.write(f"**P&L:** ${trade['net_pnl']:+.2f}")
                st.write(f"**Fees:** ${trade['fees']:.2f}")
                st.write(f"**Duration:** {trade['duration_minutes']:.1f} min")
                st.write(f"**Exit Reason:** {trade['exit_reason']}")


def display_performance_metrics(metrics, engine):
    """Display detailed performance metrics"""

    st.subheader("Performance Breakdown")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Trade Statistics")
        st.write(f"**Total Trades:** {metrics.total_trades}")
        st.write(f"**Winning Trades:** {metrics.winning_trades}")
        st.write(f"**Losing Trades:** {metrics.losing_trades}")
        st.write(f"**Win Rate:** {metrics.win_rate:.2f}%")
        st.write(f"**Avg Win:** ${metrics.avg_win:.2f}")
        st.write(f"**Avg Loss:** ${metrics.avg_loss:.2f}")
        st.write(f"**Largest Win:** ${metrics.largest_win:.2f}")
        st.write(f"**Largest Loss:** ${metrics.largest_loss:.2f}")

    with col2:
        st.markdown("### Risk Metrics")
        st.write(f"**Profit Factor:** {metrics.profit_factor:.2f}")
        st.write(f"**Expectancy:** ${metrics.expectancy:.2f} per trade")
        st.write(f"**Sharpe Ratio:** {metrics.sharpe_ratio:.2f}")
        st.write(f"**Max Drawdown:** ${metrics.max_drawdown:.2f} ({metrics.max_drawdown_pct:.2f}%)")
        st.write(f"**Max Consecutive Losses:** {metrics.max_consecutive_losses}")
        st.write(f"**Avg Risk/Reward:** {metrics.avg_risk_reward:.2f}")

    st.markdown("---")

    # Direction breakdown
    st.subheader("Direction Analysis")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### LONG Trades")
        st.metric("Count", metrics.long_trades)
        st.metric("Win Rate", f"{metrics.long_win_rate:.1f}%")

    with col2:
        st.markdown("### SHORT Trades")
        st.metric("Count", metrics.short_trades)
        st.metric("Win Rate", f"{metrics.short_win_rate:.1f}%")

    # Time metrics
    st.markdown("---")
    st.subheader("Time Analysis")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Duration", f"{metrics.duration_days:.1f} days")

    with col2:
        st.metric("Trades per Day", f"{metrics.trades_per_day:.2f}")

    with col3:
        st.metric("Avg Trade Duration", f"{metrics.avg_trade_duration_minutes:.1f} min")


def display_ml_insights(engine):
    """Display ML model insights and feature importance"""

    st.subheader("🤖 Machine Learning Insights")

    ml_optimizer = engine.ml_optimizer

    if ml_optimizer.model is None:
        st.info(f"ML model not trained yet. Need {ml_optimizer.min_samples} trades minimum.")
        st.write(f"Current trades: {len(engine.closed_trades)}")
        return

    # Feature importance
    st.markdown("### Feature Importance")
    st.caption("Which factors predict winning trades?")

    importance = ml_optimizer.get_feature_importance()

    if importance:
        # Create bar chart
        import plotly.express as px

        df_importance = pd.DataFrame([
            {'Feature': k, 'Importance': v}
            for k, v in list(importance.items())[:10]  # Top 10
        ])

        fig = px.bar(
            df_importance,
            x='Importance',
            y='Feature',
            orientation='h',
            title="Top 10 Predictive Features"
        )

        st.plotly_chart(fig, use_container_width=True)

        # Insights
        top_3 = list(importance.keys())[:3]
        st.success(f"**Top 3 Features:** {', '.join(top_3)}")

    # Model performance
    st.markdown("---")
    st.markdown("### Model Performance")

    training_report = ml_optimizer.generate_training_report(engine.closed_trades)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Training Data", f"{training_report['total_trades']} trades")

    with col2:
        st.metric("Model Accuracy", training_report.get('test_accuracy', 'N/A'))

    with col3:
        st.metric("Baseline Win Rate", training_report['win_rate'])

    # Suggestions
    st.markdown("---")
    st.markdown("### Parameter Suggestions")

    suggestions = ml_optimizer.suggest_threshold_adjustment(engine.closed_trades[-50:])

    if 'adjustments' in suggestions and suggestions['adjustments']:
        for adj in suggestions['adjustments']:
            st.warning(f"**{adj['parameter']}**: {adj['current']} → {adj['suggested']}")
            st.caption(adj['reason'])
    else:
        st.success("✓ No adjustments needed - performance looks good!")


def display_trade_rating(engine):
    """Allow user to rate trades for ML training"""

    st.subheader("⭐ Rate Trades")
    st.caption("Your ratings help the algorithm learn your trading style")

    if not engine.closed_trades:
        st.info("No trades to rate yet. Run a backtest first!")
        return

    # Select trade to rate
    trade_options = [
        f"Trade #{i+1}: {t['direction']} @ ${t['entry_price']:,.2f} | P&L: ${t['net_pnl']:+.2f}"
        for i, t in enumerate(engine.closed_trades)
    ]

    selected_idx = st.selectbox("Select Trade", range(len(trade_options)), format_func=lambda x: trade_options[x])

    if selected_idx is not None:
        trade = engine.closed_trades[selected_idx]

        # Display trade details
        explanation = create_trade_explanation(
            symbol=trade['symbol'],
            direction=trade['direction'],
            entry_price=trade['entry_price'],
            timestamp=trade['entry_time'],
            clc_score=type('obj', (object,), trade.get('clc_score', {}))(),
            ml_prediction=None,
            human_context=None
        )

        st.markdown(explanation.to_markdown())

        st.markdown("---")

        # Rating interface
        st.markdown("### Your Rating")

        rating = st.select_slider(
            "How good was this setup?",
            options=[1, 2, 3, 4, 5],
            value=3,
            format_func=lambda x: "⭐" * x
        )

        notes = st.text_area(
            "Notes (optional)",
            placeholder="What made this setup good/bad? What did you like/dislike?"
        )

        if st.button("Submit Rating"):
            # Save rating to feedback system
            st.session_state.feedback_system.add_trade_feedback(
                trade_id=trade.get('id', f"{trade['symbol']}_{trade['entry_time']}"),
                rating=rating,
                notes=notes,
                trade_data=trade
            )

            st.success(f"✅ Rated {rating}/5 stars!")

            # Retrain ML if enough feedback
            total_feedback = len(st.session_state.feedback_system.feedback_history)
            if total_feedback >= 20 and total_feedback % 10 == 0:
                st.info("🤖 Retraining ML model with your feedback...")
                engine.ml_optimizer.train_model(engine.closed_trades)
                st.success("Model updated!")


def display_missed_setups(engine, symbol):
    """Allow user to mark missed trading opportunities"""

    st.subheader("📝 Mark Missed Setups")
    st.caption("Teach the bot about opportunities it should have taken")

    col1, col2 = st.columns(2)

    with col1:
        direction = st.selectbox("Direction", ["LONG", "SHORT"])

    with col2:
        entry_price = st.number_input("Entry Price", min_value=0.0, value=50000.0, step=100.0)

    reasons = st.multiselect(
        "Why was this a good setup?",
        options=[
            "Strong S/R bounce",
            "High volume confirmation",
            "Psychological level",
            "Multiple timeframe alignment",
            "Large orders detected",
            "Absorption at level",
            "Perfect tape reading",
            "Clean breakout/breakdown"
        ]
    )

    outcome = st.radio(
        "Would it have been a winner?",
        options=["Would have won", "Would have lost", "Uncertain"]
    )

    notes = st.text_area(
        "Additional notes",
        placeholder="Describe what made this setup special..."
    )

    if st.button("Mark as Missed Setup"):
        if not reasons:
            st.error("Please select at least one reason")
            return

        # Save to feedback system
        st.session_state.feedback_system.mark_missed_setup(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            reasons=reasons,
            expected_outcome=outcome,
            notes=notes
        )

        st.success("✅ Missed setup recorded!")

        # Show analysis if enough missed setups
        missed_count = len(st.session_state.feedback_system.missed_setups)
        if missed_count >= 5:
            st.info(f"📊 You've marked {missed_count} missed setups. Analyzing patterns...")

            analysis = st.session_state.feedback_system.analyze_missed_setups()
            if analysis.get('top_missing_pattern'):
                st.warning(f"**Most Common Pattern:** {analysis['top_missing_pattern']} ({analysis['top_missing_count']} times)")
                st.caption("Consider adjusting parameters to capture these setups")


if __name__ == "__main__":
    main()
