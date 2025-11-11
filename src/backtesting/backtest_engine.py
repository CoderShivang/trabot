"""
Backtesting engine that uses REAL Binance historical data
with simulated order execution for strategy validation.
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import json
from pathlib import Path
import pandas as pd
import numpy as np

from data.binance_client import BinanceClient
from data.orderbook import OrderBookDepth, PriceLevel
from strategy.clc_engine import CLCEngine, CLCScore
from strategy.context_analyzer import ContextAnalyzer
from strategy.location_detector import LocationDetector
from strategy.confirmation import ConfirmationAnalyzer
from strategy.big_orders import BigOrdersDetector
from learning.feedback_system import AdaptiveFeedbackSystem
from utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class BacktestPosition:
    """Simulated position for backtesting"""
    symbol: str
    direction: str
    entry_price: float
    entry_time: int
    quantity: float
    stop_loss: float
    take_profit: float
    clc_score: Dict
    current_price: float = 0.0
    exit_price: Optional[float] = None
    exit_time: Optional[int] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None
    fees: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = float('inf')
    partial_exits: List[Dict] = field(default_factory=list)
    remaining_quantity: float = 0.0

    def __post_init__(self):
        self.remaining_quantity = self.quantity
        self.highest_price = self.entry_price if self.direction == "LONG" else self.entry_price
        self.lowest_price = self.entry_price if self.direction == "SHORT" else self.entry_price


@dataclass
class BacktestMetrics:
    """Performance metrics from backtest"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    avg_trade_duration_minutes: float = 0.0
    trades_per_day: float = 0.0
    roi_pct: float = 0.0
    expectancy: float = 0.0

    # Trade distribution
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0

    # Time-based metrics
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_days: float = 0.0

    # Risk metrics
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    avg_risk_reward: float = 0.0


class BacktestEngine:
    """
    Backtesting engine using real Binance historical data.

    Fetches:
    - Historical klines (OHLCV) for context/location
    - Historical trades (order flow) for confirmation

    Simulates:
    - Orderbook state from trades
    - Position management with real slippage
    - Fee calculation
    """

    def __init__(self, config, offline_mode=False):
        self.config = config
        self.binance_client = None
        self.offline_mode = offline_mode  # Use cached data instead of API
        self.starting_balance = 100.0  # $100 starting capital
        self.current_balance = self.starting_balance

        # Strategy components
        self.feedback_system = None
        self.context_analyzer = None
        self.location_detector = None
        self.confirmation_analyzer = None
        self.big_orders_detector = None
        self.clc_engine = None

        # Backtest state
        self.positions: Dict[str, BacktestPosition] = {}
        self.closed_trades: List[Dict] = []
        self.equity_curve: List[Tuple[int, float]] = []
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.max_consecutive_losses = 0
        self.last_trade_time = {}

        # Historical data cache
        self.klines_cache = {}
        self.trades_cache = {}

    async def initialize(self):
        """Initialize backtesting components"""
        logger.info("[BACKTEST] Initializing components...")

        # CRITICAL: Use force_mainnet_data=True to fetch REAL market data
        # Backtests must use real BTC/USDT Perpetual Futures data, not testnet
        if self.offline_mode:
            # Offline mode: Create mock client, no API connection needed
            logger.info("[BACKTEST] Offline mode - will use cached data only")
            self.binance_client = BinanceClient(self.config, force_mainnet_data=True, backtest_mode=True)
            # Don't connect in offline mode
        else:
            # Online mode: Connect to API to fetch data
            self.binance_client = BinanceClient(self.config, force_mainnet_data=True, backtest_mode=False)
            await self.binance_client.connect(skip_ping=True)  # Skip ping to avoid geo-restrictions

        self.feedback_system = AdaptiveFeedbackSystem(self.config)
        self.context_analyzer = ContextAnalyzer(self.config, self.binance_client)
        self.location_detector = LocationDetector(self.config, self.binance_client, self.feedback_system)
        self.confirmation_analyzer = ConfirmationAnalyzer(self.config, self.binance_client)
        self.big_orders_detector = BigOrdersDetector(self.config, self.binance_client)
        self.clc_engine = CLCEngine(
            self.config,
            self.context_analyzer,
            self.location_detector,
            self.confirmation_analyzer,
            self.big_orders_detector,
            self.feedback_system
        )

        logger.info("[BACKTEST] All components ready")

    async def run_backtest(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1m'
    ) -> BacktestMetrics:
        """
        Run backtest on historical data.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            start_date: Start of backtest period
            end_date: End of backtest period
            timeframe: Candle timeframe for execution ('1m', '5m')

        Returns:
            BacktestMetrics with performance summary
        """
        logger.info(f"[BACKTEST] Starting backtest for {symbol}")
        logger.info(f"[BACKTEST] Period: {start_date} to {end_date}")
        logger.info(f"[BACKTEST] Timeframe: {timeframe}")

        # Load historical data
        logger.info("[BACKTEST] Loading historical data...")
        await self._load_historical_data(symbol, start_date, end_date, timeframe)

        # Get klines for iteration
        klines = self.klines_cache[symbol][timeframe]
        logger.info(f"[BACKTEST] Loaded {len(klines)} candles")

        # Iterate through each candle
        total_candles = len(klines)
        for i, kline in enumerate(klines):
            if i % 100 == 0:
                progress = (i / total_candles) * 100
                logger.info(f"[BACKTEST] Progress: {progress:.1f}% ({i}/{total_candles} candles), Trades: {len(self.closed_trades)}")

            # Extract candle data
            timestamp = int(kline[0])
            open_price = float(kline[1])
            high_price = float(kline[2])
            low_price = float(kline[3])
            close_price = float(kline[4])
            volume = float(kline[5])

            current_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)

            # Update existing positions
            await self._update_positions(symbol, high_price, low_price, close_price, timestamp)

            # Check for new entry signals (use close price)
            if self._can_open_position(symbol, timestamp):
                await self._evaluate_entry(symbol, close_price, timestamp, i, klines)

            # Record equity
            self.equity_curve.append((timestamp, self.current_balance))

        logger.info("[BACKTEST] Backtest completed, calculating metrics...")

        # Close any remaining open positions
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            await self._close_position(symbol, float(klines[-1][4]), klines[-1][0], "backtest_end")

        # Calculate metrics
        metrics = self._calculate_metrics(start_date, end_date)

        # Save results
        self._save_backtest_results(metrics)

        return metrics

    def _load_cached_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ):
        """Load historical data from cached JSON file"""
        cache_dir = Path("data/cache")
        cache_filename = f"{symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"
        cache_path = cache_dir / cache_filename

        if not cache_path.exists():
            logger.error(f"[BACKTEST] Cache file not found: {cache_path}")
            logger.error(f"[BACKTEST] Run data downloader first: python src/download_data.py {symbol} --start {start_date.strftime('%Y-%m-%d')} --end {end_date.strftime('%Y-%m-%d')}")
            raise FileNotFoundError(f"Cached data not found: {cache_path}")

        logger.info(f"[BACKTEST] Loading cached data from {cache_path}...")
        with open(cache_path, 'r') as f:
            data = json.load(f)

        # Initialize caches
        if symbol not in self.klines_cache:
            self.klines_cache[symbol] = {}

        # Load timeframe data
        for tf, klines in data['timeframes'].items():
            self.klines_cache[symbol][tf] = klines
            logger.info(f"[BACKTEST] Loaded {len(klines)} {tf} candles from cache")

        # Inject cache into binance_client
        self.binance_client.set_backtest_cache(self.klines_cache)
        logger.info("[BACKTEST] ✓ Cached data loaded successfully")

    async def _load_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ):
        """Load historical klines and trades from Binance or cache"""

        # In offline mode, load from cache
        if self.offline_mode:
            self._load_cached_data(symbol, start_date, end_date)
            return

        # Initialize caches
        if symbol not in self.klines_cache:
            self.klines_cache[symbol] = {}
        if symbol not in self.trades_cache:
            self.trades_cache[symbol] = []

        # Calculate number of candles needed
        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)

        # Convert timeframe to milliseconds
        timeframe_ms = {
            '1m': 60 * 1000,
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '1h': 60 * 60 * 1000
        }[timeframe]

        # Fetch klines in chunks (Binance limit: 1000 per request)
        all_klines = []
        current_start = start_ms

        while current_start < end_ms:
            try:
                # Calculate chunk end time (either 1000 candles ahead or end_ms, whichever is smaller)
                chunk_end = min(current_start + (1000 * timeframe_ms), end_ms)

                klines = await self.binance_client.get_klines(
                    symbol=symbol,
                    interval=timeframe,
                    limit=1000,
                    start_time=current_start,
                    end_time=chunk_end
                )

                if not klines:
                    logger.warning(f"[BACKTEST] No klines returned for {symbol} starting at {current_start}")
                    break

                # Add klines to cache
                all_klines.extend(klines)
                logger.info(f"[BACKTEST] Fetched {len(klines)} candles (total: {len(all_klines)})")

                # Move to next chunk (start after the last candle we received)
                if klines:
                    current_start = klines[-1][0] + timeframe_ms
                else:
                    break

                # Rate limiting to avoid API throttling
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"[BACKTEST] Error loading klines: {e}")
                break

        self.klines_cache[symbol][timeframe] = all_klines

        # Also load higher timeframes for context (15m and 1h)
        for tf in ['15m', '1h']:
            if tf != timeframe and tf not in self.klines_cache[symbol]:
                try:
                    logger.info(f"[BACKTEST] Loading {tf} candles for context...")
                    klines = await self.binance_client.get_klines(
                        symbol=symbol,
                        interval=tf,
                        limit=1000,
                        start_time=start_ms,
                        end_time=end_ms
                    )
                    self.klines_cache[symbol][tf] = klines
                    logger.info(f"[BACKTEST] Loaded {len(klines)} {tf} candles")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"[BACKTEST] Error loading {tf} klines: {e}")

        logger.info(f"[BACKTEST] Loaded {len(all_klines)} {timeframe} candles")

        # Inject cache into binance_client to prevent live API calls during backtest
        self.binance_client.set_backtest_cache(self.klines_cache)

    async def _evaluate_entry(
        self,
        symbol: str,
        current_price: float,
        timestamp: int,
        candle_index: int,
        klines: List
    ):
        """Evaluate if we should enter a trade at this candle"""

        try:
            # Simulate orderbook from recent candles
            orderbook = self._simulate_orderbook(symbol, current_price, klines, candle_index)

            # Simulate recent trades from recent candles
            recent_trades = self._simulate_trades(symbol, klines, candle_index)

            # Update detectors
            self.big_orders_detector.update_trade_history(symbol, recent_trades)
            self.big_orders_detector.update_orderbook_snapshot(symbol, orderbook)

            # Evaluate LONG and SHORT
            long_score = await self.clc_engine.evaluate_trade(
                symbol, "LONG", current_price, orderbook, recent_trades
            )
            short_score = await self.clc_engine.evaluate_trade(
                symbol, "SHORT", current_price, orderbook, recent_trades
            )

            # Log scores for debugging (only log every 100 candles to avoid spam)
            if candle_index % 100 == 0:
                min_conf_signals = self.config.clc_strategy.confirmation.get('min_signals_required', 2) if isinstance(self.config.clc_strategy.confirmation, dict) else 2
                logger.info(f"[BACKTEST] Candle {candle_index} @ ${current_price:.2f}:")
                logger.info(f"  LONG: total={long_score.total_score:.1f}, ctx={long_score.context_score:.1f}, loc={long_score.location_score:.1f}, conf={long_score.confirmation_score:.1f}, big={long_score.big_orders_score:.1f}")
                logger.info(f"    at_location={long_score.at_location}, conf_signals={len(long_score.confirmation_signals)}, location_type={long_score.location_type}")
                logger.info(f"  SHORT: total={short_score.total_score:.1f}, ctx={short_score.context_score:.1f}, loc={short_score.location_score:.1f}, conf={short_score.confirmation_score:.1f}, big={short_score.big_orders_score:.1f}")
                logger.info(f"    at_location={short_score.at_location}, conf_signals={len(short_score.confirmation_signals)}, location_type={short_score.location_type}")
                logger.info(f"  Entry criteria: score>={self.config.scoring.min_entry_score}, at_location=True, conf_signals>={min_conf_signals}")

            # Determine best direction
            best = None
            min_conf_signals = self.config.clc_strategy.confirmation.get('min_signals_required', 2) if isinstance(self.config.clc_strategy.confirmation, dict) else 2
            if long_score.meets_entry_criteria(self.config.scoring.min_entry_score, min_conf_signals):
                best = ("LONG", long_score)
            if short_score.meets_entry_criteria(self.config.scoring.min_entry_score, min_conf_signals):
                if best is None or short_score.total_score > best[1].total_score:
                    best = ("SHORT", short_score)

            if best:
                direction, score = best
                logger.info(f"[BACKTEST] Entry signal: {direction} {symbol} @ {current_price:.2f}, score={score.total_score:.1f}")
                await self._open_position(symbol, direction, current_price, timestamp, score)

        except Exception as e:
            logger.error(f"[BACKTEST] Error evaluating entry: {e}", exc_info=True)

    def _simulate_orderbook(
        self,
        symbol: str,
        current_price: float,
        klines: List,
        candle_index: int
    ) -> OrderBookDepth:
        """
        Simulate orderbook state from recent price action.

        Uses recent candles to estimate bid/ask distribution.
        """
        # Get recent candles (last 10)
        recent_klines = klines[max(0, candle_index - 10):candle_index + 1]

        # Calculate typical spread from recent volatility
        atr = self._calculate_atr([float(k[2]) for k in recent_klines],
                                   [float(k[3]) for k in recent_klines],
                                   [float(k[4]) for k in recent_klines])

        typical_spread = atr * 0.1  # 10% of ATR as typical spread

        # Create simulated orderbook
        orderbook = OrderBookDepth(symbol=symbol, levels={})

        # Simulate 20 price levels above and below
        bids = []
        asks = []

        for i in range(20):
            # Bid side (below current price)
            bid_price = current_price - (typical_spread / 2) - (i * typical_spread * 0.1)
            bid_volume = 1.0 * (1.5 ** (-i/5))  # Exponentially decreasing volume
            bids.append((bid_price, bid_volume))

            # Ask side (above current price)
            ask_price = current_price + (typical_spread / 2) + (i * typical_spread * 0.1)
            ask_volume = 1.0 * (1.5 ** (-i/5))
            asks.append((ask_price, ask_volume))

        orderbook.update_depth(bids, asks)

        return orderbook

    def _simulate_trades(
        self,
        symbol: str,
        klines: List,
        candle_index: int,
        lookback: int = 50
    ) -> List[Dict]:
        """
        Simulate trade flow from candle data.

        Distributes candle volume across price range to simulate trades.
        """
        recent_klines = klines[max(0, candle_index - lookback):candle_index + 1]

        simulated_trades = []

        for kline in recent_klines:
            timestamp = int(kline[0])
            open_price = float(kline[1])
            high_price = float(kline[2])
            low_price = float(kline[3])
            close_price = float(kline[4])
            volume = float(kline[5])

            # Determine if candle was bullish or bearish
            is_bullish = close_price >= open_price

            # Distribute volume across price range
            # Simulate 10 trades per candle
            num_trades = 10
            volume_per_trade = volume / num_trades

            for i in range(num_trades):
                # Random price within candle range
                trade_price = np.random.uniform(low_price, high_price)
                trade_qty = volume_per_trade / trade_price

                # Determine if buyer or seller maker (based on candle direction)
                is_buyer_maker = not is_bullish if np.random.random() > 0.5 else is_bullish

                simulated_trades.append({
                    'price': trade_price,
                    'qty': trade_qty,
                    'isBuyerMaker': is_buyer_maker,
                    'time': timestamp + (i * 6000)  # Distribute across 1-minute candle
                })

        return simulated_trades

    def _calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """Calculate Average True Range"""
        if len(highs) < 2:
            return 0.0

        trs = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
            trs.append(tr)

        if not trs:
            return 0.0

        return sum(trs[-period:]) / min(len(trs), period)

    def _can_open_position(self, symbol: str, timestamp: int) -> bool:
        """Check if we can open a new position"""
        # Already have position in this symbol
        if symbol in self.positions:
            return False

        # Max positions reached
        if len(self.positions) >= self.config.trading.max_positions:
            return False

        # Daily loss limit hit
        if self.daily_pnl <= -self.config.risk.max_daily_loss_usdt:
            return False

        # Cooldown between trades
        last_trade = self.last_trade_time.get(symbol, 0)
        min_cooldown = getattr(self.config.trading, 'min_time_between_trades_seconds', 180)
        if (timestamp - last_trade) < (min_cooldown * 1000):
            return False

        return True

    async def _open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        timestamp: int,
        clc_score: CLCScore
    ):
        """Open a simulated position"""

        # Calculate position size with leverage
        leverage = self.config.trading.leverage
        initial_margin = self.config.trading.position_size_usdt  # e.g., $100
        notional_value = initial_margin * leverage  # e.g., $100 * 100 = $10,000

        # Quantity in BTC (or ETH)
        quantity = notional_value / entry_price

        # Get risk/reward parameters
        if symbol.startswith("BTC"):
            risk_points = self.config.trading.btc_risk_points
            target_points = self.config.trading.btc_target_points
        else:
            risk_points = self.config.trading.eth_risk_points
            target_points = self.config.trading.eth_target_points

        # Calculate stop loss and take profit
        if direction == "LONG":
            stop_loss = entry_price - risk_points
            take_profit = entry_price + target_points
        else:
            stop_loss = entry_price + risk_points
            take_profit = entry_price - target_points

        # Create position
        position = BacktestPosition(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            entry_time=timestamp,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            clc_score=clc_score.__dict__ if hasattr(clc_score, '__dict__') else {},
            current_price=entry_price
        )

        self.positions[symbol] = position
        self.last_trade_time[symbol] = timestamp

        logger.info(f"[BACKTEST] OPEN {direction} {symbol} @ {entry_price:.2f}, qty={quantity:.6f}, SL={stop_loss:.2f}, TP={take_profit:.2f}")

    async def _update_positions(
        self,
        symbol: str,
        high_price: float,
        low_price: float,
        close_price: float,
        timestamp: int
    ):
        """Update open positions and check exit conditions"""

        if symbol not in self.positions:
            return

        pos = self.positions[symbol]

        # Update price tracking
        pos.highest_price = max(pos.highest_price, high_price)
        pos.lowest_price = min(pos.lowest_price, low_price)
        pos.current_price = close_price

        # Check for stop loss or take profit hit within this candle
        exit_reason = None
        exit_price = close_price

        if pos.direction == "LONG":
            # Check if stop loss was hit
            if low_price <= pos.stop_loss:
                exit_reason = "stop_loss"
                exit_price = pos.stop_loss  # Assume filled at stop price

            # Check if take profit was hit
            elif high_price >= pos.take_profit:
                exit_reason = "take_profit"
                exit_price = pos.take_profit

        else:  # SHORT
            # Check if stop loss was hit
            if high_price >= pos.stop_loss:
                exit_reason = "stop_loss"
                exit_price = pos.stop_loss

            # Check if take profit was hit
            elif low_price <= pos.take_profit:
                exit_reason = "take_profit"
                exit_price = pos.take_profit

        # Check for trailing stop (if enabled)
        if self.config.risk.trailing_stop_enabled and exit_reason is None:
            unrealized_pnl = self._calculate_unrealized_pnl(pos, close_price)

            if unrealized_pnl >= self.config.risk.trailing_stop_activation:
                # Activate trailing stop
                if pos.direction == "LONG":
                    trail_stop = pos.highest_price - self.config.risk.trailing_stop_distance
                    pos.stop_loss = max(pos.stop_loss, trail_stop)
                else:
                    trail_stop = pos.lowest_price + self.config.risk.trailing_stop_distance
                    pos.stop_loss = min(pos.stop_loss, trail_stop)

        # Close position if exit triggered
        if exit_reason:
            await self._close_position(symbol, exit_price, timestamp, exit_reason)

    def _calculate_unrealized_pnl(self, pos: BacktestPosition, current_price: float) -> float:
        """Calculate unrealized P&L for position"""
        if pos.direction == "LONG":
            return (current_price - pos.entry_price) * pos.remaining_quantity
        else:
            return (pos.entry_price - current_price) * pos.remaining_quantity

    async def _close_position(
        self,
        symbol: str,
        exit_price: float,
        timestamp: int,
        reason: str
    ):
        """Close a position and record results"""

        if symbol not in self.positions:
            return

        pos = self.positions[symbol]

        # Calculate P&L
        if pos.direction == "LONG":
            pnl = (exit_price - pos.entry_price) * pos.remaining_quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.remaining_quantity

        # Calculate fees (entry + exit)
        fee_rate = self.config.trading.taker_fee_bps / 10000
        entry_fees = pos.entry_price * pos.quantity * fee_rate
        exit_fees = exit_price * pos.remaining_quantity * fee_rate
        total_fees = entry_fees + exit_fees

        net_pnl = pnl - total_fees

        # Update balance
        self.current_balance += net_pnl
        self.daily_pnl += net_pnl

        # Track consecutive wins/losses
        if net_pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)

        # Calculate ROE (Return on Equity) - PnL relative to initial margin
        leverage = self.config.trading.leverage
        initial_margin = self.config.trading.position_size_usdt
        roe_pct = (net_pnl / initial_margin) * 100

        # Record trade
        trade_record = {
            'symbol': symbol,
            'direction': pos.direction,
            'entry_price': pos.entry_price,
            'entry_time': pos.entry_time,
            'exit_price': exit_price,
            'exit_time': timestamp,
            'quantity': pos.quantity,
            'notional_value': pos.entry_price * pos.quantity,
            'initial_margin': initial_margin,
            'leverage': leverage,
            'pnl': pnl,
            'fees': total_fees,
            'net_pnl': net_pnl,
            'pnl_pct': (net_pnl / (pos.entry_price * pos.quantity)) * 100,  # PnL % on notional
            'roe_pct': roe_pct,  # ROE % on margin
            'exit_reason': reason,
            'duration_minutes': (timestamp - pos.entry_time) / 60000,
            'clc_score': pos.clc_score
        }

        self.closed_trades.append(trade_record)

        # Remove position
        del self.positions[symbol]

        logger.info(f"[BACKTEST] CLOSE {pos.direction} {symbol} @ {exit_price:.2f}, P&L: ${net_pnl:+.2f}, reason: {reason}")

    def _calculate_metrics(self, start_date: datetime, end_date: datetime) -> BacktestMetrics:
        """Calculate comprehensive backtest metrics"""

        metrics = BacktestMetrics()

        if not self.closed_trades:
            logger.warning("[BACKTEST] No trades executed during backtest period")
            return metrics

        # Basic counts
        metrics.total_trades = len(self.closed_trades)
        wins = [t for t in self.closed_trades if t['net_pnl'] > 0]
        losses = [t for t in self.closed_trades if t['net_pnl'] <= 0]

        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)
        metrics.win_rate = (len(wins) / len(self.closed_trades)) * 100 if self.closed_trades else 0

        # P&L metrics
        metrics.total_pnl = sum(t['pnl'] for t in self.closed_trades)
        metrics.total_fees = sum(t['fees'] for t in self.closed_trades)
        metrics.net_pnl = sum(t['net_pnl'] for t in self.closed_trades)
        metrics.roi_pct = (metrics.net_pnl / self.starting_balance) * 100

        # Win/Loss averages
        if wins:
            metrics.avg_win = sum(t['net_pnl'] for t in wins) / len(wins)
            metrics.largest_win = max(t['net_pnl'] for t in wins)

        if losses:
            metrics.avg_loss = sum(t['net_pnl'] for t in losses) / len(losses)
            metrics.largest_loss = min(t['net_pnl'] for t in losses)

        # Profit factor
        total_wins = sum(t['net_pnl'] for t in wins) if wins else 0
        total_losses = abs(sum(t['net_pnl'] for t in losses)) if losses else 1
        metrics.profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Expectancy
        metrics.expectancy = metrics.net_pnl / metrics.total_trades if metrics.total_trades > 0 else 0

        # Drawdown
        peak = self.starting_balance
        max_dd = 0

        for timestamp, balance in self.equity_curve:
            if balance > peak:
                peak = balance
            dd = peak - balance
            if dd > max_dd:
                max_dd = dd

        metrics.max_drawdown = max_dd
        metrics.max_drawdown_pct = (max_dd / self.starting_balance) * 100 if self.starting_balance > 0 else 0

        # Sharpe ratio (simplified, daily returns)
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev_balance = self.equity_curve[i - 1][1]
                curr_balance = self.equity_curve[i][1]
                ret = (curr_balance - prev_balance) / prev_balance if prev_balance > 0 else 0
                returns.append(ret)

            if returns:
                avg_return = np.mean(returns)
                std_return = np.std(returns) if len(returns) > 1 else 1
                metrics.sharpe_ratio = (avg_return / std_return) * np.sqrt(252) if std_return > 0 else 0

        # Trade duration
        durations = [t['duration_minutes'] for t in self.closed_trades]
        metrics.avg_trade_duration_minutes = np.mean(durations) if durations else 0

        # Time-based metrics
        metrics.start_time = start_date
        metrics.end_time = end_date
        metrics.duration_days = (end_date - start_date).total_seconds() / 86400
        metrics.trades_per_day = metrics.total_trades / metrics.duration_days if metrics.duration_days > 0 else 0

        # Direction-based metrics
        long_trades = [t for t in self.closed_trades if t['direction'] == 'LONG']
        short_trades = [t for t in self.closed_trades if t['direction'] == 'SHORT']

        metrics.long_trades = len(long_trades)
        metrics.short_trades = len(short_trades)

        if long_trades:
            long_wins = [t for t in long_trades if t['net_pnl'] > 0]
            metrics.long_win_rate = (len(long_wins) / len(long_trades)) * 100

        if short_trades:
            short_wins = [t for t in short_trades if t['net_pnl'] > 0]
            metrics.short_win_rate = (len(short_wins) / len(short_trades)) * 100

        # Risk/reward
        if metrics.avg_loss != 0:
            metrics.avg_risk_reward = abs(metrics.avg_win / metrics.avg_loss)

        # Max consecutive
        metrics.max_consecutive_losses = self.max_consecutive_losses

        return metrics

    def _save_backtest_results(self, metrics: BacktestMetrics):
        """Save backtest results to disk"""

        results_dir = Path('data/backtest_results')
        results_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time())

        # Save metrics
        metrics_dict = {
            'timestamp': timestamp,
            'starting_balance': self.starting_balance,
            'ending_balance': self.current_balance,
            'metrics': {
                'total_trades': metrics.total_trades,
                'winning_trades': metrics.winning_trades,
                'losing_trades': metrics.losing_trades,
                'win_rate': f"{metrics.win_rate:.2f}%",
                'total_pnl': f"${metrics.total_pnl:.2f}",
                'total_fees': f"${metrics.total_fees:.2f}",
                'net_pnl': f"${metrics.net_pnl:.2f}",
                'roi': f"{metrics.roi_pct:.2f}%",
                'avg_win': f"${metrics.avg_win:.2f}",
                'avg_loss': f"${metrics.avg_loss:.2f}",
                'largest_win': f"${metrics.largest_win:.2f}",
                'largest_loss': f"${metrics.largest_loss:.2f}",
                'profit_factor': f"{metrics.profit_factor:.2f}",
                'max_drawdown': f"${metrics.max_drawdown:.2f}",
                'max_drawdown_pct': f"{metrics.max_drawdown_pct:.2f}%",
                'sharpe_ratio': f"{metrics.sharpe_ratio:.2f}",
                'expectancy': f"${metrics.expectancy:.2f}",
                'avg_trade_duration_minutes': f"{metrics.avg_trade_duration_minutes:.1f}",
                'trades_per_day': f"{metrics.trades_per_day:.2f}",
                'long_trades': metrics.long_trades,
                'short_trades': metrics.short_trades,
                'long_win_rate': f"{metrics.long_win_rate:.2f}%",
                'short_win_rate': f"{metrics.short_win_rate:.2f}%",
                'avg_risk_reward': f"{metrics.avg_risk_reward:.2f}",
                'max_consecutive_losses': metrics.max_consecutive_losses,
                'duration_days': f"{metrics.duration_days:.1f}"
            }
        }

        with open(results_dir / f'metrics_{timestamp}.json', 'w') as f:
            json.dump(metrics_dict, f, indent=2, default=str)

        # Save trade log
        with open(results_dir / f'trades_{timestamp}.json', 'w') as f:
            json.dump(self.closed_trades, f, indent=2, default=str)

        # Save equity curve
        equity_df = pd.DataFrame(self.equity_curve, columns=['timestamp', 'balance'])
        equity_df.to_csv(results_dir / f'equity_{timestamp}.csv', index=False)

        logger.info(f"[BACKTEST] Results saved to {results_dir}")
