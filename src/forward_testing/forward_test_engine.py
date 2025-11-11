"""
Forward Testing Engine - Real-time simulation with live market data.

This runs like live trading but doesn't place actual orders. It tracks simulated
positions in real-time, allowing you to test your strategy during live market hours
without risking capital.

Forward testing vs Backtesting:
- Backtesting: Historical data, can lookahead, fast replay
- Forward testing: Live data, no lookahead, real-time only
- Paper trading: Live data, real testnet orders, execution risk

Forward testing is the bridge between backtesting and paper trading.
"""

import asyncio
import time
import json
from datetime import datetime, timezone
from typing import Dict, Optional, List
from pathlib import Path
from dataclasses import dataclass, field, asdict

from data.binance_client import BinanceClient
from strategy.clc_engine import CLCEngine, CLCScore
from strategy.context_analyzer import ContextAnalyzer
from strategy.location_detector import LocationDetector
from strategy.confirmation import ConfirmationAnalyzer
from strategy.big_orders import BigOrdersDetector
from learning.feedback_system import AdaptiveFeedbackSystem
from utils.notifications import NotificationManager
from utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class ForwardTestPosition:
    """Simulated position for forward testing"""
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
        self.highest_price = self.entry_price
        self.lowest_price = self.entry_price


@dataclass
class ForwardTestMetrics:
    """Performance metrics for forward testing session"""
    session_start: datetime
    session_end: Optional[datetime] = None
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    current_balance: float = 0.0
    starting_balance: float = 0.0
    roi_pct: float = 0.0


class ForwardTestEngine:
    """
    Real-time forward testing engine.

    Connects to live market data and simulates trading in real-time without
    placing actual orders. Useful for validating strategy on current market
    conditions before risking capital.
    """

    def __init__(self, config):
        self.config = config
        self.running = False

        # Trading state
        self.positions: Dict[str, ForwardTestPosition] = {}
        self.closed_trades: List[Dict] = []
        self.daily_pnl = 0.0
        self.starting_balance = 100.0  # Starting virtual balance
        self.current_balance = self.starting_balance

        # Components (will be initialized in initialize())
        self.binance_client = None
        self.clc_engine = None
        self.context_analyzer = None
        self.location_detector = None
        self.confirmation_analyzer = None
        self.big_orders_detector = None
        self.feedback_system = None
        self.notification_manager = None

        # Metrics
        self.session_start = datetime.now()
        self.last_trade_time: Dict[str, int] = {}
        self.last_save_time = 0  # For periodic saves to update dashboard

        # Results storage
        self.results_file = Path("data/forward_test_results.json")
        self.results_file.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """Initialize all components"""
        logger.info("[FORWARD_TEST] Initializing components...")

        # Use mainnet data for forward testing (real live data)
        self.binance_client = BinanceClient(self.config, force_mainnet_data=True)
        await self.binance_client.connect()

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
            self.big_orders_detector
        )

        self.notification_manager = NotificationManager(self.config)

        logger.info("[FORWARD_TEST] Initialization complete")

    async def start(self):
        """Start forward testing"""
        if self.running:
            logger.warning("[FORWARD_TEST] Already running")
            return

        logger.info("[FORWARD_TEST] Starting real-time forward testing...")
        logger.info(f"[FORWARD_TEST] Symbols: {self.config.trading.symbols}")
        logger.info(f"[FORWARD_TEST] Starting balance: ${self.starting_balance:.2f}")

        self.running = True
        self.session_start = datetime.now()

        # Send startup notification
        await self.notification_manager._send_message(
            f"""
🧪 **FORWARD TESTING STARTED**

Mode: Real-time simulation (NO REAL ORDERS)
Symbols: {', '.join(self.config.trading.symbols)}
Starting Balance: ${self.starting_balance:.2f}

The bot will analyze live market data and simulate trades.
You'll receive notifications for all simulated entries and exits.

Time: {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
        )

        try:
            # Main loop
            while self.running:
                await self._trading_cycle()
                await asyncio.sleep(1)  # Check every second

        except KeyboardInterrupt:
            logger.info("[FORWARD_TEST] Interrupted by user")
        except Exception as e:
            logger.error(f"[FORWARD_TEST] Error in main loop: {e}", exc_info=True)
            await self.notification_manager.send_error_alert(
                "Forward Test Error",
                str(e)
            )
        finally:
            await self.stop()

    async def stop(self):
        """Stop forward testing and save results"""
        if not self.running:
            return

        logger.info("[FORWARD_TEST] Stopping...")
        self.running = False

        # Close any open positions
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            await self._close_position(
                symbol,
                pos.current_price,
                int(time.time() * 1000),
                "session_end"
            )

        # Calculate final metrics
        metrics = self._calculate_metrics()

        # Save results
        self._save_results(metrics)

        # Send session summary
        await self._send_session_summary(metrics)

        logger.info("[FORWARD_TEST] Session ended")

    async def _trading_cycle(self):
        """One iteration of the trading loop"""
        try:
            for symbol in self.config.trading.symbols:
                # Update open positions
                if symbol in self.positions:
                    await self._update_position(symbol)

                # Check for new entry signals
                elif self._can_open_position(symbol):
                    await self._evaluate_entry(symbol)

            # Save results every 10 seconds for live dashboard
            current_time = time.time()
            if current_time - self.last_save_time >= 10:
                metrics = self._calculate_metrics()
                self._save_results(metrics)
                self.last_save_time = current_time

        except Exception as e:
            logger.error(f"[FORWARD_TEST] Error in trading cycle: {e}", exc_info=True)

    async def _evaluate_entry(self, symbol: str):
        """Evaluate if we should enter a trade"""
        try:
            # Fetch current market data
            orderbook = await self.binance_client.get_orderbook(symbol)
            recent_trades = await self.binance_client.get_recent_trades(symbol)

            if not orderbook or not orderbook.best_bid or not orderbook.best_ask:
                return

            current_price = (orderbook.best_bid + orderbook.best_ask) / 2

            # Update detectors with latest data
            self.big_orders_detector.update_trade_history(symbol, recent_trades)
            self.big_orders_detector.update_orderbook_snapshot(symbol, orderbook)

            # Evaluate LONG and SHORT
            long_score = await self.clc_engine.evaluate_trade(
                symbol, "LONG", current_price, orderbook, recent_trades
            )
            short_score = await self.clc_engine.evaluate_trade(
                symbol, "SHORT", current_price, orderbook, recent_trades
            )

            # Get entry threshold
            min_score = self.config.scoring.min_entry_score if hasattr(self.config.scoring, 'min_entry_score') else 75.0

            # Determine best direction
            best = None
            if long_score.total_score >= min_score:
                best = ("LONG", long_score)
            if short_score.total_score >= min_score:
                if best is None or short_score.total_score > best[1].total_score:
                    best = ("SHORT", short_score)

            if best:
                direction, score = best
                logger.info(f"[FORWARD_TEST] Entry signal: {direction} {symbol} @ {current_price:.2f}, score={score.total_score:.1f}")
                await self._open_position(symbol, direction, current_price, score)

        except Exception as e:
            logger.error(f"[FORWARD_TEST] Error evaluating entry for {symbol}: {e}", exc_info=True)

    def _can_open_position(self, symbol: str) -> bool:
        """Check if we can open a new position"""
        # Already have position
        if symbol in self.positions:
            return False

        # Max positions reached
        max_pos = self.config.trading.max_positions if hasattr(self.config.trading, 'max_positions') else 1
        if len(self.positions) >= max_pos:
            return False

        # Daily loss limit hit
        daily_limit = self.config.risk.max_daily_loss_usdt if hasattr(self.config.risk, 'max_daily_loss_usdt') else 30.0
        if self.daily_pnl <= -daily_limit:
            logger.warning(f"[FORWARD_TEST] Daily loss limit hit: ${self.daily_pnl:.2f}")
            return False

        # Cooldown between trades
        min_time_between = 180  # 3 minutes default
        last_trade = self.last_trade_time.get(symbol, 0)
        current_time = int(time.time() * 1000)
        if (current_time - last_trade) < (min_time_between * 1000):
            return False

        return True

    async def _open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        clc_score: CLCScore
    ):
        """Open a simulated position"""
        timestamp = int(time.time() * 1000)

        # Calculate position size
        position_size = self.config.trading.position_size_usdt if hasattr(self.config.trading, 'position_size_usdt') else 15.0

        # Get risk parameters
        if symbol.startswith("BTC"):
            risk_points = self.config.trading.btc_risk_points if hasattr(self.config.trading, 'btc_risk_points') else 200
            target_points = self.config.trading.btc_target_points if hasattr(self.config.trading, 'btc_target_points') else 200
        else:
            risk_points = self.config.trading.eth_risk_points if hasattr(self.config.trading, 'eth_risk_points') else 15
            target_points = self.config.trading.eth_target_points if hasattr(self.config.trading, 'eth_target_points') else 15

        # Calculate quantity
        quantity = position_size / entry_price

        # Calculate stops
        if direction == "LONG":
            stop_loss = entry_price - risk_points
            take_profit = entry_price + target_points
        else:
            stop_loss = entry_price + risk_points
            take_profit = entry_price - target_points

        # Create position
        position = ForwardTestPosition(
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

        logger.info(f"[FORWARD_TEST] OPENED {direction} {symbol} @ ${entry_price:.2f}, SL=${stop_loss:.2f}, TP=${take_profit:.2f}")

        # Send notification
        await self.notification_manager.send_trade_open(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
            clc_score=clc_score.total_score if hasattr(clc_score, 'total_score') else 0,
            mode="FORWARD_TEST"
        )

    async def _update_position(self, symbol: str):
        """Update position with current price and check exit conditions"""
        try:
            pos = self.positions[symbol]

            # Fetch current price
            orderbook = await self.binance_client.get_orderbook(symbol)
            if not orderbook or not orderbook.best_bid or not orderbook.best_ask:
                return

            current_price = (orderbook.best_bid + orderbook.best_ask) / 2

            # Update price tracking
            pos.current_price = current_price
            pos.highest_price = max(pos.highest_price, current_price)
            pos.lowest_price = min(pos.lowest_price, current_price)

            # Check exit conditions
            should_exit = False
            exit_price = current_price
            exit_reason = None

            if pos.direction == "LONG":
                if current_price <= pos.stop_loss:
                    should_exit = True
                    exit_price = pos.stop_loss
                    exit_reason = "stop_loss"
                elif current_price >= pos.take_profit:
                    should_exit = True
                    exit_price = pos.take_profit
                    exit_reason = "take_profit"
            else:  # SHORT
                if current_price >= pos.stop_loss:
                    should_exit = True
                    exit_price = pos.stop_loss
                    exit_reason = "stop_loss"
                elif current_price <= pos.take_profit:
                    should_exit = True
                    exit_price = pos.take_profit
                    exit_reason = "take_profit"

            if should_exit:
                await self._close_position(symbol, exit_price, int(time.time() * 1000), exit_reason)

        except Exception as e:
            logger.error(f"[FORWARD_TEST] Error updating position {symbol}: {e}", exc_info=True)

    async def _close_position(
        self,
        symbol: str,
        exit_price: float,
        timestamp: int,
        exit_reason: str
    ):
        """Close a simulated position"""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]

        # Calculate P&L
        if pos.direction == "LONG":
            gross_pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            gross_pnl = (pos.entry_price - exit_price) * pos.quantity

        # Calculate fees (0.04% taker fee on entry and exit)
        entry_value = pos.entry_price * pos.quantity
        exit_value = exit_price * pos.quantity
        fees = (entry_value + exit_value) * 0.0004

        net_pnl = gross_pnl - fees
        pnl_pct = (net_pnl / entry_value) * 100

        # Update position
        pos.exit_price = exit_price
        pos.exit_time = timestamp
        pos.exit_reason = exit_reason
        pos.pnl = gross_pnl
        pos.fees = fees

        # Update balance and daily P&L
        self.current_balance += net_pnl
        self.daily_pnl += net_pnl

        # Duration
        duration_ms = timestamp - pos.entry_time
        duration_minutes = duration_ms / (1000 * 60)

        # Log
        logger.info(f"[FORWARD_TEST] CLOSED {pos.direction} {symbol} @ ${exit_price:.2f}, P&L=${net_pnl:+.2f} ({pnl_pct:+.2f}%), Reason={exit_reason}")

        # Send notification
        await self.notification_manager.send_trade_close(
            symbol=symbol,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            pnl=gross_pnl,
            pnl_pct=pnl_pct,
            fees=fees,
            duration_minutes=int(duration_minutes),
            exit_reason=exit_reason,
            mode="FORWARD_TEST"
        )

        # Save to closed trades
        trade_record = {
            **asdict(pos),
            'net_pnl': net_pnl,
            'pnl_pct': pnl_pct,
            'duration_minutes': int(duration_minutes)
        }
        self.closed_trades.append(trade_record)

        # Remove from active positions
        del self.positions[symbol]

        # Save results after each trade
        self._save_results(self._calculate_metrics())

    def _calculate_metrics(self) -> ForwardTestMetrics:
        """Calculate current session metrics"""
        if not self.closed_trades:
            return ForwardTestMetrics(
                session_start=self.session_start,
                starting_balance=self.starting_balance,
                current_balance=self.current_balance
            )

        wins = [t for t in self.closed_trades if t['pnl'] > 0]
        losses = [t for t in self.closed_trades if t['pnl'] <= 0]

        total_wins = sum(t['pnl'] for t in wins)
        total_losses = sum(abs(t['pnl']) for t in losses)

        metrics = ForwardTestMetrics(
            session_start=self.session_start,
            session_end=datetime.now(),
            total_trades=len(self.closed_trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=len(wins) / len(self.closed_trades) * 100 if self.closed_trades else 0,
            total_pnl=sum(t['pnl'] for t in self.closed_trades),
            total_fees=sum(t['fees'] for t in self.closed_trades),
            net_pnl=self.current_balance - self.starting_balance,
            largest_win=max((t['pnl'] for t in wins), default=0),
            largest_loss=min((t['pnl'] for t in losses), default=0),
            avg_win=total_wins / len(wins) if wins else 0,
            avg_loss=total_losses / len(losses) if losses else 0,
            profit_factor=total_wins / total_losses if total_losses > 0 else 0,
            starting_balance=self.starting_balance,
            current_balance=self.current_balance,
            roi_pct=((self.current_balance - self.starting_balance) / self.starting_balance) * 100
        )

        return metrics

    def _save_results(self, metrics: ForwardTestMetrics):
        """Save results to file (including open positions for live dashboard)"""
        try:
            # Combine closed trades with open positions for live monitoring
            all_trades = list(self.closed_trades)

            # Add open positions (with current prices)
            for symbol, pos in self.positions.items():
                all_trades.append(asdict(pos))

            results = {
                'session_start': metrics.session_start.isoformat(),
                'session_end': metrics.session_end.isoformat() if metrics.session_end else None,
                'metrics': {
                    'total_trades': metrics.total_trades,
                    'winning_trades': metrics.winning_trades,
                    'losing_trades': metrics.losing_trades,
                    'win_rate': metrics.win_rate,
                    'total_pnl': metrics.total_pnl,
                    'total_fees': metrics.total_fees,
                    'net_pnl': metrics.net_pnl,
                    'largest_win': metrics.largest_win,
                    'largest_loss': metrics.largest_loss,
                    'avg_win': metrics.avg_win,
                    'avg_loss': metrics.avg_loss,
                    'profit_factor': metrics.profit_factor,
                    'starting_balance': metrics.starting_balance,
                    'current_balance': metrics.current_balance,
                    'roi_pct': metrics.roi_pct
                },
                'trades': all_trades,  # Includes both closed and open
                'has_open_position': len(self.positions) > 0
            }

            with open(self.results_file, 'w') as f:
                json.dump(results, f, indent=2)

            logger.debug(f"[FORWARD_TEST] Results saved to {self.results_file}")

        except Exception as e:
            logger.error(f"[FORWARD_TEST] Error saving results: {e}")

    async def _send_session_summary(self, metrics: ForwardTestMetrics):
        """Send final session summary"""
        duration = (metrics.session_end - metrics.session_start).total_seconds() / 3600

        await self.notification_manager._send_message(
            f"""
🧪 **FORWARD TEST SESSION ENDED**

**Duration:** {duration:.1f} hours
**Total Trades:** {metrics.total_trades}
**Wins:** {metrics.winning_trades} | **Losses:** {metrics.losing_trades}
**Win Rate:** {metrics.win_rate:.1f}%

**Starting Balance:** ${metrics.starting_balance:.2f}
**Ending Balance:** ${metrics.current_balance:.2f}
**Net P&L:** ${metrics.net_pnl:+.2f} ({metrics.roi_pct:+.2f}%)

**Largest Win:** ${metrics.largest_win:.2f}
**Largest Loss:** ${metrics.largest_loss:.2f}
**Profit Factor:** {metrics.profit_factor:.2f}

Results saved to: {self.results_file}
            """.strip()
        )
