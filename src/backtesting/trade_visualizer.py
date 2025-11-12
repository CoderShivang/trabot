"""
Trade visualizer for generating chart snapshots with indicators and S/R zones
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.dates import DateFormatter
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TradeVisualizer:
    def __init__(self, config, binance_client):
        self.config = config
        self.client = binance_client
        self.output_dir = Path("backtest_charts")
        self.output_dir.mkdir(exist_ok=True)

    async def generate_trade_chart(
        self,
        trade: Dict[str, Any],
        market_context: Any,
        sr_zones: List[Dict],
        trade_num: int
    ):
        """
        Generate a chart snapshot for a single trade showing:
        - Price action (candlesticks)
        - EMAs (20, 50, 200)
        - VWAP
        - S/R zones
        - Entry point marker
        """
        try:
            symbol = trade['symbol']
            entry_time = trade['entry_time']
            entry_price = trade['entry_price']
            direction = trade['direction']

            # Fetch 4 hours of 1-minute data centered around entry
            lookback_ms = 2 * 60 * 60 * 1000  # 2 hours before
            lookahead_ms = 2 * 60 * 60 * 1000  # 2 hours after
            start_time = entry_time - lookback_ms
            end_time = entry_time + lookahead_ms

            # Get klines
            klines = await self.client.get_klines(
                symbol=symbol,
                interval='1m',
                limit=240,  # 4 hours
                start_time=start_time,
                end_time=end_time
            )

            if not klines or len(klines) < 50:
                logger.warning(f"Not enough data to generate chart for trade {trade_num}")
                return None

            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'qav', 'num_trades', 'tb_base', 'tb_quote', 'ignore'
            ])

            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            # Calculate indicators
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean() if len(df) >= 200 else df['ema50']

            # VWAP
            df['tp'] = (df['high'] + df['low'] + df['close']) / 3
            df['vwap'] = (df['tp'] * df['volume']).cumsum() / df['volume'].cumsum()

            # Create figure
            fig, ax = plt.subplots(figsize=(16, 10))

            # Plot candlesticks (simplified as high-low lines with close markers)
            for idx, row in df.iterrows():
                color = 'green' if row['close'] >= row['open'] else 'red'
                ax.plot([row['timestamp'], row['timestamp']],
                       [row['low'], row['high']],
                       color=color, linewidth=0.5, alpha=0.3)
                ax.plot(row['timestamp'], row['close'], 'o',
                       color=color, markersize=1.5)

            # Plot EMAs
            ax.plot(df['timestamp'], df['ema20'], label='EMA 20',
                   color='blue', linewidth=1.5, alpha=0.7)
            ax.plot(df['timestamp'], df['ema50'], label='EMA 50',
                   color='orange', linewidth=1.5, alpha=0.7)
            ax.plot(df['timestamp'], df['ema200'], label='EMA 200',
                   color='red', linewidth=1.5, alpha=0.7)

            # Plot VWAP
            ax.plot(df['timestamp'], df['vwap'], label='VWAP',
                   color='purple', linewidth=2, linestyle='--', alpha=0.8)

            # Plot S/R zones
            if sr_zones:
                for zone in sr_zones[:10]:  # Top 10 zones
                    level = zone['level']
                    strength = zone.get('strength', 5)
                    zone_type = zone.get('type', 'unknown')

                    # Color and alpha based on strength
                    alpha = min(0.2 + (strength / 10) * 0.3, 0.5)
                    color = 'red' if zone_type == 'resistance' else 'green'

                    # Draw horizontal zone
                    zone_size = level * 0.003  # 0.3% zone
                    ax.axhline(y=level, color=color, linestyle=':',
                              linewidth=1, alpha=alpha)
                    ax.axhspan(level - zone_size, level + zone_size,
                              color=color, alpha=alpha * 0.3)

                    # Label
                    ax.text(df['timestamp'].iloc[-1], level,
                           f" {zone_type[:1].upper()} {strength:.1f}",
                           fontsize=8, color=color, alpha=0.7,
                           verticalalignment='center')

            # Mark entry point
            entry_dt = pd.to_datetime(entry_time, unit='ms')
            entry_color = 'darkgreen' if direction == 'LONG' else 'darkred'
            entry_marker = '^' if direction == 'LONG' else 'v'

            ax.scatter([entry_dt], [entry_price],
                      color=entry_color, s=200, marker=entry_marker,
                      edgecolors='black', linewidths=2, zorder=10,
                      label=f'{direction} Entry')

            # Annotate entry
            ax.annotate(f'{direction}\n${entry_price:,.2f}',
                       xy=(entry_dt, entry_price),
                       xytext=(0, 40 if direction == 'LONG' else -40),
                       textcoords='offset points',
                       fontsize=10, fontweight='bold',
                       color=entry_color,
                       bbox=dict(boxstyle='round,pad=0.5',
                                facecolor='white', edgecolor=entry_color, linewidth=2),
                       arrowprops=dict(arrowstyle='->',
                                     connectionstyle='arc3,rad=0',
                                     color=entry_color, linewidth=2))

            # Mark exit if available
            if 'exit_price' in trade and trade['exit_price']:
                exit_dt = pd.to_datetime(trade['exit_time'], unit='ms')
                exit_price = trade['exit_price']
                exit_color = 'blue'

                ax.scatter([exit_dt], [exit_price],
                          color=exit_color, s=150, marker='x',
                          linewidths=3, zorder=10,
                          label=f'Exit: {trade.get("exit_reason", "unknown")}')

            # Formatting
            ax.set_xlabel('Time (UTC+5:30 IST)', fontsize=12, fontweight='bold')
            ax.set_ylabel('Price (USDT)', fontsize=12, fontweight='bold')

            # Title with trade details
            regime = market_context.regime.upper() if hasattr(market_context, 'regime') else 'UNKNOWN'
            adx = market_context.adx if hasattr(market_context, 'adx') else 0

            title = f"Trade #{trade_num} - {direction} {symbol}\n"
            title += f"Entry: {entry_dt.strftime('%Y-%m-%d %H:%M:%S')} IST | "
            title += f"Price: ${entry_price:,.2f} | "
            title += f"Regime: {regime} (ADX={adx:.1f})"

            if 'net_pnl' in trade:
                pnl = trade['net_pnl']
                pnl_color = 'green' if pnl >= 0 else 'red'
                title += f" | P&L: ${pnl:+.2f}"

            ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

            # Legend
            ax.legend(loc='upper left', fontsize=10, framealpha=0.9)

            # Grid
            ax.grid(True, alpha=0.3, linestyle='--')

            # Format x-axis dates
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
            plt.xticks(rotation=45)

            # Tight layout
            plt.tight_layout()

            # Save
            filename = f"trade_{trade_num:03d}_{symbol}_{direction}_{entry_dt.strftime('%Y%m%d_%H%M')}.png"
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()

            logger.info(f"Generated chart: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Error generating chart for trade {trade_num}: {e}")
            return None

    async def generate_all_trade_charts(
        self,
        trades: List[Dict],
        contexts: List[Any],
        sr_zones_list: List[List[Dict]]
    ):
        """Generate charts for all trades in a backtest"""

        logger.info(f"Generating charts for {len(trades)} trades...")

        chart_paths = []
        for i, trade in enumerate(trades, 1):
            context = contexts[i-1] if i-1 < len(contexts) else None
            sr_zones = sr_zones_list[i-1] if i-1 < len(sr_zones_list) else []

            if context:
                chart_path = await self.generate_trade_chart(
                    trade=trade,
                    market_context=context,
                    sr_zones=sr_zones,
                    trade_num=i
                )

                if chart_path:
                    chart_paths.append(chart_path)

        logger.info(f"Generated {len(chart_paths)} charts in {self.output_dir}")

        return chart_paths
