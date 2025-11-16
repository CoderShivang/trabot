"""
Binance client (REST wrappers) - uses python-binance for simple REST-based retrieval.
Websocket feed not implemented here (can be extended later).
"""

import asyncio
from binance.client import Client
from binance.exceptions import BinanceAPIException
from data.orderbook import OrderBookDepth
from utils.logger import setup_logger

logger = setup_logger(__name__)

class BinanceClient:
    def __init__(self, config, force_mainnet_data=False, backtest_mode=False):
        self.config = config
        self.rest = None
        self.data_client = None  # Separate client for historical data
        self.force_mainnet_data = force_mainnet_data
        self.backtest_mode = backtest_mode  # Skip connection in backtest mode
        self.orderbooks = {sym: OrderBookDepth(symbol=sym, levels={}) for sym in config.trading.symbols}
        self.backtest_cache = None  # Cache for backtest mode

    async def connect(self, skip_ping=False):
        # Skip connection in backtest mode - we'll use cached data only
        if self.backtest_mode:
            logger.info("[BINANCE] Backtest mode - skipping API connection (will use cached data)")
            return

        # For backtesting with skip_ping, create client with minimal configuration
        # to avoid geo-restriction errors during SDK initialization
        if skip_ping:
            logger.info("[BINANCE] Backtest mode - creating data-only client (no ping)")
            try:
                # Try to create a mainnet client for data fetching
                # The SDK will still try to ping, but we'll catch the error
                self.data_client = Client(api_key=self.config.api_key, api_secret=self.config.api_secret, testnet=False)
                logger.info("[BINANCE] Data client ready for backtest")
            except Exception as e:
                # If client creation fails due to geo-restriction, we can't proceed
                logger.error(f"[BINANCE] Failed to create client for backtest: {e}")
                logger.error("[BINANCE] Backtesting requires API access to fetch historical data")
                logger.error("[BINANCE] Options: 1) Use VPN  2) Run from allowed location  3) Use pre-cached data")
                raise
            return

        # Trading client (respects paper_trading flag)
        if self.config.trading.paper_trading:
            self.rest = Client(api_key=self.config.api_key, api_secret=self.config.api_secret, testnet=True)
            logger.info("[BINANCE] Trading client connected (TESTNET)")
        else:
            self.rest = Client(api_key=self.config.api_key, api_secret=self.config.api_secret)
            logger.info("[BINANCE] Trading client connected (MAINNET)")

        # Data client (ALWAYS mainnet for accurate historical data)
        # Historical data (klines, trades) should always come from real market
        if self.force_mainnet_data or self.config.trading.paper_trading:
            # Use mainnet for historical data even when paper trading
            self.data_client = Client(api_key=self.config.api_key, api_secret=self.config.api_secret, testnet=False)
            logger.info("[BINANCE] Data client connected (MAINNET - real historical data)")
        else:
            # Use same client for both trading and data
            self.data_client = self.rest

        try:
            self.rest.futures_ping()
        except Exception as e:
            logger.error("[BINANCE] connect failed: %s", e)
            raise

    async def get_orderbook(self, symbol: str, limit: int = 50) -> OrderBookDepth:
        try:
            depth = self.rest.futures_order_book(symbol=symbol, limit=limit)
            bids = [(float(p), float(q)) for p, q in depth['bids']]
            asks = [(float(p), float(q)) for p, q in depth['asks']]
            ob = self.orderbooks[symbol]
            ob.update_depth(bids, asks)
            return ob
        except BinanceAPIException as e:
            logger.error(f"[BINANCE] orderbook error: {e}")
            return self.orderbooks[symbol]
        except Exception as e:
            logger.error(f"[BINANCE] unexpected orderbook error: {e}")
            return self.orderbooks[symbol]

    async def get_recent_trades(self, symbol: str, limit: int = 200):
        """Fetch recent trades - uses data_client for real market data"""
        try:
            trades = self.data_client.futures_recent_trades(symbol=symbol, limit=limit)
            # adapt to uniform keys
            normalized = []
            for t in trades:
                normalized.append({
                    'price': float(t['price']),
                    'qty': float(t['qty']),
                    'isBuyerMaker': t.get('isBuyerMaker', False),
                    'time': t.get('time', 0)
                })
            return normalized
        except Exception as e:
            logger.error(f"[BINANCE] recent trades error: {e}")
            return []

    def set_backtest_cache(self, klines_cache: dict):
        """Set cached klines for backtesting mode"""
        self.backtest_cache = klines_cache
        logger.info("[BINANCE] Backtest cache enabled - will use pre-loaded data")

    async def get_klines(self, symbol: str, interval: str, limit: int = 200, start_time: int = None, end_time: int = None):
        """Fetch historical klines - check cache first if in backtest mode

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Timeframe ('1m', '5m', '15m', '1h', etc.)
            limit: Number of candles to fetch (max 1000)
            start_time: Start timestamp in milliseconds (optional)
            end_time: End timestamp in milliseconds (optional)
        """
        # Check cache first (backtest mode)
        if self.backtest_cache and symbol in self.backtest_cache:
            if interval in self.backtest_cache[symbol]:
                cached = self.backtest_cache[symbol][interval]
                # Return last N candles from cache
                result = cached[-limit:] if len(cached) > limit else cached
                logger.debug(f"[BINANCE] Returning {len(result)} cached {interval} klines for {symbol}")
                return result

        # In backtest mode without cache, return empty (shouldn't happen if cache is set up properly)
        if self.backtest_mode:
            logger.warning(f"[BINANCE] Backtest mode but no cache for {symbol} {interval} - returning empty")
            return []

        # Fallback to live API (live trading mode only)
        try:
            # Build kwargs for API call
            kwargs = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }

            # Add date range if provided
            if start_time is not None:
                kwargs['startTime'] = start_time
            if end_time is not None:
                kwargs['endTime'] = end_time

            kl = self.data_client.futures_klines(**kwargs)
            return kl
        except Exception as e:
            logger.error(f"[BINANCE] klines error: {e}")
            return []

    async def disconnect(self):
        logger.info("[BINANCE] disconnect called (no ws to close)")
        return

