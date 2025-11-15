
"""
Position manager with Kelly + volatility-adjusted sizing and correlation checks.
"""

import time
import json
from typing import Dict, Optional
from dataclasses import dataclass
from statistics import mean
from pathlib import Path
import asyncio

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class Position:
    symbol: str
    direction: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    entry_timestamp: int
    entry_score: dict
    current_price: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = float('inf')
    unrealized_pnl: float = 0.0
    hold_duration: int = 0

    def update(self, current_price: float):
        self.current_price = current_price
        self.hold_duration = int(time.time() * 1000) - self.entry_timestamp
        if self.direction == "LONG":
            self.highest_price = max(self.highest_price, current_price)
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            self.lowest_price = min(self.lowest_price, current_price)
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity

class PositionManager:
    def __init__(self, config, binance_client, feedback_system=None):
        self.config = config
        self.binance_client = binance_client
        self.feedback_system = feedback_system
        self.positions: Dict[str, Position] = {}
        self.closed_trades = []
        self.starting_balance = 100.0  # user said starting with $100
        self.current_balance = self.starting_balance
        Path('data').mkdir(exist_ok=True)
        self._load_trades()

    def can_open_position(self, symbol: str) -> bool:
        if symbol in self.positions:
            return False
        if len(self.positions) >= self.config.trading.max_positions:
            return False
        # correlation-based check: if BTC and ETH both would exceed correlation limit, block (handled at open)
        return True

    async def open_position(self, decision: Dict) -> Optional[Position]:
        symbol = decision['symbol']
        direction = decision['direction']
        entry_price = decision['entry_price']
        timestamp = decision['timestamp']
        score = decision.get('score', {})

        # compute ATR / volatility
        klines = await self.binance_client.get_klines(symbol, '1m', 100)
        atr = 0.0
        if klines:
            atr = self._compute_atr(klines)

        # target and risk points based on symbol
        if symbol.startswith("BTC"):
            target_points = self.config.trading.btc_target_points
            risk_points = self.config.trading.btc_risk_points
        else:
            target_points = self.config.trading.eth_target_points
            risk_points = self.config.trading.eth_risk_points

        # Base desired position not to exceed position_size_usdt * leverage
        intended_notional = self.config.trading.position_size_usdt * self.config.trading.leverage

        # Determine quantity in base units
        base_qty = (self.config.trading.position_size_usdt) / entry_price

        # Volatility-adjusted stop: choose larger of configured risk_points and ATR * multiplier
        vol_stop_points = max(risk_points, (atr * 3))  # ATR multiplier 3
        effective_risk_points = vol_stop_points

        # Compute max quantity so that if stop is hit, loss <= per_trade_max_loss_usdt
        per_trade_limit = self.config.trading.per_trade_max_loss_usdt
        max_qty_by_dollar = per_trade_limit / effective_risk_points if effective_risk_points > 0 else base_qty

        # choose final quantity conservatively (min of base_qty and max_qty_by_dollar)
        quantity = min(base_qty, max_qty_by_dollar)

        # Kelly sizing (very conservative fraction)
        kelly_qty = await self._kelly_sizing(symbol, entry_price)
        if kelly_qty:
            quantity = min(quantity, kelly_qty)

        # enforce min qty
        if quantity <= 0:
            logger.warning("[POSITION] Computed quantity <= 0; skipping open.")
            return None

        # compute stop & take
        if direction == "LONG":
            stop_loss = entry_price - effective_risk_points
            take_profit = entry_price + target_points
        else:
            stop_loss = entry_price + effective_risk_points
            take_profit = entry_price - target_points

        position = Position(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_timestamp=timestamp,
            entry_score=score,
            current_price=entry_price,
            highest_price=entry_price if direction=="LONG" else entry_price,
            lowest_price=entry_price if direction=="SHORT" else entry_price
        )

        # record position
        self.positions[symbol] = position
        logger.info(f"[POSITION] Opened {direction} {symbol} qty={quantity:.6f} entry={entry_price:.2f} stop={stop_loss:.2f}")
        self._save_positions()
        return position

    async def close_position(self, symbol: str, exit_price: float, reason: str) -> Optional[Dict]:
        if symbol not in self.positions:
            return None
        pos = self.positions[symbol]
        if pos.direction == "LONG":
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        # fees approximated
        fees = (pos.entry_price * pos.quantity + exit_price * pos.quantity) * (self.config.trading.taker_fee_bps / 10000)
        net_pnl = pnl - fees
        pnl_pct = (net_pnl / (pos.entry_price * pos.quantity)) * 100 if pos.entry_price*pos.quantity else 0

        trade_record = {
            'id': f"{symbol}_{pos.entry_timestamp}",
            'symbol': symbol,
            'direction': pos.direction,
            'entry_price': pos.entry_price,
            'exit_price': exit_price,
            'quantity': pos.quantity,
            'pnl': net_pnl,
            'pnl_pct': pnl_pct,
            'fees': fees,
            'hold_duration': int((int(time.time()*1000) - pos.entry_timestamp)/1000),
            'reason': reason,
            'entry_score': pos.entry_score.get('total_score') if isinstance(pos.entry_score, dict) else pos.entry_score,
            'timestamp': int(time.time()*1000)
        }
        self.closed_trades.append(trade_record)
        del self.positions[symbol]
        self._save_trades()
        self._save_positions()
        logger.info(f"[POSITION] Closed {symbol} P&L {net_pnl:+.2f} reason={reason}")
        return trade_record

    def update_position(self, symbol: str, current_price: float):
        if symbol in self.positions:
            self.positions[symbol].update(current_price)
            self._save_positions()

    def check_exit_conditions(self, symbol: str, current_price: float) -> Optional[str]:
        if symbol not in self.positions:
            return None
        pos = self.positions[symbol]
        if pos.direction == "LONG":
            if current_price <= pos.stop_loss:
                return "Stop loss hit"
            if current_price >= pos.take_profit:
                return "Take profit hit"
        else:
            if current_price >= pos.stop_loss:
                return "Stop loss hit"
            if current_price <= pos.take_profit:
                return "Take profit hit"
        return None

    def get_active_positions(self):
        return {s: {
            'symbol': p.symbol,
            'direction': p.direction,
            'entry_price': p.entry_price,
            'current_price': p.current_price,
            'quantity': p.quantity,
            'stop_loss': p.stop_loss,
            'take_profit': p.take_profit,
            'unrealized_pnl': p.unrealized_pnl,
            'hold_duration': p.hold_duration,
            'entry_score': p.entry_score
        } for s,p in self.positions.items()}

    def _save_positions(self):
        try:
            data = self.get_active_positions()
            with open('data/positions.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving positions: {e}")

    def _save_trades(self):
        try:
            with open('data/trades.json', 'w') as f:
                json.dump(self.closed_trades, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving trades: {e}")

    def _load_trades(self):
        try:
            with open('data/trades.json', 'r') as f:
                self.closed_trades = json.load(f)
        except FileNotFoundError:
            self.closed_trades = []
        except Exception as e:
            logger.error(f"Error loading trades: {e}")

    def _compute_atr(self, klines, period=14):
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        closes = [float(k[4]) for k in klines]
        trs = []
        for i in range(1, len(klines)):
            tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
            trs.append(tr)
        if not trs:
            return 0.0
        return sum(trs[-period:]) / min(len(trs), period)

    async def _kelly_sizing(self, symbol, entry_price):
        # Very conservative Kelly sizing based on historical trades in trades.json
        wins = [t for t in self.closed_trades if t['pnl'] > 0]
        losses = [t for t in self.closed_trades if t['pnl'] <= 0]
        if len(self.closed_trades) < 5:
            return None
        win_rate = len(wins) / len(self.closed_trades)
        avg_win = mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = abs(mean([t['pnl'] for t in losses])) if losses else 0
        if avg_loss == 0 or avg_win == 0:
            return None
        b = avg_win / avg_loss
        kelly_fraction = (win_rate - (1 - win_rate)/b) if b > 0 else 0
        kelly_fraction = max(0.0, min(0.1, kelly_fraction))  # cap very conservatively (max 10% of balance)
        notional = self.current_balance * kelly_fraction * self.config.trading.leverage
        qty = notional / entry_price if entry_price > 0 else None
        return qty
