"""
VWAP Strategy Backtest Engine

Features:
1. Uses ONLY limit orders (entry, TP, SL) for lower fees
2. Fetches data from live Binance mainnet
3. Realistic order fill simulation
4. Detailed trade logging for analysis
5. Supports 1-minute timeframe trading

All orders are limit orders:
- Entry: Limit order at signal price
- Take Profit: Limit order at TP price
- Stop Loss: Limit order at SL price (simulates stop-limit)
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, field
import json
from pathlib import Path
import pandas as pd
import numpy as np
from tqdm import tqdm

from src.data.binance_client import BinanceClient
from src.strategy.vwap_strategy import VWAPStrategy, TradeSignal
from src.utils.logger import setup_logger
from src.visualization.dashboard import VWAPDashboard
from src.visualization.interactive_dashboard import InteractiveDashboard

logger = setup_logger(__name__)


@dataclass
class LimitOrder:
    """Limit order representation"""
    order_id: str
    order_type: str  # 'ENTRY', 'TP', 'SL'
    direction: str  # 'LONG' or 'SHORT'
    limit_price: float
    quantity: float
    created_at: int  # Timestamp (ms)
    timeout: int = 300  # Seconds before order expires
    filled: bool = False
    filled_at: Optional[int] = None
    filled_price: Optional[float] = None


@dataclass
class BacktestPosition:
    """Active position in backtest"""
    position_id: str
    direction: str
    entry_price: float
    entry_time: int
    quantity: float
    stop_loss: float
    take_profit: float
    signal: TradeSignal

    # Orders
    tp_order: Optional[LimitOrder] = None
    sl_order: Optional[LimitOrder] = None

    # Tracking
    highest_price: float = 0.0
    lowest_price: float = float('inf')
    use_trailing_tp: bool = False  # Enable trailing TP for trend trades
    trailing_activated: bool = False  # Whether trailing has been activated

    # Exit
    exit_price: Optional[float] = None
    exit_time: Optional[int] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

    # Fees
    entry_fee: Optional[float] = None
    exit_fee: Optional[float] = None
    total_fees: Optional[float] = None


@dataclass
class BacktestStats:
    """Backtest performance statistics"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_trade_duration: float = 0.0  # Minutes

    # Trade types
    mean_reversion_trades: int = 0
    trend_continuation_trades: int = 0

    # Day of week analysis
    trades_by_day: dict = field(default_factory=lambda: {
        'Monday': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Tuesday': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Wednesday': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Thursday': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Friday': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Saturday': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Sunday': {'wins': 0, 'losses': 0, 'total_pnl': 0.0}
    })

    # Limit order stats
    entry_fills: int = 0
    entry_timeouts: int = 0
    tp_fills: int = 0
    sl_fills: int = 0


class VWAPMLBacktestEngine:
    """
    ML-Enhanced Backtest engine for VWAP strategy with real-time filtering

    Features:
    - ML-based trade filtering using walk-forward analysis
    - 3-model ensemble (Random Forest, Gradient Boosting, XGBoost)
    - All orders are limit orders with realistic fill simulation
    - Prevents look-ahead bias through proper train/test splits
    """

    def __init__(self, config: Dict, ml_optimizer=None):
        self.config = config
        self.symbol = config.get('symbol', 'BTCUSDT')
        self.timeframe = config.get('timeframe', '1m')
        self.initial_capital = config.get('initial_capital', 100)
        self.risk_per_trade = config.get('risk_per_trade', 0.02)  # 2% per trade
        self.leverage = config.get('leverage', 20)  # 20x leverage for futures

        # ML Filtering
        self.ml_optimizer = ml_optimizer  # VWAPMLOptimizer instance
        self.ml_enabled = ml_optimizer is not None
        self.ml_filtered_count = 0  # Track how many trades were filtered out
        self.ml_signals_evaluated = 0  # Track total signals evaluated

        # Fees (limit orders = maker fee, based on notional value)
        self.maker_fee = 0.0002  # 0.02% Binance maker fee on notional value

        # Components - Create minimal config for BinanceClient
        binance_config = self._create_binance_config()
        self.binance_client = BinanceClient(binance_config)
        self.strategy = VWAPStrategy(config.get('strategy_params', {}))

        # State
        self.current_capital = self.initial_capital
        self.current_leverage = 20  # Track current leverage for display
        self.positions: List[BacktestPosition] = []
        self.pending_entry_orders: List[LimitOrder] = []
        self.closed_trades: List[BacktestPosition] = []
        self.stats = BacktestStats()
        self.order_signals: Dict[str, TradeSignal] = {}  # Map order_id to signal

        # Equity curve tracking for visualization
        self.equity_curve: List[Dict] = []  # [{'timestamp': ms, 'equity': float, 'drawdown': float}, ...]
        self.peak_equity = self.initial_capital

        # Results directory
        self.results_dir = Path('data/vwap_ml_backtest')
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def _create_binance_config(self):
        """Create minimal config object for BinanceClient"""
        class TradingConfig:
            def __init__(self, symbols):
                self.symbols = symbols
                self.paper_trading = False  # Use mainnet for historical data

        class MinimalConfig:
            def __init__(self, symbol):
                self.trading = TradingConfig([symbol])
                self.api_key = ""  # Read-only, no auth needed for public data
                self.api_secret = ""

        return MinimalConfig(self.symbol)

    async def run(self, start_date: datetime, end_date: datetime):
        """
        Run backtest

        Args:
            start_date: Start date for backtest
            end_date: End date for backtest
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"VWAP STRATEGY BACKTEST - {self.symbol}")
        logger.info(f"{'='*80}")
        logger.info(f"Period: {start_date.date()} to {end_date.date()}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Initial Margin: ${self.initial_capital:,.2f}")
        logger.info(f"Leverage: {self.leverage}x")
        logger.info(f"Max Position Size: ${self.initial_capital * self.leverage:,.2f}")
        logger.info(f"Risk per Trade: {self.risk_per_trade*100:.1f}%")
        logger.info(f"Maker Fee: {self.maker_fee*100:.3f}% (of notional)")
        logger.info(f"{'='*80}\n")

        # Connect to Binance client
        logger.info("[INIT] Connecting to Binance...")
        await self.binance_client.connect()

        # Fetch historical data from Binance mainnet
        logger.info("[DATA] Fetching historical data from Binance MAINNET...")
        klines = await self._fetch_historical_data(start_date, end_date)

        if not klines or len(klines) < 100:
            logger.error("[ERROR] Insufficient data for backtest")
            return

        logger.info(f"[DATA] Loaded {len(klines)} candles\n")

        # Convert to DataFrame
        df = self._klines_to_df(klines)

        # Run backtest simulation
        await self._simulate(df)

        # Generate results
        self._calculate_stats()
        results_path = self._save_results()
        self._display_results()

        # Print trade summary
        self._print_trade_summary()

        # Generate static HTML dashboard
        logger.info("\n[DASHBOARD] Generating static HTML visualization...")
        dashboard = VWAPDashboard(results_path, df)
        dashboard_path = dashboard.generate()
        logger.info(f"[DASHBOARD] Static HTML saved to: file://{Path(dashboard_path).absolute()}")

        # Offer interactive dashboard
        logger.info("\n[INTERACTIVE] To launch interactive dashboard with filtering, run:")
        logger.info(f"  python -c \"from src.visualization.interactive_dashboard import InteractiveDashboard; import pandas as pd; InteractiveDashboard('{results_path}', pd.read_parquet('data/vwap_backtest/ohlcv_data.parquet')).run()\"")
        logger.info("\nOr use the launch_interactive_dashboard.py script (see below)")

        # Save OHLCV data for interactive dashboard
        ohlcv_path = Path(results_path).parent / 'ohlcv_data.parquet'
        df.to_parquet(ohlcv_path, index=False)
        logger.debug(f"[DATA] Saved OHLCV data to: {ohlcv_path}")

        # Load and return the results from the saved file
        with open(results_path, 'r') as f:
            results = json.load(f)

        return results

    async def _fetch_historical_data(self, start_date: datetime, end_date: datetime) -> List:
        """Fetch historical klines from Binance mainnet"""
        all_klines = []

        timeframe_ms = self._timeframe_to_ms(self.timeframe)
        current_start = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        while current_start < end_ts:
            chunk_end = min(current_start + (1000 * timeframe_ms), end_ts)

            klines = await self.binance_client.get_klines(
                symbol=self.symbol,
                interval=self.timeframe,
                start_time=current_start,
                end_time=chunk_end
            )

            if not klines:
                break

            all_klines.extend(klines)
            logger.info(f"  Fetched {len(klines)} candles (total: {len(all_klines)})")

            if klines:
                current_start = klines[-1][0] + timeframe_ms
            else:
                break

            # Rate limiting
            await asyncio.sleep(0.1)

        return all_klines

    async def _simulate(self, df: pd.DataFrame):
        """
        Simulate trading with limit orders

        Process:
        1. On each candle, check for entry signals
        2. Place limit entry orders
        3. Check if pending orders get filled
        4. Manage open positions (TP/SL limit orders)
        5. Multi-timeframe S/R zone detection (1m, 5m, 15m)
        """
        logger.info("[BACKTEST] Starting simulation...")
        logger.info("[MTF] Preparing multi-timeframe data (1m, 5m, 15m)...")

        # Resample 1m data to 5m, 15m, and 1D for HTF S/R zones and trend filter
        df_5m = self._resample_ohlcv(df, '5min')  # 5 minutes
        df_15m = self._resample_ohlcv(df, '15min')  # 15 minutes
        df_1d = self._resample_ohlcv(df, '1D')  # 1 day

        logger.info(f"[MTF] 1m: {len(df)} bars | 5m: {len(df_5m)} bars | 15m: {len(df_15m)} bars | 1D: {len(df_1d)} bars")

        # Need lookback for strategy
        lookback = 200

        # Progress bar for simulation
        logger.info(f"[BACKTEST] Simulating {len(df) - lookback} bars...\n")
        pbar = tqdm(total=len(df) - lookback, desc="Backtesting", unit="bar", ncols=100)

        for idx in range(lookback, len(df)):
            pbar.update(1)

            # Calculate current win rate
            if len(self.closed_trades) > 0:
                wins = sum(1 for t in self.closed_trades if t.pnl > 0)
                win_rate = (wins / len(self.closed_trades)) * 100
            else:
                win_rate = 0.0

            # Update progress bar with trades, capital, win rate, and leverage
            pbar.set_postfix({
                "Trades": len(self.closed_trades),
                "Capital": f"${self.current_capital:.0f}",
                "WinRate": f"{win_rate:.1f}%",
                "Lev": f"{self.current_leverage}x"
            })

            current_bar = df.iloc[idx]
            timestamp = int(current_bar['timestamp'].timestamp() * 1000)
            open_price = float(current_bar['open'])
            high = float(current_bar['high'])
            low = float(current_bar['low'])
            close = float(current_bar['close'])

            # Historical data for strategy (up to current bar)
            hist_df = df.iloc[:idx+1].copy()

            # Get corresponding HTF data (up to current time)
            current_time = current_bar['timestamp']
            hist_df_5m = df_5m[df_5m['timestamp'] <= current_time].copy()
            hist_df_15m = df_15m[df_15m['timestamp'] <= current_time].copy()
            hist_df_1d = df_1d[df_1d['timestamp'] <= current_time].copy()

            # === 1. Check pending entry orders for fills ===
            self._check_entry_fills(timestamp, high, low)

            # === 2. Check open positions for TP/SL fills ===
            self._check_position_fills(timestamp, high, low)

            # === 3. Update position tracking, breakeven stops, and trailing TP ===
            for pos in self.positions:
                pos.highest_price = max(pos.highest_price, high)
                pos.lowest_price = min(pos.lowest_price, low)

                # Move stop to breakeven for ALL trades (once 50% to target)
                self._update_breakeven_stop(pos, close)

                # Implement trailing TP for trend trades
                if pos.use_trailing_tp and pos.tp_order:
                    self._update_trailing_tp(pos, close)

            # === 4. Look for new entry signals (if no position) ===
            if len(self.positions) == 0 and len(self.pending_entry_orders) == 0:
                # Pass multi-timeframe data to strategy
                signals = self.strategy.analyze(
                    hist_df,
                    close,
                    df_5m=hist_df_5m if len(hist_df_5m) >= 50 else None,
                    df_15m=hist_df_15m if len(hist_df_15m) >= 50 else None,
                    df_1d=hist_df_1d if len(hist_df_1d) >= 100 else None  # Need 100+ days for 100 SMA
                )

                if signals:
                    # Take best signal
                    best_signal = signals[0]
                    # Use tqdm.write to print without disrupting progress bar
                    tqdm.write(f"[SIGNAL] {best_signal.direction} @ ${best_signal.entry_price:,.0f} | Conf: {best_signal.confidence:.0f}")

                    if best_signal.confidence >= 50:  # Lowered from 65 for initial testing
                        # === ML FILTERING ===
                        if self.ml_enabled and self.ml_optimizer.is_trained:
                            self.ml_signals_evaluated += 1

                            # Prepare market data for ML
                            market_data = {
                                'current_price': close,
                                'timestamp': timestamp,
                                'volume': df.iloc[idx]['volume'],
                                'volatility': df.iloc[idx]['high'] - df.iloc[idx]['low'],
                                'spread_bps': 10  # Approximate
                            }

                            # Convert TradeSignal object to dict for ML optimizer
                            signal_dict = {
                                'direction': best_signal.direction,
                                'signal_type': best_signal.signal_type,
                                'entry_price': best_signal.entry_price,
                                'confidence': best_signal.confidence,
                                'vwap_band': best_signal.vwap_band,
                                'htf_confluence': best_signal.htf_confluence,
                                'zone_strength': best_signal.sr_zone.strength if best_signal.sr_zone else 0,
                                'zone_type': best_signal.sr_zone.zone_type if best_signal.sr_zone else 'unknown'
                            }

                            # Get ML prediction
                            win_prob, model_probs = self.ml_optimizer.predict_win_probability(
                                signal_dict,
                                market_data
                            )

                            logger.info(f"[ML-FILTER] Win Prob: {win_prob:.1%} | RF: {model_probs['rf']:.1%} GB: {model_probs['gb']:.1%} XGB: {model_probs['xgb']:.1%}")

                            # Only take trade if ML predicts high enough win probability
                            if win_prob >= self.ml_optimizer.min_win_probability:
                                logger.info(f"[ML-APPROVED] Trade passed ML filter (>{self.ml_optimizer.min_win_probability:.0%})")
                                self._place_entry_order(best_signal, timestamp)
                            else:
                                self.ml_filtered_count += 1
                                logger.info(f"[ML-REJECTED] Trade filtered out ({win_prob:.1%} < {self.ml_optimizer.min_win_probability:.0%})")
                        else:
                            # No ML or ML not trained yet - take all trades
                            self._place_entry_order(best_signal, timestamp)

        # Close progress bar
        pbar.close()

        # Close any remaining positions at end
        self._close_all_positions(df.iloc[-1], "backtest_end")

        logger.info(f"\n[BACKTEST] Simulation complete!")

    def _check_entry_fills(self, timestamp: int, high: float, low: float):
        """Check if pending entry orders get filled"""
        filled_orders = []

        for order in self.pending_entry_orders:
            # Check timeout
            elapsed = (timestamp - order.created_at) / 1000
            if elapsed > order.timeout:
                logger.debug(f"[ORDER] Entry order {order.order_id} TIMEOUT")
                filled_orders.append(order)
                self.stats.entry_timeouts += 1
                continue

            # Check if limit price was touched
            filled = False
            fill_price = order.limit_price

            if order.direction == 'LONG':
                # For LONG, we want to buy at limit or lower
                if low <= order.limit_price:
                    filled = True
                    # Fill at limit or better
                    fill_price = min(order.limit_price, low + 1)  # Assume filled near low
            else:  # SHORT
                # For SHORT, we want to sell at limit or higher
                if high >= order.limit_price:
                    filled = True
                    # Fill at limit or better
                    fill_price = max(order.limit_price, high - 1)  # Assume filled near high

            if filled:
                order.filled = True
                order.filled_at = timestamp
                order.filled_price = fill_price
                filled_orders.append(order)

                # Open position
                self._open_position(order, timestamp)
                self.stats.entry_fills += 1

        # Remove filled/timeout orders and cleanup signal mappings
        for order in filled_orders:
            self.pending_entry_orders.remove(order)
            # Clean up signal mapping
            if order.order_id in self.order_signals:
                del self.order_signals[order.order_id]

    def _check_position_fills(self, timestamp: int, high: float, low: float):
        """Check if TP or SL orders get filled"""
        closed_positions = []

        for pos in self.positions:
            # Check TP (limit order)
            if pos.tp_order and not pos.tp_order.filled:
                if pos.direction == 'LONG':
                    # TP sell limit: triggers if high >= tp_price
                    if high >= pos.take_profit:
                        pos.tp_order.filled = True
                        pos.tp_order.filled_at = timestamp
                        pos.tp_order.filled_price = pos.take_profit
                        self._close_position(pos, timestamp, pos.take_profit, "TP")
                        closed_positions.append(pos)
                        self.stats.tp_fills += 1
                        continue
                else:  # SHORT
                    # TP buy limit: triggers if low <= tp_price
                    if low <= pos.take_profit:
                        pos.tp_order.filled = True
                        pos.tp_order.filled_at = timestamp
                        pos.tp_order.filled_price = pos.take_profit
                        self._close_position(pos, timestamp, pos.take_profit, "TP")
                        closed_positions.append(pos)
                        self.stats.tp_fills += 1
                        continue

            # Check SL (stop-limit order, simulated as limit)
            if pos.sl_order and not pos.sl_order.filled:
                if pos.direction == 'LONG':
                    # SL sell limit: triggers if low <= sl_price
                    if low <= pos.stop_loss:
                        pos.sl_order.filled = True
                        pos.sl_order.filled_at = timestamp
                        pos.sl_order.filled_price = pos.stop_loss
                        self._close_position(pos, timestamp, pos.stop_loss, "SL")
                        closed_positions.append(pos)
                        self.stats.sl_fills += 1
                        continue
                else:  # SHORT
                    # SL buy limit: triggers if high >= sl_price
                    if high >= pos.stop_loss:
                        pos.sl_order.filled = True
                        pos.sl_order.filled_at = timestamp
                        pos.sl_order.filled_price = pos.stop_loss
                        self._close_position(pos, timestamp, pos.stop_loss, "SL")
                        closed_positions.append(pos)
                        self.stats.sl_fills += 1
                        continue

        # Remove closed positions
        for pos in closed_positions:
            self.positions.remove(pos)

    def _place_entry_order(self, signal: TradeSignal, timestamp: int):
        """Place limit entry order with leverage"""
        # FULL COMPOUNDING: Use current capital for realistic growth
        # Dynamic leverage naturally controls position sizes as account grows
        position_base = self.current_capital

        # DYNAMIC LEVERAGE: Reduce leverage as capital grows (safer, more stable)
        # $100-$199: 20x leverage
        # $200-$399: 15x leverage
        # $400-$599: 10x leverage
        # $600+:     5x leverage (conservative for larger accounts)
        if self.current_capital < 200:
            current_leverage = 20
        elif self.current_capital < 400:
            current_leverage = 15
        elif self.current_capital < 600:
            current_leverage = 10
        else:
            current_leverage = 5

        # Store current leverage for display
        self.current_leverage = current_leverage

        stop_distance = abs(signal.entry_price - signal.stop_loss)

        if stop_distance == 0:
            logger.warning("[RISK] Stop distance is zero, skipping trade")
            return

        risk_amount = position_base * self.risk_per_trade

        # Calculate quantity: risk_amount / stop_distance
        # With leverage, we can control (quantity * price) notional value
        quantity = risk_amount / stop_distance

        # Check if notional value exceeds leverage limits
        notional_value = quantity * signal.entry_price
        max_notional = position_base * current_leverage

        if notional_value > max_notional:
            # Cap the position size to current leverage limit
            quantity = max_notional / signal.entry_price
            logger.warning(f"[RISK] Position capped by {current_leverage}x leverage (${max_notional:,.2f})")

        # Create limit order
        order_id = f"ENTRY_{timestamp}_{signal.direction}"

        order = LimitOrder(
            order_id=order_id,
            order_type='ENTRY',
            direction=signal.direction,
            limit_price=signal.entry_price,
            quantity=quantity,
            created_at=timestamp,
            timeout=180  # 3 minutes timeout for entry
        )

        self.pending_entry_orders.append(order)
        self.order_signals[order_id] = signal  # Store signal for later

        logger.info(f"\n[SIGNAL] {signal.direction} {signal.signal_type}")
        logger.info(f"  Entry (Limit): ${signal.entry_price:,.2f}")
        logger.info(f"  Stop Loss: ${signal.stop_loss:,.2f}")
        logger.info(f"  Take Profit: ${signal.take_profit:,.2f}")
        logger.info(f"  Confidence: {signal.confidence:.0f}%")
        logger.info(f"  Reason: {signal.reason}")

    def _open_position(self, entry_order: LimitOrder, timestamp: int):
        """Open position after entry limit order fills"""
        # Get the signal from the order_signals mapping
        signal = self.order_signals.get(entry_order.order_id)

        pos_id = f"POS_{timestamp}_{entry_order.direction}"

        # Recalculate TP/SL based on ACTUAL filled price, not signal price
        # This ensures consistent risk/reward regardless of fill price
        if signal:
            # Calculate the intended distances from the signal
            signal_stop_distance = abs(signal.stop_loss - signal.entry_price)
            signal_target_distance = abs(signal.take_profit - signal.entry_price)

            # Apply those distances to the actual filled price
            if entry_order.direction == 'LONG':
                stop_loss = entry_order.filled_price - signal_stop_distance
                take_profit = entry_order.filled_price + signal_target_distance
            else:  # SHORT
                stop_loss = entry_order.filled_price + signal_stop_distance
                take_profit = entry_order.filled_price - signal_target_distance
        else:
            # Fallback defaults (should rarely happen)
            if entry_order.direction == 'LONG':
                stop_loss = entry_order.filled_price - 150
                take_profit = entry_order.filled_price + 200
            else:
                stop_loss = entry_order.filled_price + 150
                take_profit = entry_order.filled_price - 200

        # Enable trailing TP for trend continuation trades
        use_trailing = signal.signal_type == 'trend_continuation' if signal else False

        position = BacktestPosition(
            position_id=pos_id,
            direction=entry_order.direction,
            entry_price=entry_order.filled_price,
            entry_time=timestamp,
            quantity=entry_order.quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal=signal,  # Store the signal!
            highest_price=entry_order.filled_price,
            lowest_price=entry_order.filled_price,
            use_trailing_tp=use_trailing
        )

        # Create TP and SL limit orders
        position.tp_order = LimitOrder(
            order_id=f"TP_{pos_id}",
            order_type='TP',
            direction='SELL' if entry_order.direction == 'LONG' else 'BUY',
            limit_price=take_profit,
            quantity=entry_order.quantity,
            created_at=timestamp
        )

        position.sl_order = LimitOrder(
            order_id=f"SL_{pos_id}",
            order_type='SL',
            direction='SELL' if entry_order.direction == 'LONG' else 'BUY',
            limit_price=stop_loss,
            quantity=entry_order.quantity,
            created_at=timestamp
        )

        self.positions.append(position)

        # Deduct entry fees and store in position
        entry_fee = entry_order.filled_price * entry_order.quantity * self.maker_fee
        position.entry_fee = entry_fee
        self.current_capital -= entry_fee
        self.stats.total_fees += entry_fee

        tqdm.write(f"[ENTRY] {entry_order.direction} @ ${entry_order.filled_price:,.0f}")

    def _update_breakeven_stop(self, position: BacktestPosition, current_price: float):
        """
        Move stop loss to breakeven once trade moves significantly in our favor

        Logic:
        - Move SL to breakeven (entry price) once price moves 50% toward target
        - Protects against turning winners into losers (img 090902 issue)
        - Only moves SL once, doesn't trail multiple times
        """
        if not position.sl_order:
            return

        # Check if we've already moved to breakeven
        # For LONG: breakeven means SL >= entry, for SHORT: SL <= entry
        if position.direction == 'LONG':
            if position.stop_loss >= position.entry_price:
                return  # Already at or above breakeven

            # Calculate how far we've moved toward target
            unrealized_pnl = current_price - position.entry_price
            target_distance = position.take_profit - position.entry_price

            # Move to breakeven once 50% to target
            if unrealized_pnl >= target_distance * 0.5:
                old_sl = position.stop_loss
                position.stop_loss = position.entry_price
                position.sl_order.limit_price = position.entry_price
                tqdm.write(f"[BREAKEVEN] LONG SL moved ${old_sl:,.0f} -> ${position.entry_price:,.0f} (breakeven)")

        else:  # SHORT
            if position.stop_loss <= position.entry_price:
                return  # Already at or below breakeven

            # Calculate how far we've moved toward target
            unrealized_pnl = position.entry_price - current_price
            target_distance = position.entry_price - position.take_profit

            # Move to breakeven once 50% to target
            if unrealized_pnl >= target_distance * 0.5:
                old_sl = position.stop_loss
                position.stop_loss = position.entry_price
                position.sl_order.limit_price = position.entry_price
                tqdm.write(f"[BREAKEVEN] SHORT SL moved ${old_sl:,.0f} -> ${position.entry_price:,.0f} (breakeven)")

    def _update_trailing_tp(self, position: BacktestPosition, current_price: float):
        """
        Update trailing take profit for trend continuation trades

        Logic:
        - Activate trailing once price moves 50% toward TP
        - Trail TP to lock in 60% of unrealized profit
        - Never move TP closer (only further)
        """
        if not position.tp_order:
            return

        # Calculate unrealized P&L
        if position.direction == 'LONG':
            unrealized_pnl = current_price - position.entry_price
            target_distance = position.take_profit - position.entry_price

            # Activate trailing once we're 50% to target
            if not position.trailing_activated:
                if unrealized_pnl >= target_distance * 0.5:
                    position.trailing_activated = True
                    tqdm.write(f"[TRAILING] LONG trailing activated @ ${current_price:,.0f} (50% to target)")

            # Trail TP if activated
            if position.trailing_activated:
                # Lock in 60% of unrealized profit
                new_tp = position.entry_price + (unrealized_pnl * 0.6)

                # Only move TP up (never down)
                if new_tp > position.take_profit:
                    old_tp = position.take_profit
                    position.take_profit = new_tp
                    position.tp_order.limit_price = new_tp
                    tqdm.write(f"[TRAILING] LONG TP moved ${old_tp:,.0f} -> ${new_tp:,.0f}")

        else:  # SHORT
            unrealized_pnl = position.entry_price - current_price
            target_distance = position.entry_price - position.take_profit

            # Activate trailing once we're 50% to target
            if not position.trailing_activated:
                if unrealized_pnl >= target_distance * 0.5:
                    position.trailing_activated = True
                    tqdm.write(f"[TRAILING] SHORT trailing activated @ ${current_price:,.0f} (50% to target)")

            # Trail TP if activated
            if position.trailing_activated:
                # Lock in 60% of unrealized profit
                new_tp = position.entry_price - (unrealized_pnl * 0.6)

                # Only move TP down (never up)
                if new_tp < position.take_profit:
                    old_tp = position.take_profit
                    position.take_profit = new_tp
                    position.tp_order.limit_price = new_tp
                    tqdm.write(f"[TRAILING] SHORT TP moved ${old_tp:,.0f} -> ${new_tp:,.0f}")

    def _close_position(self, position: BacktestPosition, timestamp: int, exit_price: float, reason: str):
        """Close position"""
        position.exit_price = exit_price
        position.exit_time = timestamp
        position.exit_reason = reason

        # Calculate P&L
        if position.direction == 'LONG':
            pnl = (exit_price - position.entry_price) * position.quantity
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * position.quantity

        pnl_pct = (pnl / (position.entry_price * position.quantity)) * 100

        # Deduct exit fees and store in position
        exit_fee = exit_price * position.quantity * self.maker_fee
        net_pnl = pnl - exit_fee

        position.pnl = net_pnl
        position.pnl_pct = pnl_pct
        position.exit_fee = exit_fee
        position.total_fees = position.entry_fee + exit_fee

        self.current_capital += net_pnl
        self.stats.total_fees += exit_fee

        # Track equity curve for visualization
        if self.current_capital > self.peak_equity:
            self.peak_equity = self.current_capital
        drawdown = ((self.peak_equity - self.current_capital) / self.peak_equity) * 100

        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': self.current_capital,
            'drawdown': drawdown,
            'pnl': net_pnl
        })

        # Track day of week statistics
        exit_datetime = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        day_name = exit_datetime.strftime('%A')  # 'Monday', 'Tuesday', etc.

        if day_name in self.stats.trades_by_day:
            if net_pnl > 0:
                self.stats.trades_by_day[day_name]['wins'] += 1
            else:
                self.stats.trades_by_day[day_name]['losses'] += 1
            self.stats.trades_by_day[day_name]['total_pnl'] += net_pnl

        self.closed_trades.append(position)

        # Log trade
        duration_mins = (timestamp - position.entry_time) / 1000 / 60
        tqdm.write(f"[EXIT] {reason} | P&L: ${net_pnl:,.2f} ({pnl_pct:+.2f}%)")

    def _close_all_positions(self, last_bar, reason: str):
        """Force close all positions at end of backtest"""
        timestamp = int(last_bar['timestamp'].timestamp() * 1000)
        close_price = float(last_bar['close'])

        for pos in self.positions[:]:
            self._close_position(pos, timestamp, close_price, reason)
            self.positions.remove(pos)

    def _calculate_stats(self):
        """Calculate performance statistics"""
        if not self.closed_trades:
            logger.warning("[STATS] No closed trades to analyze")
            return

        self.stats.total_trades = len(self.closed_trades)

        wins = [t for t in self.closed_trades if t.pnl > 0]
        losses = [t for t in self.closed_trades if t.pnl <= 0]

        self.stats.winning_trades = len(wins)
        self.stats.losing_trades = len(losses)
        self.stats.total_pnl = sum(t.pnl for t in self.closed_trades)
        # Net P&L should be actual capital change, not sum of trades
        self.stats.net_pnl = self.current_capital - self.initial_capital

        if self.stats.total_trades > 0:
            self.stats.win_rate = (self.stats.winning_trades / self.stats.total_trades) * 100

        if wins:
            self.stats.avg_win = sum(t.pnl for t in wins) / len(wins)
            self.stats.largest_win = max(t.pnl for t in wins)

        if losses:
            self.stats.avg_loss = sum(t.pnl for t in losses) / len(losses)
            self.stats.largest_loss = min(t.pnl for t in losses)

        # Average trade duration
        durations = [(t.exit_time - t.entry_time) / 1000 / 60 for t in self.closed_trades if t.exit_time]
        if durations:
            self.stats.avg_trade_duration = sum(durations) / len(durations)

    def _save_results(self):
        """Save backtest results to JSON"""
        timestamp = int(datetime.now(timezone.utc).timestamp())
        results_file = self.results_dir / f'vwap_backtest_{self.symbol}_{timestamp}.json'

        # Prepare trade data
        trades_data = []
        for trade in self.closed_trades:
            # Extract signal data if available
            signal_data = None
            if trade.signal:
                signal_data = {
                    'signal_type': trade.signal.signal_type,
                    'confidence': trade.signal.confidence,
                    'reason': trade.signal.reason,
                    'vwap_band': float(trade.signal.vwap_band) if trade.signal.vwap_band else None,
                    'htf_confluence': trade.signal.htf_confluence
                }

                # Add SR zone data if available
                if trade.signal.sr_zone:
                    signal_data['sr_zone'] = {
                        'level': float(trade.signal.sr_zone.level),
                        'upper': float(trade.signal.sr_zone.upper),
                        'lower': float(trade.signal.sr_zone.lower),
                        'zone_type': trade.signal.sr_zone.zone_type,
                        'strength': trade.signal.sr_zone.strength,
                        'timeframe': trade.signal.sr_zone.timeframe,
                        'invalidated': trade.signal.sr_zone.invalidated
                    }

            trades_data.append({
                'position_id': trade.position_id,
                'direction': trade.direction,
                'entry_price': float(trade.entry_price),
                'entry_time': trade.entry_time,
                'exit_price': float(trade.exit_price) if trade.exit_price else None,
                'exit_time': trade.exit_time,
                'exit_reason': trade.exit_reason,
                'quantity': float(trade.quantity),
                'pnl': float(trade.pnl) if trade.pnl else None,
                'pnl_pct': float(trade.pnl_pct) if trade.pnl_pct else None,
                'entry_fee': float(trade.entry_fee) if trade.entry_fee else None,
                'exit_fee': float(trade.exit_fee) if trade.exit_fee else None,
                'total_fees': float(trade.total_fees) if trade.total_fees else None,
                'stop_loss': float(trade.stop_loss),
                'take_profit': float(trade.take_profit),
                'duration_minutes': (trade.exit_time - trade.entry_time) / 1000 / 60 if trade.exit_time else None,
                'signal': signal_data  # Include signal and SR zone data
            })

        # Prepare results
        results = {
            'backtest_config': {
                'symbol': self.symbol,
                'timeframe': self.timeframe,
                'initial_capital': self.initial_capital,
                'leverage': self.leverage,
                'max_position_size': self.initial_capital * self.leverage,
                'final_capital': float(self.current_capital),
                'risk_per_trade': self.risk_per_trade,
                'maker_fee': self.maker_fee,
                'ml_enabled': self.ml_enabled,
                'ml_min_win_prob': self.ml_optimizer.min_win_probability if self.ml_enabled else None
            },
            'ml_filtering_stats': {
                'ml_enabled': self.ml_enabled,
                'signals_evaluated': self.ml_signals_evaluated,
                'signals_filtered': self.ml_filtered_count,
                'signals_approved': self.ml_signals_evaluated - self.ml_filtered_count if self.ml_enabled else 0,
                'filter_rate': (self.ml_filtered_count / self.ml_signals_evaluated * 100) if self.ml_signals_evaluated > 0 else 0
            },
            'performance': {
                'total_trades': self.stats.total_trades,
                'winning_trades': self.stats.winning_trades,
                'losing_trades': self.stats.losing_trades,
                'win_rate': float(self.stats.win_rate),
                'total_pnl': float(self.stats.total_pnl),
                'total_fees': float(self.stats.total_fees),
                'net_pnl': float(self.stats.net_pnl),
                'return_pct': ((self.current_capital - self.initial_capital) / self.initial_capital) * 100,
                'avg_win': float(self.stats.avg_win),
                'avg_loss': float(self.stats.avg_loss),
                'largest_win': float(self.stats.largest_win),
                'largest_loss': float(self.stats.largest_loss),
                'avg_trade_duration_minutes': float(self.stats.avg_trade_duration),
                'trades_by_day': self.stats.trades_by_day
            },
            'order_stats': {
                'entry_fills': self.stats.entry_fills,
                'entry_timeouts': self.stats.entry_timeouts,
                'tp_fills': self.stats.tp_fills,
                'sl_fills': self.stats.sl_fills
            },
            'trades': trades_data,
            'equity_curve': self.equity_curve
        }

        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"\n[RESULTS] Saved to: {results_file}")

        # Also save detailed CSV for trade analysis
        self._save_trades_csv(timestamp)

        return str(results_file)

    def _save_trades_csv(self, timestamp: int):
        """Save detailed trade log to CSV with IST timestamps"""
        import csv
        from datetime import datetime, timezone, timedelta

        csv_file = self.results_dir / f'trades_vwap_{self.symbol}_{timestamp}.csv'

        # IST is UTC+5:30
        ist_offset = timedelta(hours=5, minutes=30)

        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'Trade_ID',
                'Entry_Day',
                'Entry_Date_IST',
                'Entry_Time_IST',
                'Entry_DateTime_UTC',
                'Direction',
                'Signal_Type',
                'Entry_Price',
                'Exit_Price',
                'Exit_Day',
                'Exit_Date_IST',
                'Exit_Time_IST',
                'Exit_DateTime_UTC',
                'Exit_Reason',
                'Quantity',
                'Stop_Loss',
                'Take_Profit',
                'PNL_$',
                'PNL_%',
                'Fees_$',
                'Net_PNL_$',
                'Duration_Minutes',
                'Highest_Price',
                'Lowest_Price',
                'Confidence_%',
                'Signal_Reason',
                'VWAP_Band',
                'SR_Zone_Center',
                'SR_Zone_Type',
                'SR_Zone_Strength'
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for i, trade in enumerate(self.closed_trades, 1):
                # Convert entry time to IST
                entry_utc = datetime.fromtimestamp(trade.entry_time / 1000, tz=timezone.utc)
                entry_ist = entry_utc + ist_offset

                # Convert exit time to IST
                exit_utc = datetime.fromtimestamp(trade.exit_time / 1000, tz=timezone.utc) if trade.exit_time else None
                exit_ist = (exit_utc + ist_offset) if exit_utc else None

                # Calculate fees (entry + exit)
                fees = (trade.entry_price * trade.quantity * self.maker_fee * 2) # Entry + Exit

                # Get signal information
                signal_reason = trade.signal.reason if trade.signal else "N/A"
                confidence = trade.signal.confidence if trade.signal else 0
                vwap_band = f"${trade.signal.vwap_band:,.2f}" if trade.signal else "N/A"
                sr_zone_center = f"${trade.signal.sr_zone.level:,.2f}" if (trade.signal and trade.signal.sr_zone) else "N/A"
                sr_zone_type = trade.signal.sr_zone.zone_type if (trade.signal and trade.signal.sr_zone) else "N/A"
                sr_zone_strength = trade.signal.sr_zone.strength if (trade.signal and trade.signal.sr_zone) else "N/A"

                row = {
                    'Trade_ID': i,
                    'Entry_Day': entry_ist.strftime('%A'),
                    'Entry_Date_IST': entry_ist.strftime('%Y-%m-%d'),
                    'Entry_Time_IST': entry_ist.strftime('%H:%M:%S'),
                    'Entry_DateTime_UTC': entry_utc.strftime('%Y-%m-%d %H:%M:%S'),
                    'Direction': trade.direction,
                    'Signal_Type': trade.signal.signal_type if trade.signal else "N/A",
                    'Entry_Price': f"{trade.entry_price:.2f}",
                    'Exit_Price': f"{trade.exit_price:.2f}" if trade.exit_price else "N/A",
                    'Exit_Day': exit_ist.strftime('%A') if exit_ist else "N/A",
                    'Exit_Date_IST': exit_ist.strftime('%Y-%m-%d') if exit_ist else "N/A",
                    'Exit_Time_IST': exit_ist.strftime('%H:%M:%S') if exit_ist else "N/A",
                    'Exit_DateTime_UTC': exit_utc.strftime('%Y-%m-%d %H:%M:%S') if exit_utc else "N/A",
                    'Exit_Reason': trade.exit_reason or "N/A",
                    'Quantity': f"{trade.quantity:.4f}",
                    'Stop_Loss': f"{trade.stop_loss:.2f}",
                    'Take_Profit': f"{trade.take_profit:.2f}",
                    'PNL_$': f"{trade.pnl:.2f}" if trade.pnl else "0.00",
                    'PNL_%': f"{trade.pnl_pct:.2f}" if trade.pnl_pct else "0.00",
                    'Fees_$': f"{fees:.2f}",
                    'Net_PNL_$': f"{(trade.pnl - fees):.2f}" if trade.pnl else f"{-fees:.2f}",
                    'Duration_Minutes': f"{((trade.exit_time - trade.entry_time) / 1000 / 60):.1f}" if trade.exit_time else "N/A",
                    'Highest_Price': f"{trade.highest_price:.2f}",
                    'Lowest_Price': f"{trade.lowest_price:.2f}",
                    'Confidence_%': f"{confidence:.0f}",
                    'Signal_Reason': signal_reason,
                    'VWAP_Band': vwap_band,
                    'SR_Zone_Center': sr_zone_center,
                    'SR_Zone_Type': sr_zone_type,
                    'SR_Zone_Strength': sr_zone_strength
                }

                writer.writerow(row)

        logger.info(f"[CSV] Detailed trade log saved to: {csv_file}")

    def _display_results(self):
        """Display backtest results"""
        logger.info(f"\n{'='*80}")
        logger.info("BACKTEST RESULTS")
        logger.info(f"{'='*80}")
        logger.info(f"\nCapital:")
        logger.info(f"  Initial: ${self.initial_capital:,.2f}")
        logger.info(f"  Final: ${self.current_capital:,.2f}")
        logger.info(f"  Net P&L: ${self.stats.net_pnl:,.2f}")
        logger.info(f"  Return: {((self.current_capital - self.initial_capital) / self.initial_capital) * 100:.2f}%")

        logger.info(f"\nTrade Statistics:")
        logger.info(f"  Total Trades: {self.stats.total_trades}")
        logger.info(f"  Winning: {self.stats.winning_trades}")
        logger.info(f"  Losing: {self.stats.losing_trades}")
        logger.info(f"  Win Rate: {self.stats.win_rate:.2f}%")
        logger.info(f"  Avg Win: ${self.stats.avg_win:,.2f}")
        logger.info(f"  Avg Loss: ${self.stats.avg_loss:,.2f}")
        logger.info(f"  Largest Win: ${self.stats.largest_win:,.2f}")
        logger.info(f"  Largest Loss: ${self.stats.largest_loss:,.2f}")
        logger.info(f"  Avg Duration: {self.stats.avg_trade_duration:.1f} minutes")

        logger.info(f"\nFees:")
        logger.info(f"  Total Fees: ${self.stats.total_fees:,.2f}")

        logger.info(f"\nOrder Statistics:")
        logger.info(f"  Entry Fills: {self.stats.entry_fills}")
        logger.info(f"  Entry Timeouts: {self.stats.entry_timeouts}")
        logger.info(f"  TP Fills: {self.stats.tp_fills}")
        logger.info(f"  SL Fills: {self.stats.sl_fills}")
        logger.info(f"{'='*80}\n")

    def _klines_to_df(self, klines) -> pd.DataFrame:
        """Convert klines to DataFrame"""
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        return df

    def _resample_ohlcv(self, df: pd.DataFrame, freq: str) -> pd.DataFrame:
        """
        Resample OHLCV data to higher timeframe

        Args:
            df: Source DataFrame with columns [timestamp, open, high, low, close, volume]
            freq: Pandas frequency string ('5T' for 5min, '15T' for 15min)

        Returns:
            Resampled DataFrame
        """
        df_resampled = df.set_index('timestamp').resample(freq).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        df_resampled.reset_index(inplace=True)
        return df_resampled

    def _timeframe_to_ms(self, timeframe: str) -> int:
        """Convert timeframe to milliseconds"""
        units = {'m': 60000, 'h': 3600000, 'd': 86400000}
        return int(timeframe[:-1]) * units[timeframe[-1]]

    def _print_trade_summary(self):
        """Print detailed trade summary to terminal"""
        logger.info(f"\n{'='*100}")
        logger.info("TRADE SUMMARY")
        logger.info(f"{'='*100}\n")

        if not self.closed_trades:
            logger.info("No trades executed.")
            return

        # Print each trade
        for i, trade in enumerate(self.closed_trades, 1):
            # Format entry reason (truncate if too long)
            reason = trade.signal.reason if trade.signal else "N/A"
            if len(reason) > 70:
                reason = reason[:67] + "..."

            # Determine if win or loss (use ASCII for Windows compatibility)
            profit_indicator = "WIN" if trade.pnl > 0 else "LOSS"

            logger.info(f"Trade #{i:3d} | {trade.direction:5s} | Entry: ${trade.entry_price:9,.2f} | Exit: ${trade.exit_price:9,.2f} | "
                       f"P&L: ${trade.pnl:7,.2f} ({trade.pnl_pct:+6.2f}%) {profit_indicator:4s} | {trade.exit_reason:2s}")
            logger.info(f"          Reason: {reason}")
            logger.info("")

        logger.info(f"{'='*100}\n")
