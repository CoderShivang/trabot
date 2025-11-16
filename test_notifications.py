#!/usr/bin/env python3
"""
Test notification setup for Discord and Telegram.

This script tests your notification configuration to ensure you'll receive
trade alerts when the bot is running.

Usage:
    python test_notifications.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config import load_config
from utils.notifications import NotificationManager
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def main():
    """Test notification channels"""
    print("="*60)
    print("NOTIFICATION TEST")
    print("="*60)
    print("\nThis will send test messages to your configured channels.\n")

    try:
        # Load config
        config = load_config()

        # Create notification manager
        notif = NotificationManager(config)

        # Check configuration
        print("Configuration:")
        print(f"  Discord: {'✓ Configured' if notif.discord_webhook else '✗ Not configured'}")
        print(f"  Telegram: {'✓ Configured' if (notif.telegram_token and notif.telegram_chat_id) else '✗ Not configured'}")
        print()

        if not notif.enabled:
            print("❌ No notification channels configured!")
            print("\nTo configure notifications:")
            print("1. Edit your .env file")
            print("2. Add Discord webhook URL and/or Telegram bot credentials")
            print("\nSee FORWARD_TESTING_GUIDE.md for setup instructions.")
            return 1

        # Send test notification
        print("Sending test notification...")
        await notif.test_notifications()
        print("✓ Test notification sent!\n")

        # Send sample trade open notification
        print("Sending sample TRADE OPEN notification...")
        await notif.send_trade_open(
            symbol="BTCUSDT",
            direction="LONG",
            entry_price=47850.00,
            stop_loss=47650.00,
            take_profit=48050.00,
            quantity=0.001,
            clc_score=78.5,
            mode="FORWARD_TEST"
        )
        print("✓ Trade open notification sent!\n")

        # Send sample trade close notification
        print("Sending sample TRADE CLOSE notification (WIN)...")
        await notif.send_trade_close(
            symbol="BTCUSDT",
            direction="LONG",
            entry_price=47850.00,
            exit_price=48050.00,
            pnl=0.20,
            pnl_pct=0.42,
            fees=0.038,
            duration_minutes=15,
            exit_reason="take_profit",
            mode="FORWARD_TEST"
        )
        print("✓ Trade close notification sent!\n")

        # Send sample trade close notification (loss)
        print("Sending sample TRADE CLOSE notification (LOSS)...")
        await notif.send_trade_close(
            symbol="ETHUSDT",
            direction="SHORT",
            entry_price=3200.00,
            exit_price=3215.00,
            pnl=-0.15,
            pnl_pct=-0.47,
            fees=0.026,
            duration_minutes=8,
            exit_reason="stop_loss",
            mode="FORWARD_TEST"
        )
        print("✓ Trade close notification sent!\n")

        print("="*60)
        print("✅ ALL NOTIFICATIONS SENT SUCCESSFULLY!")
        print("="*60)
        print("\nCheck your Discord/Telegram to see the test messages.")
        print("If you didn't receive them, verify your .env configuration.")

        return 0

    except Exception as e:
        logger.error(f"Error testing notifications: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
