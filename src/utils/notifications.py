"""
Notification manager for sending trade alerts via Discord and Telegram.
Supports trade open/close notifications with full details.
"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from utils.logger import setup_logger

logger = setup_logger(__name__)


class NotificationManager:
    """Manages trade notifications via Discord and Telegram"""

    def __init__(self, config):
        self.config = config
        self.discord_webhook = config.discord_webhook_url if hasattr(config, 'discord_webhook_url') else ""
        self.telegram_token = config.telegram_bot_token if hasattr(config, 'telegram_bot_token') else ""
        self.telegram_chat_id = config.telegram_chat_id if hasattr(config, 'telegram_chat_id') else ""

        # Notification settings
        self.enabled = self._check_enabled()

    def _check_enabled(self) -> bool:
        """Check if any notification channel is configured"""
        has_discord = bool(self.discord_webhook and self.discord_webhook.startswith('http'))
        has_telegram = bool(self.telegram_token and self.telegram_chat_id)

        if has_discord:
            logger.info("[NOTIFICATIONS] Discord enabled")
        if has_telegram:
            logger.info("[NOTIFICATIONS] Telegram enabled")

        return has_discord or has_telegram

    async def send_trade_open(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
        clc_score: float,
        mode: str = "LIVE"  # LIVE, FORWARD_TEST, PAPER
    ):
        """
        Send notification when trade is opened.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            direction: LONG or SHORT
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            quantity: Position size
            clc_score: CLC score that triggered entry
            mode: Trading mode (LIVE/FORWARD_TEST/PAPER)
        """
        if not self.enabled:
            return

        # Calculate risk and reward
        if direction == "LONG":
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit

        risk_pct = (risk / entry_price) * 100
        reward_pct = (reward / entry_price) * 100
        rr_ratio = reward / risk if risk > 0 else 0

        # Format message
        mode_emoji = {
            "LIVE": "🔴",
            "FORWARD_TEST": "🧪",
            "PAPER": "📝"
        }
        emoji = mode_emoji.get(mode, "📊")

        direction_emoji = "🟢" if direction == "LONG" else "🔴"

        message = f"""
{emoji} **{mode} TRADE OPENED** {direction_emoji}

**{symbol} {direction}**
Entry: `${entry_price:,.2f}`
Stop Loss: `${stop_loss:,.2f}` ({risk_pct:+.2f}%)
Take Profit: `${take_profit:,.2f}` ({reward_pct:+.2f}%)

Position Size: `{quantity:.6f}`
Risk/Reward: `1:{rr_ratio:.2f}`
CLC Score: `{clc_score:.1f}`

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()

        await self._send_message(message)

    async def send_trade_close(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        fees: float,
        duration_minutes: int,
        exit_reason: str,
        mode: str = "LIVE"
    ):
        """
        Send notification when trade is closed.

        Args:
            symbol: Trading pair
            direction: LONG or SHORT
            entry_price: Entry price
            exit_price: Exit price
            pnl: Profit/loss in USDT
            pnl_pct: Profit/loss percentage
            fees: Trading fees paid
            duration_minutes: How long trade was open
            exit_reason: Why trade closed (stop_loss, take_profit, manual, etc.)
            mode: Trading mode
        """
        if not self.enabled:
            return

        # Determine result emoji
        if pnl > 0:
            result_emoji = "✅ WIN"
            color = "green"
        else:
            result_emoji = "❌ LOSS"
            color = "red"

        mode_emoji = {
            "LIVE": "🔴",
            "FORWARD_TEST": "🧪",
            "PAPER": "📝"
        }
        emoji = mode_emoji.get(mode, "📊")

        # Format duration
        hours = duration_minutes // 60
        mins = duration_minutes % 60
        duration_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

        # Format exit reason
        reason_map = {
            "stop_loss": "Stop Loss Hit",
            "take_profit": "Take Profit Hit",
            "manual": "Manual Close",
            "daily_limit": "Daily Loss Limit",
            "timeout": "Time Stop",
            "backtest_end": "Period End"
        }
        reason_display = reason_map.get(exit_reason, exit_reason.replace('_', ' ').title())

        message = f"""
{emoji} **{mode} TRADE CLOSED** {result_emoji}

**{symbol} {direction}**
Entry: `${entry_price:,.2f}`
Exit: `${exit_price:,.2f}`

**P&L: `${pnl:+,.2f}` ({pnl_pct:+.2f}%)**
Fees: `${fees:.2f}`
Net: `${pnl - fees:+,.2f}`

Duration: `{duration_str}`
Reason: `{reason_display}`

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()

        await self._send_message(message, color=color)

    async def send_daily_summary(
        self,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        total_pnl: float,
        total_fees: float,
        win_rate: float,
        largest_win: float,
        largest_loss: float,
        mode: str = "LIVE"
    ):
        """Send daily trading summary"""
        if not self.enabled:
            return

        net_pnl = total_pnl - total_fees
        result_emoji = "🎉" if net_pnl > 0 else "😔"

        message = f"""
📊 **DAILY SUMMARY** - {datetime.now().strftime('%Y-%m-%d')}

**Mode:** {mode}
**Total Trades:** {total_trades}
**Wins:** {winning_trades} | **Losses:** {losing_trades}
**Win Rate:** {win_rate:.1f}%

**Gross P&L:** ${total_pnl:+,.2f}
**Fees:** ${total_fees:.2f}
**Net P&L:** ${net_pnl:+,.2f} {result_emoji}

**Largest Win:** ${largest_win:,.2f}
**Largest Loss:** ${largest_loss:,.2f}
        """.strip()

        await self._send_message(message)

    async def send_error_alert(self, error_type: str, error_message: str):
        """Send critical error alert"""
        if not self.enabled:
            return

        message = f"""
🚨 **ERROR ALERT**

**Type:** {error_type}
**Message:** {error_message}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please check the logs and bot status.
        """.strip()

        await self._send_message(message, urgent=True)

    async def _send_message(self, message: str, color: str = "blue", urgent: bool = False):
        """Send message to all configured channels"""
        tasks = []

        if self.discord_webhook:
            tasks.append(self._send_discord(message, color, urgent))

        if self.telegram_token and self.telegram_chat_id:
            tasks.append(self._send_telegram(message, urgent))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_discord(self, message: str, color: str = "blue", urgent: bool = False):
        """Send message via Discord webhook"""
        try:
            # Color mapping
            colors = {
                "green": 0x00FF00,
                "red": 0xFF0000,
                "blue": 0x0099FF,
                "yellow": 0xFFFF00,
                "orange": 0xFF9900
            }
            embed_color = colors.get(color, colors["blue"])

            # Create embed
            embed = {
                "description": message,
                "color": embed_color,
                "timestamp": datetime.utcnow().isoformat()
            }

            payload = {
                "embeds": [embed]
            }

            # Add @everyone mention for urgent messages
            if urgent:
                payload["content"] = "@everyone"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.discord_webhook,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 204:
                        logger.debug("[DISCORD] Message sent successfully")
                    else:
                        logger.warning(f"[DISCORD] Unexpected response: {response.status}")

        except Exception as e:
            logger.error(f"[DISCORD] Failed to send message: {e}")

    async def _send_telegram(self, message: str, urgent: bool = False):
        """Send message via Telegram bot"""
        try:
            # Telegram uses Markdown formatting
            telegram_message = message.replace('**', '*').replace('`', '`')

            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

            payload = {
                "chat_id": self.telegram_chat_id,
                "text": telegram_message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }

            # Add notification sound for urgent messages
            if urgent:
                payload["disable_notification"] = False
            else:
                payload["disable_notification"] = True

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.debug("[TELEGRAM] Message sent successfully")
                    else:
                        text = await response.text()
                        logger.warning(f"[TELEGRAM] Failed: {response.status} - {text}")

        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send message: {e}")

    async def test_notifications(self):
        """Test notification channels"""
        if not self.enabled:
            logger.warning("[NOTIFICATIONS] No channels configured")
            return False

        message = """
🧪 **TEST NOTIFICATION**

This is a test message from your trading bot.
If you see this, notifications are working correctly!

Time: {time}
        """.format(time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        await self._send_message(message)
        logger.info("[NOTIFICATIONS] Test message sent")
        return True
