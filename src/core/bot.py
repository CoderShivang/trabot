"""
Main orchestrator (updated to pass feedback system and enhanced detectors)
"""

import asyncio
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from data.binance_client import BinanceClient
from strategy.clc_engine import CLCEngine
from strategy.context_analyzer import ContextAnalyzer
from strategy.location_detector import LocationDetector
from strategy.confirmation import ConfirmationAnalyzer
from strategy.big_orders import BigOrdersDetector
from core.position_manager import PositionManager
from learning.feedback_system import AdaptiveFeedbackSystem
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ScalperBot:
    def __init__(self, config):
        self.config = config
        self.running = False
        self.binance_client: Optional[BinanceClient] = None
        self.context_analyzer: Optional[ContextAnalyzer] = None
        self.location_detector: Optional[LocationDetector] = None
        self.confirmation_analyzer: Optional[ConfirmationAnalyzer] = None
        self.big_orders_detector: Optional[BigOrdersDetector] = None
        self.clc_engine: Optional[CLCEngine] = None
        self.position_manager: Optional[PositionManager] = None
        self.feedback_system: Optional[AdaptiveFeedbackSystem] = None
        self.last_check_time = {}
        self.trading_paused = False
        self.daily_pnl = 0.0
        self.consecutive_losses = 0

    async def initialize(self):
        logger.info("[INIT] Initializing components...")
        self.binance_client = BinanceClient(self.config)
        await self.binance_client.connect()

        self.feedback_system = AdaptiveFeedbackSystem(self.config)
        self.context_analyzer = ContextAnalyzer(self.config, self.binance_client)
        self.location_detector = LocationDetector(self.config, self.binance_client, self.feedback_system)
        self.confirmation_analyzer = ConfirmationAnalyzer(self.config, self.binance_client)
        self.big_orders_detector = BigOrdersDetector(self.config, self.binance_client)
        self.clc_engine = CLCEngine(self.config, self.context_analyzer, self.location_detector,
                                    self.confirmation_analyzer, self.big_orders_detector, self.feedback_system)
        self.position_manager = PositionManager(self.config, self.binance_client, self.feedback_system)
        logger.info("[INIT] All components ready")

    async def run(self):
        self.running = True
        tasks = [
            asyncio.create_task(self._main_loop()),
            asyncio.create_task(self._position_monitor_loop()),
            asyncio.create_task(self._status_loop()),
            asyncio.create_task(self._command_listener())
        ]
        await asyncio.gather(*tasks)

    async def _main_loop(self):
        logger.info("[MAIN] Starting main decision loop")
        while self.running:
            if self.trading_paused:
                await asyncio.sleep(1)
                continue

            # weekend stop: simple UTC-based cutoff (cfg trading contains approximate hours)
            now = datetime.now(timezone.utc)
            # Friday UTC check: stop between Fri 21:00 UTC and Mon 21:00 UTC (approx)
            if not self._is_trading_allowed(now):
                logger.debug("[MAIN] Weekend trading disabled by config/time")
                await asyncio.sleep(10)
                continue

            for symbol in self.config.trading.symbols:
                try:
                    # throttle per-symbol checks
                    elapsed = time.time() - self.last_check_time.get(symbol, 0)
                    if elapsed < 0.5:
                        continue
                    self.last_check_time[symbol] = time.time()

                    if not self.position_manager.can_open_position(symbol):
                        continue

                    orderbook = await self.binance_client.get_orderbook(symbol)
                    current_price = (orderbook.best_bid + orderbook.best_ask) / 2
                    recent_trades = await self.binance_client.get_recent_trades(symbol, limit=200)

                    # update detectors
                    self.big_orders_detector.update_trade_history(symbol, recent_trades)
                    self.big_orders_detector.update_orderbook_snapshot(symbol, orderbook)

                    long_score = await self.clc_engine.evaluate_trade(symbol, "LONG", current_price, orderbook, recent_trades)
                    short_score = await self.clc_engine.evaluate_trade(symbol, "SHORT", current_price, orderbook, recent_trades)

                    best = None
                    min_conf_signals = self.config.clc_strategy.confirmation.get('min_signals_required', 2) if isinstance(self.config.clc_strategy.confirmation, dict) else 2
                    if long_score.meets_entry_criteria(self.config.scoring.min_entry_score, min_conf_signals):
                        best = ("LONG", long_score)
                    if short_score.meets_entry_criteria(self.config.scoring.min_entry_score, min_conf_signals):
                        # choose higher score or prefer single if conflict
                        if best is None or short_score.total_score > best[1].total_score:
                            best = ("SHORT", short_score)

                    if best:
                        await self._enter_trade(symbol, best[0], best[1], current_price)

                except Exception as e:
                    logger.error(f"[MAIN] Error scanning {symbol}: {e}", exc_info=True)
            await asyncio.sleep(0.2)

    def _is_trading_allowed(self, now):
        # Simple weekend stop using weekday (UTC)
        # weekday(): Mon=0 ... Sun=6
        if not self.config.trading.weekend_trading:
            if now.weekday() == 4 and now.hour >= self.config.trading.weekend_stop_start_hour_utc:
                return False
            if now.weekday() in (5,6):
                return False
            if now.weekday() == 0 and now.hour < self.config.trading.weekend_stop_end_hour_utc:
                return False
        return True

    async def _enter_trade(self, symbol, direction, clc_score, current_price):
        logger.info(f"[ENTER] {direction} {symbol} score={clc_score.total_score:.1f}")
        # position manager handles sizing, leverage and checks
        decision = {
            'symbol': symbol,
            'direction': direction,
            'entry_price': current_price,
            'stop_loss': None,  # pm will compute stop given config/points
            'take_profit': None,
            'score': clc_score.__dict__ if hasattr(clc_score, '__dict__') else {},
            'timestamp': int(time.time() * 1000)
        }
        await self.position_manager.open_position(decision)

    async def _position_monitor_loop(self):
        logger.info("[MONITOR] Starting position monitor loop")
        while self.running:
            try:
                positions = self.position_manager.get_active_positions()
                for symbol, pos in positions.items():
                    orderbook = await self.binance_client.get_orderbook(symbol)
                    current_price = (orderbook.best_bid + orderbook.best_ask) / 2
                    self.position_manager.update_position(symbol, current_price)
                    exit_reason = self.position_manager.check_exit_conditions(symbol, current_price)
                    if exit_reason:
                        record = await self.position_manager.close_position(symbol, current_price, exit_reason)
                        if record and record['pnl'] < 0:
                            self.consecutive_losses += 1
                        else:
                            self.consecutive_losses = 0
                        self.daily_pnl += record['pnl'] if record else 0
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[MONITOR] Error: {e}", exc_info=True)
                await asyncio.sleep(2)

    async def _status_loop(self):
        while self.running:
            data = {
                'running': self.running and not self.trading_paused,
                'last_update': int(time.time() * 1000),
                'active_positions': len(self.position_manager.positions),
                'daily_pnl': self.daily_pnl,
                'consecutive_losses': self.consecutive_losses
            }
            Path('data').mkdir(exist_ok=True)
            with open('data/bot_status.json', 'w') as f:
                json.dump(data, f, indent=2)
            await asyncio.sleep(5)

    async def _command_listener(self):
        while self.running:
            try:
                cmd_file = Path('data/bot_commands.json')
                if cmd_file.exists():
                    data = json.loads(cmd_file.read_text())
                    cmd = data.get('command')
                    if cmd == 'pause':
                        self.trading_paused = True
                    elif cmd == 'resume':
                        self.trading_paused = False
                    elif cmd == 'restart':
                        self.trading_paused = True
                        await self.shutdown()
                    cmd_file.unlink()
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[COMMAND] Error: {e}", exc_info=True)
                await asyncio.sleep(2)

    async def shutdown(self):
        logger.info("[SHUTDOWN] Closing positions and shutting down...")
        for symbol in list(self.position_manager.positions.keys()):
            orderbook = await self.binance_client.get_orderbook(symbol)
            price = (orderbook.best_bid + orderbook.best_ask) / 2
            await self.position_manager.close_position(symbol, price, "shutdown")
        if self.binance_client:
            await self.binance_client.disconnect()
        self.running = False
        logger.info("[SHUTDOWN] Done.")
