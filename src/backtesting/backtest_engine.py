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
from backtesting.trade_dashboard import TradeDashboard
from utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class PendingLimitOrder:
    """Pending limit order waiting to be filled"""
    symbol: str
    direction: str
    limit_price: float
    market_price: float  # Price when order was placed
    order_time: int
    quantity: float
    stop_loss: float
    take_profit: float
    clc_score: Dict
    retry_count: int = 0
    order_type: str = "limit"  # 'limit' or 'market' (after timeout)


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
    trailing_active: bool = False  # Track if aggressive trailing is active
    used_limit_order: bool = False  # Track if entry was via limit order (maker fee)

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
        self.trade_dashboard = None

        # Backtest state
        self.positions: Dict[str, BacktestPosition] = {}
        self.pending_orders: Dict[str, PendingLimitOrder] = {}  # Pending limit orders
        self.closed_trades: List[Dict] = []
        self.equity_curve: List[Tuple[int, float]] = []
        self.daily_pnl = 0.0
        self.current_day = None  # Track current day for daily P&L reset
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
        self.trade_dashboard = TradeDashboard(self.config, self.binance_client)

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

        # Pass klines cache to location detector for MTF S/R zone detection
        self.location_detector.klines_cache = self.klines_cache

        # Initialize context analyzer with backtest mode (timestamp will be updated per candle)
        self.context_analyzer.set_backtest_data(self.klines_cache, 0)

        # Get klines for iteration
        klines = self.klines_cache[symbol][timeframe]
        logger.info(f"[BACKTEST] Loaded {len(klines)} candles")

        # PRE-CALCULATE INDICATORS for massive speedup (CRITICAL: use 1h timeframe, not 1m!)
        if symbol in self.klines_cache and '1h' in self.klines_cache[symbol]:
            logger.info(f"[BACKTEST] Pre-calculating indicators for 1h candles (one-time cost)...")
            self._precalculate_indicators(symbol, self.klines_cache[symbol]['1h'])
            logger.info(f"[BACKTEST] [OK] Indicators pre-calculated! Backtest will now run 10-20x faster.")
        else:
            logger.warning(f"[BACKTEST] No 1h klines found, skipping indicator pre-calculation")

        # Iterate through each candle
        total_candles = len(klines)
        logger.info(f"[BACKTEST] Starting backtest for {total_candles} candles...\n")

        # Temporarily suppress verbose logs during backtest loop (only show errors)
        import sys
        import logging as logging_module

        # Disable all logging below ERROR level globally
        # This works even for loggers created during the backtest loop
        logging_module.disable(logging_module.INFO)

        # Progress bar setup
        start_time = datetime.now(timezone.utc)

        for i, kline in enumerate(klines):
            # Update progress bar every candle
            progress = (i + 1) / total_candles * 100
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            candles_per_sec = (i + 1) / elapsed if elapsed > 0 else 0
            eta_seconds = (total_candles - i - 1) / candles_per_sec if candles_per_sec > 0 else 0
            eta_str = f"{int(eta_seconds//60)}m {int(eta_seconds%60)}s" if eta_seconds > 60 else f"{int(eta_seconds)}s"

            # Create progress bar (ASCII characters for Windows compatibility)
            bar_width = 40
            filled = int(bar_width * progress / 100)
            bar = '=' * filled + '-' * (bar_width - filled)

            # Print progress (overwrite same line)
            sys.stdout.write(f"\r[BACKTEST] {bar} {progress:.1f}% | Candle {i+1}/{total_candles} | Trades: {len(self.closed_trades)} | ETA: {eta_str}   ")
            sys.stdout.flush()

            # Extract candle data
            timestamp = int(kline[0])
            open_price = float(kline[1])
            high_price = float(kline[2])
            low_price = float(kline[3])
            close_price = float(kline[4])
            volume = float(kline[5])

            current_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)

            # Reset daily P&L at the start of each new day (UTC midnight)
            current_day = current_time.date()
            if self.current_day is None:
                self.current_day = current_day
            elif current_day != self.current_day:
                # New day started - reset daily P&L
                logger.debug(f"[BACKTEST] New day {current_day}, resetting daily P&L from ${self.daily_pnl:.2f} to $0.00")
                self.daily_pnl = 0.0
                self.current_day = current_day

            # Update context analyzer's current timestamp for this candle
            # This ensures indicators (ADX, ATR, etc.) are calculated from historical data up to this point
            self.context_analyzer.backtest_current_timestamp = timestamp

            # Check and process pending limit orders
            await self._process_pending_orders(symbol, high_price, low_price, close_price, timestamp)

            # Update existing positions
            await self._update_positions(symbol, high_price, low_price, close_price, timestamp)

            # Check for new entry signals (use close price)
            if self._can_open_position(symbol, timestamp):
                await self._evaluate_entry(symbol, close_price, timestamp, i, klines)
                logger.debug(f"[BACKTEST] Completed evaluation for candle {i}")

            # Record equity (sample every 50 candles to reduce memory usage and improve performance)
            if i % 50 == 0 or i == total_candles - 1:
                self.equity_curve.append((timestamp, self.current_balance))

        # Re-enable logging and print newline after progress bar
        logging_module.disable(logging_module.NOTSET)

        # Clear backtest mode from context analyzer
        self.context_analyzer.clear_backtest_mode()

        sys.stdout.write("\n")
        sys.stdout.flush()

        logger.info("[BACKTEST] Backtest completed, calculating metrics...")

        # Close any remaining open positions
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            await self._close_position(symbol, float(klines[-1][4]), klines[-1][0], "backtest_end")

        # Calculate metrics
        metrics = self._calculate_metrics(start_date, end_date)

        # Save results
        self._save_backtest_results(metrics)

        # Generate interactive HTML dashboard
        if self.closed_trades:
            logger.info(f"[BACKTEST] Generating interactive dashboard for {len(self.closed_trades)} trades...")
            # Pass klines cache to dashboard for chart generation
            self.trade_dashboard.klines_cache = self.klines_cache
            dashboard_path = await self.trade_dashboard.generate_dashboard(
                trades=self.closed_trades,
                metrics=metrics,
                start_date=start_date,
                end_date=end_date
            )
            logger.info(f"[BACKTEST] Dashboard ready! Open: {dashboard_path}")

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
        logger.info("[BACKTEST] [OK] Cached data loaded successfully")

    def _save_data_cache(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ):
        """Save fetched data to cache for faster subsequent runs"""
        cache_dir = Path("data/cache")
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_filename = f"{symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"
        cache_path = cache_dir / cache_filename

        # Check if cache already exists
        if cache_path.exists():
            logger.debug(f"[BACKTEST] Cache file already exists: {cache_filename}")
            return

        logger.info(f"[BACKTEST] Saving data to cache: {cache_filename}")

        cache_data = {
            'symbol': symbol,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'timeframes': {}
        }

        # Save all timeframes
        if symbol in self.klines_cache:
            for tf, klines in self.klines_cache[symbol].items():
                cache_data['timeframes'][tf] = klines
                logger.debug(f"[BACKTEST] Caching {len(klines)} {tf} candles")

        with open(cache_path, 'w') as f:
            json.dump(cache_data, f)

        logger.info(f"[BACKTEST] [OK] Data cached successfully! Next run will be 50-100x faster.")
        logger.info(f"[BACKTEST] Cache file: {cache_path}")

    async def _load_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ):
        """Load historical klines and trades from Binance or cache"""

        # Check if cache exists (auto-caching for faster subsequent runs)
        cache_dir = Path("data/cache")
        cache_filename = f"{symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"
        cache_path = cache_dir / cache_filename

        if cache_path.exists():
            logger.info(f"[BACKTEST] Cache found! Loading from {cache_filename} (50-100x faster than API)")
            self._load_cached_data(symbol, start_date, end_date)
            return

        # In offline mode but no cache, error out
        if self.offline_mode:
            logger.error(f"[BACKTEST] Offline mode but cache not found: {cache_path}")
            self._load_cached_data(symbol, start_date, end_date)  # Will raise error
            return

        # Online mode: fetch from API
        logger.info(f"[BACKTEST] No cache found. Fetching from Binance API (this will take ~10 min)...")

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

        # Also load higher timeframes for context (5m, 15m, 1h)
        # CRITICAL: Load historical data BEFORE backtest start for indicator calculation
        # We need at least 500 candles for EMA200 and other indicators
        for tf in ['5m', '15m', '1h']:
            if tf != timeframe and tf not in self.klines_cache[symbol]:
                try:
                    # Calculate how far back to load based on timeframe
                    # Goal: Get ~500 candles of historical data before backtest starts
                    tf_minutes = {
                        '5m': 5,
                        '15m': 15,
                        '1h': 60
                    }[tf]

                    # Load 500 candles before start + backtest period
                    lookback_ms = 500 * tf_minutes * 60 * 1000
                    context_start_ms = start_ms - lookback_ms

                    logger.info(f"[BACKTEST] Loading {tf} candles for context (including {500} historical candles)...")
                    klines = await self.binance_client.get_klines(
                        symbol=symbol,
                        interval=tf,
                        limit=1000,
                        start_time=context_start_ms,  # Start 500 candles before backtest
                        end_time=end_ms
                    )
                    self.klines_cache[symbol][tf] = klines
                    logger.info(f"[BACKTEST] Loaded {len(klines)} {tf} candles (historical + backtest period)")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"[BACKTEST] Error loading {tf} klines: {e}")

        logger.info(f"[BACKTEST] Loaded {len(all_klines)} {timeframe} candles")

        # Save data to cache for faster subsequent runs
        self._save_data_cache(symbol, start_date, end_date)

        # Inject cache into binance_client to prevent live API calls during backtest
        self.binance_client.set_backtest_cache(self.klines_cache)

    def _precalculate_indicators(self, symbol: str, klines: List):
        """
        Pre-calculate all indicators (ADX, ATR, regime) for every timestamp.
        This eliminates redundant calculations during the main backtest loop,
        resulting in 10-20x speedup.
        """
        import pandas as pd
        import numpy as np

        # Convert klines to DataFrame for vectorized operations
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])

        # Convert to numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        # Calculate ADX for all candles
        period = self.config.regime_detection.adx_period

        # True Range
        df['h_l'] = df['high'] - df['low']
        df['h_pc'] = abs(df['high'] - df['close'].shift(1))
        df['l_pc'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['h_l', 'h_pc', 'l_pc']].max(axis=1)

        # Directional Movement
        df['up_move'] = df['high'] - df['high'].shift(1)
        df['down_move'] = df['low'].shift(1) - df['low']
        df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
        df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)

        # Smoothed indicators
        df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
        df['plus_di'] = 100 * df['plus_dm'].ewm(alpha=1/period, adjust=False).mean() / df['atr'].replace(0, 1e-10)
        df['minus_di'] = 100 * df['minus_dm'].ewm(alpha=1/period, adjust=False).mean() / df['atr'].replace(0, 1e-10)

        # DX and ADX
        di_sum = (df['plus_di'] + df['minus_di']).replace(0, 1e-10)
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / di_sum
        df['adx'] = df['dx'].ewm(alpha=1/period, adjust=False).mean()

        # Bollinger Bands
        bb_period = 20
        df['sma'] = df['close'].rolling(window=bb_period).mean()
        df['std'] = df['close'].rolling(window=bb_period).std()
        df['bb_upper'] = df['sma'] + (2 * df['std'])
        df['bb_lower'] = df['sma'] - (2 * df['std'])
        df['bb_width_pct'] = ((df['bb_upper'] - df['bb_lower']) / df['sma'] * 100)

        # Store in cache indexed by timestamp
        self.indicator_cache = {}
        for idx, row in df.iterrows():
            timestamp = int(row['timestamp'])
            self.indicator_cache[timestamp] = {
                'adx': float(row['adx']) if not pd.isna(row['adx']) else 25.0,
                'atr': float(row['atr']) if not pd.isna(row['atr']) else 0.0,
                'bb_width_pct': float(row['bb_width_pct']) if not pd.isna(row['bb_width_pct']) else 0.0,
                'bb_upper': float(row['bb_upper']) if not pd.isna(row['bb_upper']) else row['close'],
                'bb_lower': float(row['bb_lower']) if not pd.isna(row['bb_lower']) else row['close'],
            }

        # Inject cache into context analyzer
        self.context_analyzer.indicator_cache = self.indicator_cache
        logger.debug(f"[BACKTEST] Pre-calculated indicators for {len(self.indicator_cache)} timestamps")

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
            logger.info(f"[BACKTEST] >>> Evaluating candle {candle_index} @ ${current_price:.2f}")
            logger.debug(f"[BACKTEST] >>> _evaluate_entry CALLED for candle {candle_index}")
            # Simulate orderbook from recent candles
            orderbook = self._simulate_orderbook(symbol, current_price, klines, candle_index)

            # Simulate recent trades from recent candles
            recent_trades = self._simulate_trades(symbol, klines, candle_index)

            # Update detectors (trade history is updated inside analyze(), no need to call explicitly)
            self.big_orders_detector.update_orderbook_snapshot(symbol, orderbook)

            # Evaluate LONG and SHORT
            long_score = await self.clc_engine.evaluate_trade(
                symbol, "LONG", current_price, orderbook, recent_trades
            )
            short_score = await self.clc_engine.evaluate_trade(
                symbol, "SHORT", current_price, orderbook, recent_trades
            )

            logger.info(f"[BACKTEST] [OK] Scoring complete for candle {candle_index}: LONG={long_score.total_score:.1f}, SHORT={short_score.total_score:.1f}")
            logger.debug(f"[BACKTEST] Scores calculated for candle {candle_index}")

            # Log scores for debugging (only log every 100 candles to avoid spam)
            if candle_index % 100 == 0:
                min_conf_signals = getattr(self.config.clc_strategy.confirmation, 'min_signals_required', 2)
                logger.info(f"[BACKTEST] Candle {candle_index} @ ${current_price:.2f}:")
                logger.info(f"  LONG: total={long_score.total_score:.1f}, ctx={long_score.context_score:.1f}, loc={long_score.location_score:.1f}, conf={long_score.confirmation_score:.1f}, big={long_score.big_orders_score:.1f}")
                logger.info(f"    at_location={long_score.at_location}, conf_signals={len(long_score.confirmation_signals)}, location_type={long_score.location_type}")
                logger.info(f"  SHORT: total={short_score.total_score:.1f}, ctx={short_score.context_score:.1f}, loc={short_score.location_score:.1f}, conf={short_score.confirmation_score:.1f}, big={short_score.big_orders_score:.1f}")
                logger.info(f"    at_location={short_score.at_location}, conf_signals={len(short_score.confirmation_signals)}, location_type={short_score.location_type}")
                logger.info(f"  Entry criteria: score>={self.config.scoring.min_entry_score}, at_location=True, conf_signals>={min_conf_signals}")

            # Determine best direction
            logger.debug(f"[BACKTEST] Checking entry criteria for candle {candle_index}")
            best = None
            min_conf_signals = getattr(self.config.clc_strategy.confirmation, 'min_signals_required', 2)
            logger.debug(f"[BACKTEST] Checking LONG entry criteria")
            if long_score.meets_entry_criteria(self.config.scoring.min_entry_score, min_conf_signals):
                best = ("LONG", long_score)
                logger.debug(f"[BACKTEST] LONG meets criteria")
            logger.debug(f"[BACKTEST] Checking SHORT entry criteria")
            if short_score.meets_entry_criteria(self.config.scoring.min_entry_score, min_conf_signals):
                if best is None or short_score.total_score > best[1].total_score:
                    best = ("SHORT", short_score)
                    logger.debug(f"[BACKTEST] SHORT meets criteria")

            logger.debug(f"[BACKTEST] Entry criteria check complete, best={best}")
            if best:
                direction, score = best
                logger.info(f"[BACKTEST] Entry signal: {direction} {symbol} @ {current_price:.2f}, score={score.total_score:.1f}")

                # Use limit orders if enabled in config
                use_limits = getattr(self.config.trading, 'use_limit_orders', False)
                if use_limits:
                    await self._place_limit_order(symbol, direction, current_price, timestamp, score)
                else:
                    await self._open_position(symbol, direction, current_price, timestamp, score)

            logger.info(f"[BACKTEST] [DONE] Candle {candle_index} evaluation complete")
            logger.debug(f"[BACKTEST] _evaluate_entry completing for candle {candle_index}")

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

        # Already have pending order for this symbol
        if symbol in self.pending_orders:
            return False

        # Max positions reached (count both positions and pending orders)
        total_exposure = len(self.positions) + len(self.pending_orders)
        if total_exposure >= self.config.trading.max_positions:
            return False

        # Daily loss limit hit (disabled for backtesting - we want to evaluate algorithm regardless of losses)
        # Note: Daily P&L still resets each day, but doesn't block trading
        # Uncomment this line to enable daily loss limits:
        # if self.daily_pnl <= -self.config.risk.max_daily_loss_usdt:
        #     return False

        # Cooldown between trades
        last_trade = self.last_trade_time.get(symbol, 0)
        min_cooldown = getattr(self.config.trading, 'min_time_between_trades_seconds', 180)
        if (timestamp - last_trade) < (min_cooldown * 1000):
            return False

        return True

    async def _place_limit_order(
        self,
        symbol: str,
        direction: str,
        market_price: float,
        timestamp: int,
        clc_score: CLCScore
    ):
        """Place a limit order (simulated) to get maker fees"""

        # Calculate limit order price
        # For LONG: place slightly above market (e.g., at ask) to ensure fill
        # For SHORT: place slightly below market (e.g., at bid)
        offset_bps = getattr(self.config.trading, 'limit_order_offset_bps', 5)  # 0.05% default
        offset_multiplier = offset_bps / 10000  # Convert bps to decimal

        if direction == "LONG":
            # Buy limit: place at or slightly above market to ensure fill
            limit_price = market_price * (1 + offset_multiplier)
        else:
            # Sell limit: place at or slightly below market
            limit_price = market_price * (1 - offset_multiplier)

        # Calculate position parameters
        leverage = self.config.trading.leverage
        initial_margin = self.config.trading.position_size_usdt
        notional_value = initial_margin * leverage
        quantity = notional_value / market_price  # Use market price for quantity calc

        # Get risk/reward parameters
        if symbol.startswith("BTC"):
            risk_points = self.config.trading.btc_risk_points
            target_points = self.config.trading.btc_target_points
        else:
            risk_points = self.config.trading.eth_risk_points
            target_points = self.config.trading.eth_target_points

        # Calculate stop loss and take profit (from limit price)
        if direction == "LONG":
            stop_loss = limit_price - risk_points
            take_profit = limit_price + target_points
        else:
            stop_loss = limit_price + risk_points
            take_profit = limit_price - target_points

        # Get market context for logging
        ctx = await self.context_analyzer.get_context(symbol, "1h", market_price)
        locations = await self.location_detector.get_all_locations(symbol, market_price)

        # Store enhanced CLC score with market context
        enhanced_clc = clc_score.__dict__ if hasattr(clc_score, '__dict__') else {}
        enhanced_clc['market_context'] = {
            'regime': ctx.regime,
            'adx': ctx.adx,
            'vwap': ctx.vwap,
            'ema20': ctx.ema20,
            'ema50': ctx.ema50,
            'ema200': ctx.ema200,
            'bb_upper': ctx.bb_upper,
            'bb_lower': ctx.bb_lower,
            'range_high': ctx.range_high,
            'range_low': ctx.range_low
        }

        # Find nearby S/R zones
        nearby_sr = []
        sr_zones = locations.get('sr_zones', [])
        for zone in sr_zones[:3]:
            dist_pct = abs(market_price - zone.level) / market_price * 100
            if dist_pct < 2.0:
                nearby_sr.append({
                    'level': zone.level,
                    'type': zone.zone_type,
                    'distance_pct': dist_pct,
                    'strength': zone.strength
                })

        enhanced_clc['nearby_sr_zones'] = nearby_sr

        # Create pending limit order
        pending_order = PendingLimitOrder(
            symbol=symbol,
            direction=direction,
            limit_price=limit_price,
            market_price=market_price,
            order_time=timestamp,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            clc_score=enhanced_clc,
            retry_count=0
        )

        self.pending_orders[symbol] = pending_order

        logger.info(f"[BACKTEST] LIMIT ORDER {direction} {symbol}: limit=${limit_price:.2f}, market=${market_price:.2f}, qty={quantity:.6f}, SL={stop_loss:.2f}, TP={take_profit:.2f}")

    async def _process_pending_orders(
        self,
        symbol: str,
        high_price: float,
        low_price: float,
        close_price: float,
        timestamp: int
    ):
        """Check if pending limit orders should fill based on candle action"""

        if symbol not in self.pending_orders:
            return

        order = self.pending_orders[symbol]

        # Check if order would fill
        filled = False
        fill_price = order.limit_price

        if order.direction == "LONG":
            # Buy limit fills if price drops to or below our limit
            if low_price <= order.limit_price:
                filled = True
                # Filled at limit price or better (lower)
                fill_price = order.limit_price
        else:  # SHORT
            # Sell limit fills if price rises to or above our limit
            if high_price >= order.limit_price:
                filled = True
                # Filled at limit price or better (higher)
                fill_price = order.limit_price

        if filled:
            # Order filled! Convert to position
            logger.info(f"[BACKTEST] LIMIT FILLED {order.direction} {symbol} @ {fill_price:.2f} (limit was {order.limit_price:.2f})")

            # Create position from filled limit order
            position = BacktestPosition(
                symbol=symbol,
                direction=order.direction,
                entry_price=fill_price,
                entry_time=timestamp,
                quantity=order.quantity,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                clc_score=order.clc_score,
                current_price=fill_price,
                used_limit_order=True  # Flag for maker fee calculation
            )

            self.positions[symbol] = position
            self.last_trade_time[symbol] = timestamp

            # Remove from pending orders
            del self.pending_orders[symbol]

        else:
            # Check for timeout
            timeout_ms = getattr(self.config.trading, 'limit_order_timeout_seconds', 30) * 1000
            time_elapsed = timestamp - order.order_time

            if time_elapsed >= timeout_ms:
                max_retries = getattr(self.config.trading, 'max_limit_retries', 3)

                if order.retry_count < max_retries:
                    # Retry with new limit price closer to market
                    logger.info(f"[BACKTEST] Limit order timeout, retrying... (attempt {order.retry_count + 1}/{max_retries})")
                    order.retry_count += 1
                    order.order_time = timestamp  # Reset timer

                    # Adjust limit price closer to market (more aggressive)
                    offset_bps = getattr(self.config.trading, 'limit_order_offset_bps', 5)
                    # Make it more aggressive each retry
                    aggressive_offset = offset_bps * (1 + order.retry_count * 0.5)
                    offset_multiplier = aggressive_offset / 10000

                    if order.direction == "LONG":
                        order.limit_price = close_price * (1 + offset_multiplier)
                    else:
                        order.limit_price = close_price * (1 - offset_multiplier)

                    logger.info(f"[BACKTEST] New limit price: ${order.limit_price:.2f} (was ${order.market_price:.2f})")

                else:
                    # Max retries reached, cancel limit and use market order
                    logger.info(f"[BACKTEST] Limit order max retries reached, executing at market price ${close_price:.2f}")

                    # Create position at market price (taker fee will apply)
                    position = BacktestPosition(
                        symbol=symbol,
                        direction=order.direction,
                        entry_price=close_price,
                        entry_time=timestamp,
                        quantity=order.quantity,
                        stop_loss=order.stop_loss,
                        take_profit=order.take_profit,
                        clc_score=order.clc_score,
                        current_price=close_price,
                        used_limit_order=False  # Taker fee applies
                    )

                    self.positions[symbol] = position
                    self.last_trade_time[symbol] = timestamp
                    del self.pending_orders[symbol]

    async def _open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        timestamp: int,
        clc_score: CLCScore
    ):
        """Open a simulated position (market order - taker fees)"""

        # Calculate position size with leverage
        leverage = self.config.trading.leverage
        initial_margin = self.config.trading.position_size_usdt  # e.g., $100
        notional_value = initial_margin * leverage  # e.g., $100 * 50 = $5,000

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

        # Get current market context for detailed logging
        ctx = await self.context_analyzer.get_context(symbol, "1h", entry_price)
        locations = await self.location_detector.get_all_locations(symbol, entry_price)

        # Store enhanced CLC score with market context
        enhanced_clc = clc_score.__dict__ if hasattr(clc_score, '__dict__') else {}
        enhanced_clc['market_context'] = {
            'regime': ctx.regime,
            'adx': ctx.adx,
            'vwap': ctx.vwap,
            'ema20': ctx.ema20,
            'ema50': ctx.ema50,
            'ema200': ctx.ema200,
            'bb_upper': ctx.bb_upper,
            'bb_lower': ctx.bb_lower,
            'range_high': ctx.range_high,
            'range_low': ctx.range_low
        }

        # Find nearby S/R zones
        nearby_sr = []
        sr_zones = locations.get('sr_zones', [])
        for zone in sr_zones[:3]:  # Top 3 zones
            dist_pct = abs(entry_price - zone.level) / entry_price * 100
            if dist_pct < 2.0:  # Within 2%
                nearby_sr.append({
                    'level': zone.level,
                    'type': zone.zone_type,
                    'distance_pct': dist_pct,
                    'strength': zone.strength
                })

        enhanced_clc['nearby_sr_zones'] = nearby_sr

        # Create position
        position = BacktestPosition(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            entry_time=timestamp,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            clc_score=enhanced_clc,
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

        # ADAPTIVE EXIT LOGIC
        if exit_reason is None:
            unrealized_pnl = self._calculate_unrealized_pnl(pos, close_price)
            trade_duration_minutes = (timestamp - pos.entry_time) / 60000

            # 1) EARLY EXIT: Cut losers early before full SL hit
            if hasattr(self.config, 'adaptive_exits') and self.config.adaptive_exits.early_exit_enabled:
                threshold_time = self.config.adaptive_exits.early_exit_time_threshold
                loss_threshold = self.config.adaptive_exits.early_exit_loss_threshold

                # Calculate max acceptable loss (based on risk amount)
                if symbol.startswith("BTC"):
                    max_risk = self.config.trading.btc_risk_points * pos.quantity
                else:
                    max_risk = self.config.trading.eth_risk_points * pos.quantity

                # If losing > 50% of risk after 30 minutes, exit early
                if trade_duration_minutes > threshold_time and unrealized_pnl < -(max_risk * loss_threshold):
                    exit_reason = "early_exit_loss"
                    exit_price = close_price
                    logger.info(f"[BACKTEST] Early exit triggered: {unrealized_pnl:.2f} loss after {trade_duration_minutes:.1f}min")

            # 2) PARTIAL PROFIT TAKING: Take 50% profit at TP, trail the rest
            if hasattr(self.config, 'adaptive_exits') and self.config.adaptive_exits.partial_tp_enabled:
                partial_at_target = self.config.adaptive_exits.partial_tp_at_target
                partial_percentage = self.config.adaptive_exits.partial_tp_percentage

                # Calculate target profit (in dollars)
                if symbol.startswith("BTC"):
                    target_profit = self.config.trading.btc_target_points * pos.quantity
                else:
                    target_profit = self.config.trading.eth_target_points * pos.quantity

                # If profit >= target and haven't taken partial yet
                if unrealized_pnl >= (target_profit * partial_at_target) and pos.remaining_quantity == pos.quantity:
                    # Take partial profit
                    partial_qty = pos.quantity * partial_percentage
                    pos.remaining_quantity = pos.quantity - partial_qty

                    logger.info(f"[BACKTEST] Partial TP: Closed {partial_percentage*100}% at ${close_price:.2f}, P&L: +${unrealized_pnl*partial_percentage:.2f}")

                    # Now activate aggressive trailing for remaining position
                    pos.trailing_active = True

            # 3) ADAPTIVE TRAILING: Trail winners past TP
            if hasattr(self.config, 'adaptive_exits') and self.config.adaptive_exits.trail_past_tp:
                activation_multiple = self.config.adaptive_exits.trail_activation_multiple
                trail_distance_pct = self.config.adaptive_exits.trail_distance_pct

                # Calculate target profit
                if symbol.startswith("BTC"):
                    target_profit = self.config.trading.btc_target_points * pos.quantity
                else:
                    target_profit = self.config.trading.eth_target_points * pos.quantity

                # If profit > 1.2x target, start trailing aggressively
                if unrealized_pnl >= (target_profit * activation_multiple):
                    trail_distance = close_price * trail_distance_pct

                    if pos.direction == "LONG":
                        new_stop = pos.highest_price - trail_distance
                        pos.stop_loss = max(pos.stop_loss, new_stop)
                    else:
                        new_stop = pos.lowest_price + trail_distance
                        pos.stop_loss = min(pos.stop_loss, new_stop)

                    # Check if trailing stop hit
                    if pos.direction == "LONG" and low_price <= pos.stop_loss:
                        exit_reason = "trailing_stop"
                        exit_price = pos.stop_loss
                    elif pos.direction == "SHORT" and high_price >= pos.stop_loss:
                        exit_reason = "trailing_stop"
                        exit_price = pos.stop_loss

            # 4) STANDARD TRAILING STOP (original logic)
            elif self.config.risk.trailing_stop_enabled:
                if unrealized_pnl >= self.config.risk.trailing_stop_activation:
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
        # Entry fee: use maker fee if limit order was used, otherwise taker fee
        if pos.used_limit_order:
            entry_fee_rate = self.config.trading.maker_fee_bps / 10000  # 0.02%
        else:
            entry_fee_rate = self.config.trading.taker_fee_bps / 10000  # 0.04%

        # Exit fee: always taker fee (market order)
        exit_fee_rate = self.config.trading.taker_fee_bps / 10000

        entry_fees = pos.entry_price * pos.quantity * entry_fee_rate
        exit_fees = exit_price * pos.remaining_quantity * exit_fee_rate
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
            'clc_score': pos.clc_score,
            'used_limit_order': pos.used_limit_order,  # Track if maker or taker fee was used
            'entry_fee': entry_fees,
            'exit_fee': exit_fees,
            # For chart generation
            'market_context': pos.clc_score.get('market_context', {}) if isinstance(pos.clc_score, dict) else {},
            'sr_zones': pos.clc_score.get('nearby_sr_zones', []) if isinstance(pos.clc_score, dict) else []
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

        # Save detailed trade analysis text file
        self._save_detailed_trade_analysis(results_dir, timestamp, metrics)

        logger.info(f"[BACKTEST] Results saved to {results_dir}")

    def _save_detailed_trade_analysis(self, results_dir: Path, timestamp: int, metrics: BacktestMetrics):
        """Save detailed human-readable trade analysis to text file"""

        analysis_file = results_dir / f'trade_analysis_{timestamp}.txt'

        with open(analysis_file, 'w', encoding='utf-8') as f:
            f.write("=" * 100 + "\n")
            f.write("DETAILED BACKTEST TRADE ANALYSIS\n")
            f.write("=" * 100 + "\n\n")

            # Summary Statistics
            f.write("SUMMARY STATISTICS\n")
            f.write("-" * 100 + "\n")
            f.write(f"Starting Balance:        ${self.starting_balance:.2f}\n")
            f.write(f"Ending Balance:          ${self.current_balance:.2f}\n")
            f.write(f"Net P&L:                 ${metrics.net_pnl:+.2f}\n")
            f.write(f"ROI:                     {metrics.roi_pct:+.2f}%\n")
            f.write(f"Total Trades:            {metrics.total_trades}\n")
            f.write(f"Winning Trades:          {metrics.winning_trades}\n")
            f.write(f"Losing Trades:           {metrics.losing_trades}\n")
            f.write(f"Win Rate:                {metrics.win_rate:.2f}%\n")
            f.write(f"Average Win:             ${metrics.avg_win:.2f}\n")
            f.write(f"Average Loss:            ${metrics.avg_loss:.2f}\n")
            f.write(f"Largest Win:             ${metrics.largest_win:.2f}\n")
            f.write(f"Largest Loss:            ${metrics.largest_loss:.2f}\n")
            f.write(f"Profit Factor:           {metrics.profit_factor:.2f}\n")
            f.write(f"Expectancy per Trade:    ${metrics.expectancy:.2f}\n")
            f.write(f"Risk/Reward Ratio:       {metrics.avg_risk_reward:.2f}\n")
            f.write(f"Max Drawdown:            ${metrics.max_drawdown:.2f} ({metrics.max_drawdown_pct:.2f}%)\n")
            f.write(f"Max Consecutive Losses:  {metrics.max_consecutive_losses}\n")
            f.write(f"Sharpe Ratio:            {metrics.sharpe_ratio:.2f}\n")
            f.write(f"Avg Trade Duration:      {metrics.avg_trade_duration_minutes:.1f} minutes\n")
            f.write(f"Trades per Day:          {metrics.trades_per_day:.2f}\n")
            f.write(f"Total Fees:              ${metrics.total_fees:.2f}\n")
            f.write(f"\nLONG Trades:             {metrics.long_trades} (Win Rate: {metrics.long_win_rate:.2f}%)\n")
            f.write(f"SHORT Trades:            {metrics.short_trades} (Win Rate: {metrics.short_win_rate:.2f}%)\n")
            f.write("\n" + "=" * 100 + "\n\n")

            # Per-Trade Analysis
            f.write("PER-TRADE DETAILED ANALYSIS\n")
            f.write("=" * 100 + "\n\n")

            for idx, trade in enumerate(self.closed_trades, 1):
                entry_time = datetime.fromtimestamp(trade['entry_time'] / 1000, tz=timezone.utc)
                exit_time = datetime.fromtimestamp(trade['exit_time'] / 1000, tz=timezone.utc)
                duration_mins = (trade['exit_time'] - trade['entry_time']) / 60000

                pnl = trade['net_pnl']
                pnl_symbol = "WIN" if pnl > 0 else "LOSS"

                f.write(f"Trade #{idx} - {pnl_symbol} {trade['direction']}\n")
                f.write("-" * 100 + "\n")
                f.write(f"Entry Time:              {entry_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
                f.write(f"Exit Time:               {exit_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
                f.write(f"Duration:                {duration_mins:.1f} minutes ({duration_mins/60:.1f} hours)\n")
                f.write(f"Entry Price:             ${trade['entry_price']:.2f}\n")
                f.write(f"Exit Price:              ${trade['exit_price']:.2f}\n")
                f.write(f"Exit Reason:             {trade['exit_reason']}\n")
                f.write(f"Quantity:                {trade['quantity']:.6f}\n")
                f.write(f"Notional Value:          ${trade['notional_value']:.2f}\n")
                f.write(f"Leverage:                {trade['leverage']}x\n")
                f.write(f"Initial Margin:          ${trade['initial_margin']:.2f}\n")
                f.write(f"Gross P&L:               ${trade['pnl']:+.2f}\n")
                f.write(f"Entry Fee:               ${trade['entry_fee']:.2f} ({'MAKER' if trade['used_limit_order'] else 'TAKER'})\n")
                f.write(f"Exit Fee:                ${trade['exit_fee']:.2f} (TAKER)\n")
                f.write(f"Total Fees:              ${trade['fees']:.2f}\n")
                f.write(f"Net P&L:                 ${pnl:+.2f}\n")
                f.write(f"P&L %:                   {trade['pnl_pct']:+.2f}% (on notional)\n")
                f.write(f"ROE %:                   {trade['roe_pct']:+.2f}% (return on margin)\n")

                # Extract CLC score details if available
                if isinstance(trade['clc_score'], CLCScore):
                    score = trade['clc_score']
                    f.write(f"\nEntry Score Breakdown:\n")
                    f.write(f"  Total Score:           {score.total_score:.1f}\n")
                    f.write(f"  Context Score:         {score.context_score:.1f}\n")
                    f.write(f"  Location Score:        {score.location_score:.1f}\n")
                    f.write(f"  Confirmation Score:    {score.confirmation_score:.1f}\n")
                    f.write(f"  Big Orders Score:      {score.big_orders_score:.1f}\n")
                    f.write(f"  At Location:           {score.at_location}\n")
                    f.write(f"  Location Type:         {score.location_type}\n")
                    f.write(f"  Confirmation Signals:  {', '.join(score.confirmation_signals) if score.confirmation_signals else 'None'}\n")
                    f.write(f"  Big Orders Detected:   {', '.join(score.big_orders_detected) if score.big_orders_detected else 'None'}\n")
                    f.write(f"  Entry Reasons:         {', '.join(score.reasons) if score.reasons else 'N/A'}\n")
                    if score.warnings:
                        f.write(f"  Warnings:              {', '.join(score.warnings)}\n")

                f.write("\n" + "=" * 100 + "\n\n")

            # Analysis by outcome
            f.write("TRADE OUTCOME ANALYSIS\n")
            f.write("=" * 100 + "\n\n")

            winning_trades = [t for t in self.closed_trades if t['net_pnl'] > 0]
            losing_trades = [t for t in self.closed_trades if t['net_pnl'] <= 0]

            if winning_trades:
                f.write(f"WINNING TRADES ({len(winning_trades)}):\n")
                f.write("-" * 100 + "\n")
                for idx, trade in enumerate(winning_trades, 1):
                    entry_time = datetime.fromtimestamp(trade['entry_time'] / 1000, tz=timezone.utc)
                    f.write(f"  {idx}. {trade['direction']} @ ${trade['entry_price']:.2f} → ${trade['exit_price']:.2f} | "
                           f"P&L: ${trade['net_pnl']:+.2f} | {trade['exit_reason']} | {entry_time.strftime('%m/%d %H:%M')}\n")
                f.write("\n")

            if losing_trades:
                f.write(f"LOSING TRADES ({len(losing_trades)}):\n")
                f.write("-" * 100 + "\n")
                for idx, trade in enumerate(losing_trades, 1):
                    entry_time = datetime.fromtimestamp(trade['entry_time'] / 1000, tz=timezone.utc)
                    f.write(f"  {idx}. {trade['direction']} @ ${trade['entry_price']:.2f} → ${trade['exit_price']:.2f} | "
                           f"P&L: ${trade['net_pnl']:+.2f} | {trade['exit_reason']} | {entry_time.strftime('%m/%d %H:%M')}\n")
                f.write("\n")

            # Exit reason breakdown
            f.write("EXIT REASON BREAKDOWN\n")
            f.write("-" * 100 + "\n")
            exit_reasons = {}
            for trade in self.closed_trades:
                reason = trade['exit_reason']
                if reason not in exit_reasons:
                    exit_reasons[reason] = {'count': 0, 'wins': 0, 'total_pnl': 0}
                exit_reasons[reason]['count'] += 1
                if trade['net_pnl'] > 0:
                    exit_reasons[reason]['wins'] += 1
                exit_reasons[reason]['total_pnl'] += trade['net_pnl']

            for reason, stats in sorted(exit_reasons.items(), key=lambda x: x[1]['count'], reverse=True):
                win_rate = (stats['wins'] / stats['count']) * 100 if stats['count'] > 0 else 0
                f.write(f"  {reason:20s}: {stats['count']:3d} trades ({win_rate:5.1f}% win rate) | "
                       f"Total P&L: ${stats['total_pnl']:+.2f}\n")

            f.write("\n" + "=" * 100 + "\n")
            f.write("END OF ANALYSIS\n")
            f.write("=" * 100 + "\n")

        logger.info(f"[BACKTEST] Detailed trade analysis saved to {analysis_file}")
        print(f"\n[INFO] Detailed trade analysis saved to: {analysis_file}")
        print(f"[INFO] You can paste this file content for review\n")
