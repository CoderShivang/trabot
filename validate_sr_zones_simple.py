"""
S/R Zone Validation - Standalone Version
Simple script that works without full bot infrastructure
"""

import asyncio
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.strategy.consolidation_sr import ConsolidationSRDetector

# Simple Binance REST client using requests
import requests


class SimpleBinanceClient:
    """Minimal Binance client for fetching klines"""

    BASE_URL = "https://api.binance.com/api/v3"

    def get_klines(self, symbol: str, interval: str, limit: int = 1000,
                   start_time: int = None, end_time: int = None):
        """Fetch klines from Binance"""
        url = f"{self.BASE_URL}/klines"

        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }

        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching klines: {e}")
            return []


class SRZoneValidator:
    """Validates S/R zone detection without trading"""

    def __init__(self):
        self.binance_client = SimpleBinanceClient()

        # Initialize S/R detector
        self.sr_detector = ConsolidationSRDetector(
            min_consolidation_bars=15,
            max_consolidation_range_pct=0.02,
            min_touches=3,
            atr_period=14
        )

    def validate_zones(self, symbol: str = 'BTCUSDT', days: int = 7):
        """Run zone detection on historical data"""
        print(f"\n{'='*80}")
        print(f"S/R ZONE VALIDATION: {symbol} ({days} days)")
        print(f"{'='*80}\n")

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        print(f"Date range: {start_date.date()} to {end_date.date()}")

        # Fetch historical data
        print(f"Fetching 15m klines...")
        klines_15m = self._fetch_klines(symbol, '15m', start_date, end_date)

        if not klines_15m:
            print("ERROR: Failed to fetch klines")
            return []

        print(f"Fetched {len(klines_15m)} candles")

        # Convert to DataFrame
        df = self._klines_to_df(klines_15m)

        # Detect zones
        print(f"\nRunning S/R zone detection...")
        zones = self.sr_detector.detect_zones(df)

        print(f"\nDetected {len(zones)} high-confidence S/R zones\n")

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

        print(f"\nResults saved to: {results_file}")

        # Generate HTML visualization
        html_file = self._generate_visualization(df, zones, symbol, timestamp)
        print(f"Visualization saved to: {html_file}")
        print(f"\nOpen the HTML file in your browser to see the zones!\n")

        return zones

    def _fetch_klines(self, symbol: str, timeframe: str,
                     start_date: datetime, end_date: datetime):
        """Fetch historical klines"""
        all_klines = []

        timeframe_ms = self._timeframe_to_ms(timeframe)
        current_start = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        while current_start < end_ts:
            chunk_end = min(current_start + (1000 * timeframe_ms), end_ts)

            klines = self.binance_client.get_klines(
                symbol=symbol,
                interval=timeframe,
                start_time=current_start,
                end_time=chunk_end
            )

            if not klines:
                break

            all_klines.extend(klines)
            print(f"  Fetched {len(klines)} candles (total: {len(all_klines)})", end='\r')

            if klines:
                current_start = klines[-1][0] + timeframe_ms
            else:
                break

        print()  # New line after progress
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
        print(f"{'='*80}")
        print(f"DETECTED S/R ZONES FOR {symbol}")
        print(f"{'='*80}\n")

        if not zones:
            print("No zones detected. Try:")
            print("  - Increase max_consolidation_range_pct (allow wider ranges)")
            print("  - Decrease min_touches (require fewer touches)")
            print("  - Decrease min_consolidation_bars (shorter consolidations)")
            print()
            return

        for i, zone in enumerate(zones, 1):
            # Color code by type
            if zone.zone_type == 'support':
                label = "[SUPPORT]"
            elif zone.zone_type == 'resistance':
                label = "[RESISTANCE]"
            else:
                label = "[RANGE]"

            print(f"Zone #{i} {label}")
            print(f"  Price Range: ${zone.lower:,.2f} - ${zone.upper:,.2f}")
            print(f"  Center: ${zone.center:,.2f}")
            print(f"  Strength: {zone.strength} touches")
            print(f"  Confidence: {zone.confidence:.2%}")
            print(f"  Validated: {'Yes' if zone.validated else 'No'}")
            print(f"  Time Spent: {zone.time_spent} candles")
            print()

        print(f"{'='*80}\n")

    def _generate_visualization(self, df: pd.DataFrame, zones, symbol: str, timestamp: int):
        """Generate HTML visualization with Plotly"""
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            print("WARNING: Plotly not installed. Skipping visualization.")
            print("Install with: pip install plotly")
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
                text=f"{zone.zone_type.upper()}<br>${zone.center:,.0f}<br>{zone.confidence:.0%}",
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
            title=f'{symbol} S/R Zone Validation - Consolidation-Based Detection',
            xaxis_title='Time',
            yaxis_title='Price',
            xaxis2_title='Time',
            yaxis2_title='Volume',
            hovermode='x unified',
            showlegend=True,
            height=800,
            template='plotly_dark'
        )

        # Remove rangeslider
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)

        # Save to HTML
        results_dir = Path('data/sr_validation')
        html_file = results_dir / f'sr_zones_{symbol}_{timestamp}.html'

        fig.write_html(str(html_file))

        return html_file


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Validate S/R Zone Detection')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading pair')
    parser.add_argument('--days', type=int, default=7, help='Number of days to analyze')

    args = parser.parse_args()

    # Run validation
    validator = SRZoneValidator()
    zones = validator.validate_zones(args.symbol, args.days)

    print(f"{'='*80}")
    print("VALIDATION COMPLETE!")
    print(f"{'='*80}")
    print(f"Detected {len(zones)} high-confidence S/R zones")
    print("Check the HTML file in data/sr_validation/ to see zones on chart")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    main()
