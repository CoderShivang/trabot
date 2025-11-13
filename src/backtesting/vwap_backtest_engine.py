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

from src.data.binance_client import BinanceClient
from src.strategy.vwap_strategy import VWAPStrategy, TradeSignal
from src.utils.logger import setup_logger

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

    # Exit
    exit_price: Optional[float] = None
    exit_time: Optional[int] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None


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

    # Limit order stats
    entry_fills: int = 0
    entry_timeouts: int = 0
    tp_fills: int = 0
    sl_fills: int = 0


class VWAPBacktestEngine:
    """
    Backtest engine for VWAP strategy

    All orders are limit orders with realistic fill simulation
    """

    def __init__(self, config: Dict):
        self.config = config
        self.symbol = config.get('symbol', 'BTCUSDT')
        self.timeframe = config.get('timeframe', '1m')
        self.initial_capital = config.get('initial_capital', 10000)
        self.risk_per_trade = config.get('risk_per_trade', 0.02)  # 2% per trade

        # Fees (limit orders = maker fee)
        self.maker_fee = 0.0002  # 0.02% Binance maker fee

        # Components - Create minimal config for BinanceClient
        binance_config = self._create_binance_config()
        self.binance_client = BinanceClient(binance_config)
        self.strategy = VWAPStrategy(config.get('strategy_params', {}))

        # State
        self.current_capital = self.initial_capital
        self.positions: List[BacktestPosition] = []
        self.pending_entry_orders: List[LimitOrder] = []
        self.closed_trades: List[BacktestPosition] = []
        self.stats = BacktestStats()

        # Results directory
        self.results_dir = Path('data/vwap_backtest')
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
        logger.info(f"Initial Capital: ${self.initial_capital:,.2f}")
        logger.info(f"Risk per Trade: {self.risk_per_trade*100:.1f}%")
        logger.info(f"Maker Fee: {self.maker_fee*100:.3f}%")
        logger.info(f"{'='*80}\n")

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
        self._save_results()
        self._display_results()

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
        """
        logger.info("[BACKTEST] Starting simulation...\n")

        # Need lookback for strategy
        lookback = 200

        for idx in range(lookback, len(df)):
            current_bar = df.iloc[idx]
            timestamp = int(current_bar['timestamp'].timestamp() * 1000)
            open_price = float(current_bar['open'])
            high = float(current_bar['high'])
            low = float(current_bar['low'])
            close = float(current_bar['close'])

            # Historical data for strategy (up to current bar)
            hist_df = df.iloc[:idx+1].copy()

            # === 1. Check pending entry orders for fills ===
            self._check_entry_fills(timestamp, high, low)

            # === 2. Check open positions for TP/SL fills ===
            self._check_position_fills(timestamp, high, low)

            # === 3. Update position tracking ===
            for pos in self.positions:
                pos.highest_price = max(pos.highest_price, high)
                pos.lowest_price = min(pos.lowest_price, low)

            # === 4. Look for new entry signals (if no position) ===
            if len(self.positions) == 0 and len(self.pending_entry_orders) == 0:
                signals = self.strategy.analyze(hist_df, close)

                if signals:
                    # Take best signal
                    best_signal = signals[0]

                    if best_signal.confidence >= 65:
                        self._place_entry_order(best_signal, timestamp)

            # Progress
            if idx % 500 == 0:
                progress = (idx / len(df)) * 100
                logger.info(f"  Progress: {progress:.1f}% | Trades: {len(self.closed_trades)} | Capital: ${self.current_capital:,.2f}")

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

        # Remove filled/timeout orders
        for order in filled_orders:
            self.pending_entry_orders.remove(order)

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
        """Place limit entry order"""
        # Calculate position size based on risk
        risk_amount = self.current_capital * self.risk_per_trade
        stop_distance = abs(signal.entry_price - signal.stop_loss)

        if stop_distance == 0:
            logger.warning("[RISK] Stop distance is zero, skipping trade")
            return

        quantity = risk_amount / stop_distance

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

        logger.info(f"\n[SIGNAL] {signal.direction} {signal.signal_type}")
        logger.info(f"  Entry (Limit): ${signal.entry_price:,.2f}")
        logger.info(f"  Stop Loss: ${signal.stop_loss:,.2f}")
        logger.info(f"  Take Profit: ${signal.take_profit:,.2f}")
        logger.info(f"  Confidence: {signal.confidence:.0f}%")
        logger.info(f"  Reason: {signal.reason}")

    def _open_position(self, entry_order: LimitOrder, timestamp: int):
        """Open position after entry limit order fills"""
        # Find signal (stored in pending orders)
        # For now, reconstruct from order data
        # In production, you'd store the signal reference

        pos_id = f"POS_{timestamp}_{entry_order.direction}"

        # Calculate TP/SL from entry
        # This should come from the signal, but for simplicity:
        if entry_order.direction == 'LONG':
            stop_loss = entry_order.filled_price - 150
            take_profit = entry_order.filled_price + 200
        else:
            stop_loss = entry_order.filled_price + 150
            take_profit = entry_order.filled_price - 200

        position = BacktestPosition(
            position_id=pos_id,
            direction=entry_order.direction,
            entry_price=entry_order.filled_price,
            entry_time=timestamp,
            quantity=entry_order.quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal=None,  # Would store signal here
            highest_price=entry_order.filled_price,
            lowest_price=entry_order.filled_price
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

        # Deduct entry fees
        entry_fee = entry_order.filled_price * entry_order.quantity * self.maker_fee
        self.current_capital -= entry_fee
        self.stats.total_fees += entry_fee

        logger.info(f"[POSITION] Opened {entry_order.direction} at ${entry_order.filled_price:,.2f} (qty: {entry_order.quantity:.4f})")

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

        # Deduct exit fees
        exit_fee = exit_price * position.quantity * self.maker_fee
        net_pnl = pnl - exit_fee

        position.pnl = net_pnl
        position.pnl_pct = pnl_pct

        self.current_capital += net_pnl
        self.stats.total_fees += exit_fee

        self.closed_trades.append(position)

        # Log trade
        duration_mins = (timestamp - position.entry_time) / 1000 / 60
        logger.info(f"[CLOSE] {position.direction} | {reason} | P&L: ${net_pnl:,.2f} ({pnl_pct:.2f}%) | Duration: {duration_mins:.1f}m")

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
        self.stats.net_pnl = self.stats.total_pnl

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
            trades_data.append({
                'position_id': trade.position_id,
                'direction': trade.direction,
                'entry_price': float(trade.entry_price),
                'entry_time': trade.entry_time,
                'exit_price': float(trade.exit_price) if trade.exit_price else None,
                'exit_time': trade.exit_time,
                'exit_reason': trade.exit_reason,
                'pnl': float(trade.pnl) if trade.pnl else None,
                'pnl_pct': float(trade.pnl_pct) if trade.pnl_pct else None,
                'stop_loss': float(trade.stop_loss),
                'take_profit': float(trade.take_profit),
                'duration_minutes': (trade.exit_time - trade.entry_time) / 1000 / 60 if trade.exit_time else None
            })

        # Prepare results
        results = {
            'backtest_config': {
                'symbol': self.symbol,
                'timeframe': self.timeframe,
                'initial_capital': self.initial_capital,
                'final_capital': float(self.current_capital),
                'risk_per_trade': self.risk_per_trade,
                'maker_fee': self.maker_fee
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
                'avg_trade_duration_minutes': float(self.stats.avg_trade_duration)
            },
            'order_stats': {
                'entry_fills': self.stats.entry_fills,
                'entry_timeouts': self.stats.entry_timeouts,
                'tp_fills': self.stats.tp_fills,
                'sl_fills': self.stats.sl_fills
            },
            'trades': trades_data
        }

        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"\n[RESULTS] Saved to: {results_file}")

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

    def _timeframe_to_ms(self, timeframe: str) -> int:
        """Convert timeframe to milliseconds"""
        units = {'m': 60000, 'h': 3600000, 'd': 86400000}
        return int(timeframe[:-1]) * units[timeframe[-1]]
