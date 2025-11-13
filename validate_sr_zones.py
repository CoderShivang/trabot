"""
S/R Zone Validation Backtest
This script ONLY detects and visualizes S/R zones - no trading logic

Purpose: Validate that the algorithm detects zones like you do manually
"""

import asyncio
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from src.data.binance_client import BinanceClient
from src.strategy.consolidation_sr import ConsolidationSRDetector
from src.utils.logger import setup_logger
from config.config_loader import load_config

logger = setup_logger(__name__)


class SRZoneValidator:
    """Validates S/R zone detection without trading"""

    def __init__(self, config):
        self.config = config
        self.binance_client = BinanceClient(config)

        # Initialize S/R detector with configurable parameters
        self.sr_detector = ConsolidationSRDetector(
            min_consolidation_bars=15,  # Minimum bars for consolidation
            max_consolidation_range_pct=0.02,  # 2% max range
            min_touches=3,  # Minimum touches to confirm zone
            atr_period=14
        )

    async def validate_zones(self, symbol: str, days: int = 7):
        """
        Run zone detection on historical data and generate visualization

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            days: Number of days to analyze
        """
        logger.info(f"[VALIDATION] Starting S/R zone detection for {symbol} ({days} days)")

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        logger.info(f"[VALIDATION] Date range: {start_date.date()} to {end_date.date()}")

        # Fetch historical data
        logger.info(f"[VALIDATION] Fetching 15m klines...")
        klines_15m = await self._fetch_klines(symbol, '15m', start_date, end_date)

        if not klines_15m:
            logger.error("[VALIDATION] Failed to fetch klines")
            return

        logger.info(f"[VALIDATION] Fetched {len(klines_15m)} candles")

        # Convert to DataFrame
        df = self._klines_to_df(klines_15m)

        # Detect zones
        logger.info(f"[VALIDATION] Running S/R zone detection...")
        zones = self.sr_detector.detect_zones(df)

        logger.info(f"[VALIDATION] Detected {len(zones)} S/R zones")

        # Display zone details
        self._display_zones(zones, symbol)

        # Save results
        results = {
            'symbol': symbol,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_candles': len(df),
            'zones_detected': len(zones),
            'zones': [
                {
                    'upper': float(z.upper),
                    'lower': float(z.lower),
                    'center': float(z.center),
                    'type': z.zone_type,
                    'strength': z.strength,
                    'confidence': float(z.confidence),
                    'validated': z.validated,
                    'time_spent': z.time_spent,
                    'first_touch_idx': z.first_touch,
                    'last_touch_idx': z.last_touch
                }
                for z in zones
            ]
        }

        # Save to JSON
        results_dir = Path('data/sr_validation')
        results_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(datetime.now(timezone.utc).timestamp())
        results_file = results_dir / f'sr_zones_{symbol}_{timestamp}.json'

        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"[VALIDATION] Results saved to: {results_file}")

        # Generate HTML visualization
        html_file = await self._generate_visualization(df, zones, symbol, timestamp)
        logger.info(f"[VALIDATION] Visualization saved to: {html_file}")
        logger.info(f"[VALIDATION] Open the HTML file in your browser to see the zones!")

        return zones

    async def _fetch_klines(self, symbol: str, timeframe: str,
                           start_date: datetime, end_date: datetime):
        """Fetch historical klines"""
        all_klines = []

        timeframe_ms = self._timeframe_to_ms(timeframe)
        current_start = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        while current_start < end_ts:
            chunk_end = min(current_start + (1000 * timeframe_ms), end_ts)

            klines = await self.binance_client.get_klines(
                symbol=symbol,
                interval=timeframe,
                start_time=current_start,
                end_time=chunk_end
            )

            if not klines:
                break

            all_klines.extend(klines)
            logger.info(f"[VALIDATION] Fetched {len(klines)} candles (total: {len(all_klines)})")

            if klines:
                current_start = klines[-1][0] + timeframe_ms
            else:
                break

            await asyncio.sleep(0.5)

        return all_klines

    def _timeframe_to_ms(self, timeframe: str) -> int:
        """Convert timeframe to milliseconds"""
        units = {'m': 60000, 'h': 3600000, 'd': 86400000}
        return int(timeframe[:-1]) * units[timeframe[-1]]

    def _klines_to_df(self, klines) -> pd.DataFrame:
        """Convert klines to DataFrame"""
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        return df

    def _display_zones(self, zones, symbol):
        """Display detected zones in console"""
        logger.info(f"\n{'='*80}")
        logger.info(f"DETECTED S/R ZONES FOR {symbol}")
        logger.info(f"{'='*80}\n")

        for i, zone in enumerate(zones, 1):
            logger.info(f"Zone #{i} ({zone.zone_type.upper()})")
            logger.info(f"  Price Range: ${zone.lower:,.2f} - ${zone.upper:,.2f}")
            logger.info(f"  Center: ${zone.center:,.2f}")
            logger.info(f"  Strength: {zone.strength} touches")
            logger.info(f"  Confidence: {zone.confidence:.2f}")
            logger.info(f"  Validated: {'Yes' if zone.validated else 'No'}")
            logger.info(f"  Time Spent: {zone.time_spent} candles")
            logger.info("")

        logger.info(f"{'='*80}\n")

    async def _generate_visualization(self, df: pd.DataFrame, zones, symbol: str, timestamp: int):
        """Generate HTML visualization with Plotly"""
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            logger.error("[VALIDATION] Plotly not installed. Run: pip install plotly")
            return None

        # Create figure
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            subplot_titles=(f'{symbol} - S/R Zones', 'Volume'),
            vertical_spacing=0.05
        )

        # Add candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=df['timestamp'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price'
            ),
            row=1, col=1
        )

        # Add S/R zones as rectangles
        for zone in zones:
            # Color based on type and confidence
            if zone.zone_type == 'support':
                color = f'rgba(0, 255, 0, {zone.confidence * 0.3})'
                border_color = f'rgba(0, 255, 0, {zone.confidence})'
            elif zone.zone_type == 'resistance':
                color = f'rgba(255, 0, 0, {zone.confidence * 0.3})'
                border_color = f'rgba(255, 0, 0, {zone.confidence})'
            else:  # range
                color = f'rgba(138, 43, 226, {zone.confidence * 0.3})'
                border_color = f'rgba(138, 43, 226, {zone.confidence})'

            # Add rectangle
            fig.add_shape(
                type="rect",
                x0=df['timestamp'].iloc[zone.first_touch],
                x1=df['timestamp'].iloc[-1],
                y0=zone.lower,
                y1=zone.upper,
                fillcolor=color,
                line=dict(color=border_color, width=2),
                layer="below",
                row=1, col=1
            )

            # Add label
            fig.add_annotation(
                x=df['timestamp'].iloc[zone.first_touch],
                y=zone.center,
                text=f"{zone.zone_type.upper()}<br>${zone.center:,.0f}<br>Conf: {zone.confidence:.2f}",
                showarrow=False,
                xanchor="left",
                font=dict(size=10, color=border_color),
                row=1, col=1
            )

        # Add volume
        fig.add_trace(
            go.Bar(
                x=df['timestamp'],
                y=df['volume'],
                name='Volume',
                marker_color='rgba(128, 128, 128, 0.5)'
            ),
            row=2, col=1
        )

        # Update layout
        fig.update_layout(
            title=f'{symbol} S/R Zone Validation',
            xaxis_title='Time',
            yaxis_title='Price',
            xaxis2_title='Time',
            yaxis2_title='Volume',
            hovermode='x unified',
            showlegend=True,
            height=800
        )

        # Remove rangeslider
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)

        # Save to HTML
        results_dir = Path('data/sr_validation')
        html_file = results_dir / f'sr_zones_{symbol}_{timestamp}.html'

        fig.write_html(str(html_file))

        return html_file


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Validate S/R Zone Detection')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading pair')
    parser.add_argument('--days', type=int, default=7, help='Number of days to analyze')

    args = parser.parse_args()

    # Load config
    config = load_config('config/bot_config.yaml')

    # Run validation
    validator = SRZoneValidator(config)
    zones = await validator.validate_zones(args.symbol, args.days)

    logger.info(f"\n{'='*80}")
    logger.info("VALIDATION COMPLETE!")
    logger.info(f"{'='*80}")
    logger.info(f"Detected {len(zones)} high-confidence S/R zones")
    logger.info("Check the HTML file to see the zones visualized on the chart")
    logger.info(f"{'='*80}\n")


if __name__ == '__main__':
    asyncio.run(main())
