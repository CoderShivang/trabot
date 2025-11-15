
"""
Confirmation Analyzer - Extended order-flow signals:
 - volume profile (where volume concentrates)
 - tape velocity (time & sales speed)
 - cumulative delta divergences
 - tape reading (aggressive vs passive fills)
"""

from src.data.orderbook import OrderBookDepth
from typing import Dict, List
import time
import numpy as np
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class ConfirmationAnalyzer:
    def __init__(self, config, binance_client=None):
        self.config = config
        self.client = binance_client
        # rolling trades buffer per symbol
        self.trade_buffers = {}

    def analyze(self, symbol: str, orderbook: OrderBookDepth, recent_trades: List[Dict]) -> Dict:
        # ensure buffer
        buf = self.trade_buffers.setdefault(symbol, [])
        # append new trades (timestamp assumed monotonic-ish)
        for t in recent_trades:
            buf.append(t)
        # keep last 1000
        if len(buf) > 2000:
            buf = buf[-2000:]
        self.trade_buffers[symbol] = buf

        imbalance = self._calculate_imbalance(orderbook)
        delta = self._calculate_cumulative_delta(symbol)
        vp = self._volume_profile(buf, bucket_size=10.0)  # bucket in $10 for BTC default; tuned later
        tape = self._tape_velocity(buf)
        tape_signature = self._tape_aggressiveness(buf)

        # detect divergences: price moving one way while cumulative delta moving other
        divergence = self._delta_price_divergence(symbol, orderbook, buf)

        # simplistic absorption & sweep heuristics
        absorption = self._detect_absorption(buf, orderbook)
        sweep, sweep_direction = self._detect_sweep(buf, orderbook)

        return {
            'imbalance': imbalance,
            'delta': delta,
            'volume_profile': vp,
            'tape_velocity': tape,
            'tape_aggressiveness': tape_signature,
            'divergence': divergence,
            'absorption_detected': absorption[0],
            'absorption_reason': absorption[1],
            'sweep_detected': sweep,
            'sweep_direction': sweep_direction
        }

    def _calculate_imbalance(self, orderbook: OrderBookDepth) -> float:
        ladder = orderbook.get_ladder(10)
        total_bid = sum(l.bid_volume for l in ladder)
        total_ask = sum(l.ask_volume for l in ladder)
        total = total_bid + total_ask
        return float(total_bid / total) if total > 0 else 0.5

    def _calculate_cumulative_delta(self, symbol: str, lookback: int = 200) -> float:
        buf = self.trade_buffers.get(symbol, [])[-lookback:]
        buy = sum(t['qty'] for t in buf if not t['isBuyerMaker'])
        sell = sum(t['qty'] for t in buf if t['isBuyerMaker'])
        total = buy + sell
        if total == 0:
            return 0.0
        return float((buy - sell) / total)

    def _volume_profile(self, trades: List[Dict], bucket_size: float = 10.0) -> Dict:
        # bucket by price ranges (coarse)
        if not trades:
            return {}
        prices = [t['price'] for t in trades]
        min_p, max_p = min(prices), max(prices)
        if max_p - min_p < 1e-6:
            return {round(min_p,2): sum(t['qty'] for t in trades)}
        buckets = {}
        for t in trades:
            bucket = round((t['price'] - min_p) // bucket_size * bucket_size + min_p, 2)
            buckets[bucket] = buckets.get(bucket, 0) + t['qty']
        # return top concentration regions
        sorted_buckets = sorted(buckets.items(), key=lambda x: x[1], reverse=True)[:5]
        return dict(sorted_buckets)

    def _tape_velocity(self, trades: List[Dict], lookback_ms: int = 2000) -> float:
        # number of trades per second in last lookback_ms
        if not trades:
            return 0.0
        now = trades[-1]['time'] if 'time' in trades[-1] else int(time.time()*1000)
        cutoff = now - lookback_ms
        recent = [t for t in trades if t['time'] >= cutoff]
        seconds = lookback_ms / 1000.0
        return float(len(recent) / seconds) if seconds > 0 else 0.0

    def _tape_aggressiveness(self, trades: List[Dict], lookback: int = 200) -> float:
        # ratio of aggressive taker buys to passive fills
        sample = trades[-lookback:]
        aggr_buy = sum(t['qty'] for t in sample if not t['isBuyerMaker'])
        aggr_sell = sum(t['qty'] for t in sample if t['isBuyerMaker'])
        total = aggr_buy + aggr_sell
        if total == 0:
            return 0.0
        return float((aggr_buy - aggr_sell) / total)

    def _delta_price_divergence(self, symbol: str, orderbook: OrderBookDepth, trades: List[Dict]) -> bool:
        # compare short-term price move vs cumulative delta
        if not trades:
            return False
        recent = trades[-50:]
        prices = [t['price'] for t in recent]
        if len(prices) < 5:
            return False
        price_change = prices[-1] - prices[0]
        buy = sum(t['qty'] for t in recent if not t['isBuyerMaker'])
        sell = sum(t['qty'] for t in recent if t['isBuyerMaker'])
        delta = buy - sell
        # divergence if price moved up but delta negative or vice versa
        return (price_change > 0 and delta < 0) or (price_change < 0 and delta > 0)

    def _detect_absorption(self, trades: List[Dict], orderbook: OrderBookDepth):
        # naive absorption: many small sell trades hitting bids without price moving down
        if not trades:
            return (False, "")
        last_price = trades[-1]['price']
        small_sells = sum(1 for t in trades[-50:] if t['isBuyerMaker'] and t['price'] <= last_price)
        if small_sells > 20:
            return (True, "High small-sell volume at level (possible absorption)")
        return (False, "")

    def _detect_sweep(self, trades: List[Dict], orderbook: OrderBookDepth):
        # sweep = quick run below support or above resistance with high velocity
        velocity = self._tape_velocity(trades)
        if velocity > 30 and self._tape_aggressiveness(trades) < -0.4:
            return (True, "down")
        if velocity > 30 and self._tape_aggressiveness(trades) > 0.4:
            return (True, "up")
        return (False, "")
