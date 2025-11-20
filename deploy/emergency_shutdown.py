"""
Emergency Shutdown Script

Immediately:
1. Stops the trading bot
2. Cancels all open orders
3. Closes all open positions (MARKET orders for speed)

⚠️ USE THIS ONLY IN EMERGENCIES!
"""

import os
import sys
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TESTNET = os.getenv('TESTNET', 'true').lower() == 'true'
SYMBOL = os.getenv('SYMBOL', 'BTCUSDT')

if not API_KEY or not API_SECRET:
    print("❌ ERROR: API credentials not found in .env file!")
    sys.exit(1)

print("=" * 60)
print("⚠️  EMERGENCY SHUTDOWN INITIATED ⚠️")
print("=" * 60)
print(f"Mode: {'TESTNET' if TESTNET else 'LIVE MAINNET'}")
print(f"Symbol: {SYMBOL}")
print("")

# Connect to Binance
if TESTNET:
    client = Client(API_KEY, API_SECRET, testnet=True)
    client.API_URL = 'https://testnet.binancefuture.com'
else:
    client = Client(API_KEY, API_SECRET)

try:
    # Step 1: Cancel all open orders
    print("[1/3] Canceling all open orders...")
    result = client.futures_cancel_all_open_orders(symbol=SYMBOL)
    print(f"✅ Canceled {len(result) if isinstance(result, list) else 'all'} open orders")

except BinanceAPIException as e:
    print(f"⚠️  Warning: Failed to cancel orders: {e}")

try:
    # Step 2: Close all open positions
    print("\n[2/3] Closing all open positions...")
    positions = client.futures_position_information(symbol=SYMBOL)

    closed_count = 0
    for pos in positions:
        position_amt = float(pos['positionAmt'])

        if position_amt != 0:
            # Determine side (opposite of position to close)
            side = 'SELL' if position_amt > 0 else 'BUY'
            quantity = abs(position_amt)

            print(f"  Closing {side} {quantity:.3f} {SYMBOL}...")

            # Use MARKET order for immediate execution
            order = client.futures_create_order(
                symbol=SYMBOL,
                side=side,
                type='MARKET',
                quantity=quantity,
                reduceOnly=True
            )

            print(f"  ✅ Position closed - Order ID: {order['orderId']}")
            closed_count += 1

    if closed_count == 0:
        print("  No open positions to close")
    else:
        print(f"✅ Closed {closed_count} position(s)")

except BinanceAPIException as e:
    print(f"❌ ERROR: Failed to close positions: {e}")
    sys.exit(1)

# Step 3: Verify everything is closed
print("\n[3/3] Verifying all positions closed...")
try:
    positions = client.futures_position_information(symbol=SYMBOL)
    total_position = sum(abs(float(p['positionAmt'])) for p in positions)

    if total_position == 0:
        print("✅ All positions confirmed closed")
    else:
        print(f"⚠️  WARNING: {total_position:.3f} {SYMBOL} still open!")
        print("   Please check Binance UI and close manually!")

    # Check open orders
    open_orders = client.futures_get_open_orders(symbol=SYMBOL)
    if len(open_orders) == 0:
        print("✅ All orders confirmed canceled")
    else:
        print(f"⚠️  WARNING: {len(open_orders)} orders still open!")
        for order in open_orders:
            print(f"   Order #{order['orderId']}: {order['side']} {order['type']}")

except BinanceAPIException as e:
    print(f"⚠️  Warning: Failed to verify: {e}")

print("")
print("=" * 60)
print("🛡️  EMERGENCY SHUTDOWN COMPLETE")
print("=" * 60)
print("")
print("Next steps:")
print("1. Check Binance Futures UI to verify positions closed")
print("2. Review logs to understand what triggered shutdown")
print("3. Fix any issues before restarting bot")
print("")
