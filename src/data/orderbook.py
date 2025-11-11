"""
OrderBook data structures (price-level ladder with deltas)
"""

from dataclasses import dataclass
from typing import Dict, List

@dataclass
class PriceLevel:
    price: float
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    buy_delta: float = 0.0
    sell_delta: float = 0.0
    timestamp: int = 0

    @property
    def total_volume(self):
        return self.bid_volume + self.ask_volume

    @property
    def net_delta(self):
        return self.buy_delta - self.sell_delta

    @property
    def imbalance(self):
        total = self.bid_volume + self.ask_volume
        return (self.bid_volume / total) if total > 0 else 0.5

@dataclass
class OrderBookDepth:
    symbol: str
    levels: Dict[float, PriceLevel]
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread: float = 0.0
    timestamp: int = 0

    def update_depth(self, bids: List, asks: List):
        for price, qty in bids:
            self.levels[price] = self.levels.get(price, PriceLevel(price))
            self.levels[price].bid_volume = qty
        for price, qty in asks:
            self.levels[price] = self.levels.get(price, PriceLevel(price))
            self.levels[price].ask_volume = qty
        if bids:
            self.best_bid = bids[0][0]
        if asks:
            self.best_ask = asks[0][0]
        self.spread = self.best_ask - self.best_bid

    def update_trade(self, price: float, qty: float, is_buyer_maker: bool):
        if price not in self.levels:
            self.levels[price] = PriceLevel(price)
        if is_buyer_maker:
            self.levels[price].sell_delta += qty
        else:
            self.levels[price].buy_delta += qty

    def get_ladder(self, depth: int = 20):
        sorted_levels = sorted(self.levels.items(), key=lambda x: x[0], reverse=True)
        return [lvl for _, lvl in sorted_levels[:depth]]

