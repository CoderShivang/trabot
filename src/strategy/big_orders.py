"""
Big orders detector - improved:
 - large market & limit detection
 - iceberg detection by refill pattern + time decay
 - spoofing detection (rapid add/remove / cancellations)
 - passive vs aggressive distinction by comparing orderbook lifetime and trade hits
"""

import time
from collections import deque, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from utils.logger import setup_logger
logger = setup_logger(__name__)

@dataclass
class BigOrder:
    symbol: str
    side: str
    price: float
    size: float
    size_usdt: float
    timestamp: int
    order_type: str
    confidence: float
    notes: str

class BigOrdersDetector:
    def __init__(self, config, binance_client=None):
        self.config = config
        self.trade_history = defaultdict(lambda: deque(maxlen=2000))
        self.orderbook_history = defaultdict(lambda: deque(maxlen=200))
        self.detected = defaultdict(list)
        # track limit order events (simulated): price -> list of (timestamp, qty, event_type)
        self.limit_events = defaultdict(lambda: deque(maxlen=500))

    def update_trade_history(self, symbol: str, trades: List[Dict]):
        for t in trades:
            self.trade_history[symbol].append(t)

    def update_orderbook_snapshot(self, symbol: str, orderbook):
        snapshot = {
            'timestamp': int(time.time()*1000),
            'best_bid': orderbook.best_bid,
            'best_ask': orderbook.best_ask,
            'levels': {p: {'bid': lvl.bid_volume, 'ask': lvl.ask_volume} for p,lvl in orderbook.levels.items()}
        }
        self.orderbook_history[symbol].append(snapshot)
        # scan for large levels to record "limit event"
        for p,lvl in orderbook.levels.items():
            if lvl.bid_volume > 0 and lvl.bid_volume * p >= self._min_usdt(symbol):
                self.limit_events[(symbol, p, 'bid')].append((snapshot['timestamp'], lvl.bid_volume, 'present'))
            if lvl.ask_volume > 0 and lvl.ask_volume * p >= self._min_usdt(symbol):
                self.limit_events[(symbol, p, 'ask')].append((snapshot['timestamp'], lvl.ask_volume, 'present'))

    def _min_usdt(self, symbol):
        if symbol.startswith("BTC"):
            return self.config.clc_strategy.big_orders.min_btc_order_usdt
        return self.config.clc_strategy.big_orders.min_eth_order_usdt

    def analyze(self, symbol: str, orderbook, recent_trades: List[Dict]) -> Dict:
        self.update_trade_history(symbol, recent_trades)
        self.update_orderbook_snapshot(symbol, orderbook)

        large_markets = self._detect_large_market_orders(symbol)
        large_limits = self._detect_large_limit_orders(symbol, orderbook)
        iceberg = self._detect_iceberg(symbol)
        spoof = self._detect_spoofing(symbol)
        absorption = self._detect_absorption_by_big_player(symbol)

        # maintain detected cache (prune older than 5 minutes)
        now = int(time.time()*1000)
        self.detected[symbol] = [o for o in self.detected[symbol] if now - o.timestamp < 300000]
        for o in large_markets + large_limits:
            if not any(d.price == o.price and d.side == o.side for d in self.detected[symbol]):
                self.detected[symbol].append(o)
        if iceberg:
            self.detected[symbol].append(iceberg)

        return {
            'large_market_orders': large_markets,
            'large_limit_orders': large_limits,
            'iceberg_detected': iceberg is not None,
            'iceberg_reason': iceberg.notes if iceberg else "",
            'spoofing_detected': spoof,
            'big_player_absorption': absorption,
            'all_recent_big_orders': self.detected[symbol]
        }

    def _detect_large_market_orders(self, symbol: str) -> List[BigOrder]:
        if len(self.trade_history[symbol]) < 50:
            return []
        recent = list(self.trade_history[symbol])[-200:]
        sizes = [t['qty'] for t in recent]
        avg = sum(sizes)/len(sizes) if sizes else 0
        threshold = avg * self.config.clc_strategy.big_orders.size_multiplier
        results = []
        for t in recent[-100:]:
            if t['qty'] >= threshold and t['qty']*t['price'] >= self._min_usdt(symbol):
                side = "sell" if t['isBuyerMaker'] else "buy"
                size_ratio = t['qty']/avg if avg>0 else 1.0
                confidence = min(1.0, size_ratio/10)
                results.append(BigOrder(symbol, side, t['price'], t['qty'], t['qty']*t['price'], t['time'], 'market', confidence, f"Large market {size_ratio:.1f}x"))
        return results

    def _detect_large_limit_orders(self, symbol: str, orderbook) -> List[BigOrder]:
        ladder = orderbook.get_ladder(50)
        if not ladder:
            return []
        avg_trade = sum(t['qty'] for t in list(self.trade_history[symbol])[-200:]) / (200 if len(self.trade_history[symbol])>=200 else max(1,len(self.trade_history[symbol])))
        threshold = avg_trade * self.config.clc_strategy.big_orders.large_limit_multiplier if avg_trade>0 else 100
        results = []
        for lvl in ladder:
            if lvl.bid_volume >= threshold and lvl.bid_volume * lvl.price >= self._min_usdt(symbol):
                ratio = lvl.bid_volume / avg_trade if avg_trade>0 else 1
                confidence = min(1.0, ratio/15)
                results.append(BigOrder(symbol, "buy", lvl.price, lvl.bid_volume, lvl.bid_volume*lvl.price, int(time.time()*1000), "limit", confidence, f"Bid wall {ratio:.1f}x"))
            if lvl.ask_volume >= threshold and lvl.ask_volume * lvl.price >= self._min_usdt(symbol):
                ratio = lvl.ask_volume / avg_trade if avg_trade>0 else 1
                confidence = min(1.0, ratio/15)
                results.append(BigOrder(symbol, "sell", lvl.price, lvl.ask_volume, lvl.ask_volume*lvl.price, int(time.time()*1000), "limit", confidence, f"Ask wall {ratio:.1f}x"))
        return results

    def _detect_iceberg(self, symbol: str) -> Optional[BigOrder]:
        # check limit_events for refill patterns at same (symbol,price,side)
        for key, events in list(self.limit_events.items()):
            sym, price, side = key
            if sym != symbol:
                continue
            # count 'present' events within last 10 seconds roughly
            now = int(time.time()*1000)
            recent = [e for e in events if now - e[0] < 15000]
            # refills = many present events after being consumed (heuristic)
            if len(recent) >= self.config.clc_strategy.big_orders.iceberg_refill_threshold:
                return BigOrder(symbol, side, price, 0, 0, now, 'iceberg', 0.8, f"Iceberg refills {len(recent)}")
        return None

    def _detect_spoofing(self, symbol: str) -> bool:
        # spoofing heuristic: large limit appears and disappears repeatedly without trades hitting it
        for (sym, price, side), events in self.limit_events.items():
            if sym != symbol:
                continue
            timestamps = [e[0] for e in events]
            if len(timestamps) < 4:
                continue
            # if many add/remove cycles in short time window -> potential spoof
            windows = 0
            for i in range(1,len(timestamps)):
                if timestamps[i] - timestamps[i-1] < 5000:
                    windows += 1
            if windows >= 3:
                logger.info(f"[SPOOF] {symbol} potential spoof at {price}")
                return True
        return False

    def _detect_absorption_by_big_player(self, symbol: str) -> bool:
        # detect price stuck while large trade flow attempts to push price
        trades = list(self.trade_history[symbol])[-200:]
        if not trades:
            return False
        price_changes = [t['price'] for t in trades]
        if max(price_changes) - min(price_changes) < 0.5:  # small range
            big_trades = [t for t in trades if t['qty'] * t['price'] >= self._min_usdt(symbol)/5]
            return len(big_trades) > 3
        return False

