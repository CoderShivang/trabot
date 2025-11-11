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
    def __init__(self, config, force_mainnet_data=False):
        self.config = config
        self.rest = None
        self.data_client = None  # Separate client for historical data
        self.force_mainnet_data = force_mainnet_data
        self.orderbooks = {sym: OrderBookDepth(symbol=sym, levels={}) for sym in config.trading.symbols}
        self.backtest_cache = None  # Cache for backtest mode

    async def connect(self):
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

    async def get_klines(self, symbol: str, interval: str, limit: int = 200):
        """Fetch historical klines - check cache first if in backtest mode"""
        # Check cache first (backtest mode)
        if self.backtest_cache and symbol in self.backtest_cache:
            if interval in self.backtest_cache[symbol]:
                cached = self.backtest_cache[symbol][interval]
                # Return last N candles from cache
                result = cached[-limit:] if len(cached) > limit else cached
                logger.debug(f"[BINANCE] Returning {len(result)} cached {interval} klines for {symbol}")
                return result

        # Fallback to live API (live trading mode)
        try:
            kl = self.data_client.futures_klines(symbol=symbol, interval=interval, limit=limit)
            return kl
        except Exception as e:
            logger.error(f"[BINANCE] klines error: {e}")
            return []

    async def disconnect(self):
        logger.info("[BINANCE] disconnect called (no ws to close)")
        return

