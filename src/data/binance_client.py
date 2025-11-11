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
    def __init__(self, config):
        self.config = config
        self.rest = None
        self.orderbooks = {sym: OrderBookDepth(symbol=sym, levels={}) for sym in config.trading.symbols}

    async def connect(self):
        if self.config.trading.paper_trading:
            self.rest = Client(api_key=self.config.api_key, api_secret=self.config.api_secret, testnet=True)
        else:
            self.rest = Client(api_key=self.config.api_key, api_secret=self.config.api_secret)
        try:
            self.rest.futures_ping()
            logger.info("[BINANCE] REST connected")
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
        try:
            trades = self.rest.futures_recent_trades(symbol=symbol, limit=limit)
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

    async def get_klines(self, symbol: str, interval: str, limit: int = 200):
        try:
            kl = self.rest.futures_klines(symbol=symbol, interval=interval, limit=limit)
            return kl
        except Exception as e:
            logger.error(f"[BINANCE] klines error: {e}")
            return []

    async def disconnect(self):
        logger.info("[BINANCE] disconnect called (no ws to close)")
        return

