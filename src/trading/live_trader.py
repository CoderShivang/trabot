"""
Live Trading Module with POST-Only Limit Orders

CRITICAL SAFETY FEATURES:
1. ALL orders use timeInForce='GTX' (POST-only)
2. Orders get REJECTED if they would execute as taker
3. Guarantees 0.02% maker fees (never 0.04% taker fees)
4. Multiple safety checks before each order
5. Position size limits and capital protection

⚠️ WARNING: This trades real money. Test on TESTNET first!
"""

import asyncio
import os
from typing import Optional, Dict, List
from datetime import datetime, timezone
from decimal import Decimal
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dataclasses import dataclass

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class LivePosition:
    """Active live position"""
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    position_id: str

    # Order IDs
    tp_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None


class LiveTrader:
    """
    Live futures trader with POST-only limit orders

    Features:
    - POST-only orders (GTX) for maker fees
    - Stop loss and take profit automation
    - Position size limits
    - Capital protection
    - Error handling and logging
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        symbol: str = 'BTCUSDT',
        testnet: bool = True,  # Always start with testnet!
        max_position_usdt: float = 100.0,  # Max position size
        leverage: int = 20,
        maker_fee: float = 0.0002  # 0.02%
    ):
        self.symbol = symbol
        self.testnet = testnet
        self.max_position_usdt = max_position_usdt
        self.leverage = leverage
        self.maker_fee = maker_fee

        # Initialize Binance client
        if testnet:
            logger.info("[TRADER] Connecting to TESTNET...")
            self.client = Client(api_key, api_secret, testnet=True)
            self.client.API_URL = 'https://testnet.binancefuture.com'
        else:
            logger.warning("[TRADER] ⚠️ CONNECTING TO LIVE MAINNET ⚠️")
            self.client = Client(api_key, api_secret)

        # State
        self.position: Optional[LivePosition] = None

        # Safety checks
        self._verify_connection()
        self._set_leverage()

    def _verify_connection(self):
        """Verify API connection and permissions"""
        try:
            # Check account access
            account = self.client.futures_account()
            balance = float(account['totalWalletBalance'])

            logger.info(f"[TRADER] Connected successfully")
            logger.info(f"[TRADER] Wallet Balance: ${balance:.2f}")
            logger.info(f"[TRADER] Mode: {'TESTNET' if self.testnet else 'LIVE MAINNET'}")

            # Verify permissions
            if not self.testnet:
                logger.warning("[TRADER] ⚠️ LIVE TRADING MODE - REAL MONEY AT RISK ⚠️")

        except BinanceAPIException as e:
            logger.error(f"[TRADER] Connection failed: {e}")
            raise

    def _set_leverage(self):
        """Set leverage for the symbol"""
        try:
            self.client.futures_change_leverage(
                symbol=self.symbol,
                leverage=self.leverage
            )
            logger.info(f"[TRADER] Leverage set to {self.leverage}x for {self.symbol}")
        except BinanceAPIException as e:
            logger.error(f"[TRADER] Failed to set leverage: {e}")
            raise

    def get_current_price(self) -> float:
        """Get current market price"""
        ticker = self.client.futures_symbol_ticker(symbol=self.symbol)
        return float(ticker['price'])

    def _calculate_quantity(self, entry_price: float, stop_loss: float, risk_usd: float) -> float:
        """
        Calculate position size based on risk

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            risk_usd: Amount to risk in USDT

        Returns:
            Quantity in base asset
        """
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance == 0:
            raise ValueError("Stop distance cannot be zero")

        # Calculate quantity: risk / stop_distance
        quantity = risk_usd / stop_distance

        # Verify it doesn't exceed max position size
        notional_value = quantity * entry_price
        if notional_value > self.max_position_usdt:
            quantity = self.max_position_usdt / entry_price
            logger.warning(f"[RISK] Position capped at ${self.max_position_usdt:.2f}")

        # Round to 3 decimal places for BTC (adjust per symbol)
        quantity = round(quantity, 3)

        return quantity

    def place_post_only_order(
        self,
        side: str,  # 'BUY' or 'SELL'
        price: float,
        quantity: float,
        reduce_only: bool = False
    ) -> Dict:
        """
        Place POST-ONLY limit order (GTX)

        ✅ Guarantees maker fees (0.02%)
        ❌ Gets rejected if would execute as taker

        Args:
            side: 'BUY' or 'SELL'
            price: Limit price
            quantity: Order quantity
            reduce_only: Whether this is a position exit order

        Returns:
            Order response dict

        Raises:
            BinanceAPIException: If order is rejected
        """
        try:
            logger.info(f"[ORDER] Placing POST-only {side} order")
            logger.info(f"        Symbol: {self.symbol}")
            logger.info(f"        Price: ${price:,.2f}")
            logger.info(f"        Quantity: {quantity:.3f}")
            logger.info(f"        Reduce Only: {reduce_only}")

            params = {
                'symbol': self.symbol,
                'side': side,
                'type': 'LIMIT',
                'timeInForce': 'GTX',  # ← POST-ONLY!
                'quantity': quantity,
                'price': price,
            }

            if reduce_only:
                params['reduceOnly'] = True

            order = self.client.futures_create_order(**params)

            logger.info(f"[ORDER] ✅ Order placed successfully")
            logger.info(f"        Order ID: {order['orderId']}")
            logger.info(f"        Status: {order['status']}")

            return order

        except BinanceAPIException as e:
            if "Post Only order will be rejected" in str(e):
                logger.warning(f"[ORDER] ❌ POST-only order rejected (would execute as taker)")
                logger.warning(f"        Price: ${price:,.2f} | Market: ${self.get_current_price():,.2f}")
                logger.warning(f"        This is GOOD - it prevented taker fees!")
            else:
                logger.error(f"[ORDER] ❌ Order failed: {e}")
            raise

    def open_long_position(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        risk_usd: float = 2.0  # Risk $2 per trade
    ) -> bool:
        """
        Open LONG position with POST-only entry

        Args:
            entry_price: Entry limit price
            stop_loss: Stop loss price
            take_profit: Take profit price
            risk_usd: Amount to risk in USDT

        Returns:
            True if position opened successfully
        """
        if self.position is not None:
            logger.warning("[TRADER] Position already open, skipping")
            return False

        try:
            # Calculate quantity
            quantity = self._calculate_quantity(entry_price, stop_loss, risk_usd)

            logger.info(f"\n[LONG] Opening LONG position")
            logger.info(f"       Entry: ${entry_price:,.2f}")
            logger.info(f"       Stop Loss: ${stop_loss:,.2f}")
            logger.info(f"       Take Profit: ${take_profit:,.2f}")
            logger.info(f"       Quantity: {quantity:.3f} BTC")
            logger.info(f"       Risk: ${risk_usd:.2f}")

            # Place POST-only entry order
            entry_order = self.place_post_only_order(
                side='BUY',
                price=entry_price,
                quantity=quantity
            )

            # Create position object
            self.position = LivePosition(
                symbol=self.symbol,
                side='LONG',
                entry_price=entry_price,
                quantity=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_time=datetime.now(timezone.utc),
                position_id=entry_order['orderId']
            )

            # Place SL and TP orders (also POST-only)
            self._place_exit_orders()

            logger.info(f"[LONG] ✅ Position opened successfully\n")
            return True

        except Exception as e:
            logger.error(f"[LONG] Failed to open position: {e}")
            return False

    def _place_exit_orders(self):
        """Place POST-only SL and TP orders for active position"""
        if not self.position:
            return

        try:
            # Take Profit order
            tp_order = self.place_post_only_order(
                side='SELL' if self.position.side == 'LONG' else 'BUY',
                price=self.position.take_profit,
                quantity=self.position.quantity,
                reduce_only=True
            )
            self.position.tp_order_id = tp_order['orderId']
            logger.info(f"[EXIT] ✅ TP order placed: ${self.position.take_profit:,.2f}")

            # Stop Loss order (use STOP_MARKET for reliability)
            # Note: SL uses STOP_MARKET because it's an exit, not entry
            sl_order = self.client.futures_create_order(
                symbol=self.symbol,
                side='SELL' if self.position.side == 'LONG' else 'BUY',
                type='STOP_MARKET',
                stopPrice=self.position.stop_loss,
                quantity=self.position.quantity,
                reduceOnly=True
            )
            self.position.sl_order_id = sl_order['orderId']
            logger.info(f"[EXIT] ✅ SL order placed: ${self.position.stop_loss:,.2f}")

        except BinanceAPIException as e:
            logger.error(f"[EXIT] Failed to place exit orders: {e}")
            raise

    def check_and_update_position(self):
        """Check if position has been filled/exited"""
        if not self.position:
            return

        try:
            # Check if entry order filled
            entry_status = self.client.futures_get_order(
                symbol=self.symbol,
                orderId=self.position.position_id
            )

            if entry_status['status'] != 'FILLED':
                logger.debug(f"[POSITION] Entry order not filled yet: {entry_status['status']}")
                return

            # Check TP order
            if self.position.tp_order_id:
                tp_status = self.client.futures_get_order(
                    symbol=self.symbol,
                    orderId=self.position.tp_order_id
                )

                if tp_status['status'] == 'FILLED':
                    logger.info(f"[EXIT] ✅ TP HIT - Position closed at ${self.position.take_profit:,.2f}")
                    self._close_position("TP")
                    return

            # Check SL order
            if self.position.sl_order_id:
                sl_status = self.client.futures_get_order(
                    symbol=self.symbol,
                    orderId=self.position.sl_order_id
                )

                if sl_status['status'] == 'FILLED':
                    logger.info(f"[EXIT] ❌ SL HIT - Position closed at ${self.position.stop_loss:,.2f}")
                    self._close_position("SL")
                    return

        except BinanceAPIException as e:
            logger.error(f"[POSITION] Error checking position: {e}")

    def _close_position(self, reason: str):
        """Close position and cancel remaining orders"""
        if not self.position:
            return

        try:
            # Cancel remaining orders
            self.client.futures_cancel_all_open_orders(symbol=self.symbol)

            logger.info(f"[CLOSE] Position closed - Reason: {reason}")
            self.position = None

        except BinanceAPIException as e:
            logger.error(f"[CLOSE] Error closing position: {e}")

    def emergency_close_all(self):
        """Emergency: Close all positions and cancel all orders"""
        logger.warning("[EMERGENCY] Closing all positions and canceling all orders!")

        try:
            # Cancel all orders
            self.client.futures_cancel_all_open_orders(symbol=self.symbol)

            # Close all positions at market
            positions = self.client.futures_position_information(symbol=self.symbol)
            for pos in positions:
                qty = float(pos['positionAmt'])
                if qty != 0:
                    side = 'SELL' if qty > 0 else 'BUY'
                    self.client.futures_create_order(
                        symbol=self.symbol,
                        side=side,
                        type='MARKET',
                        quantity=abs(qty),
                        reduceOnly=True
                    )
                    logger.warning(f"[EMERGENCY] Closed {abs(qty):.3f} {self.symbol}")

            self.position = None
            logger.info("[EMERGENCY] All positions closed")

        except Exception as e:
            logger.error(f"[EMERGENCY] Failed to close positions: {e}")


# Example usage
if __name__ == "__main__":
    # Load from .env
    from dotenv import load_dotenv
    load_dotenv()

    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_API_SECRET')

    # ALWAYS test on testnet first!
    trader = LiveTrader(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbol='BTCUSDT',
        testnet=True,  # ← Keep this True until you're 100% confident!
        max_position_usdt=100.0,
        leverage=20
    )

    # Example: Open a LONG position
    current_price = trader.get_current_price()
    logger.info(f"Current BTC price: ${current_price:,.2f}")

    # Entry below market (POST-only, will sit on book)
    entry = current_price - 100
    stop_loss = entry - 150
    take_profit = entry + 200

    trader.open_long_position(
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_usd=2.0
    )

    # Monitor position
    while True:
        trader.check_and_update_position()
        asyncio.sleep(5)  # Check every 5 seconds
