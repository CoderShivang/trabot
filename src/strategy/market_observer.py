"""
Adaptive Market Observer
Tracks market behavior during Asian session to identify:
- Which MAs price is most sensitive to
- Dynamic S/R zones from higher timeframes
- Volatility patterns (ATR)
- Session-based behavior changes
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class SessionObservation:
    """Observations from a trading session"""
    session: str  # 'asian', 'london', 'ny'
    start_time: datetime
    end_time: datetime

    # MA sensitivity (how many times price reacted to each MA)
    ema20_touches: int = 0
    ema50_touches: int = 0
    ema200_touches: int = 0
    vwap_touches: int = 0

    # Most sensitive MA
    dominant_ma: str = "none"

    # S/R zones discovered
    sr_zones: List[Dict] = field(default_factory=list)

    # Volatility
    avg_atr: float = 0.0
    max_atr: float = 0.0
    min_atr: float = 0.0

    # Price range
    session_high: float = 0.0
    session_low: float = 0.0
    session_range: float = 0.0


class MarketObserver:
    """
    Observes market behavior to adapt trading strategy
    Tracks Asian session to set up London/NY trades
    """

    def __init__(self, config):
        self.config = config

        # Session definitions (UTC)
        self.sessions = {
            'asian': (time(0, 0), time(8, 0)),     # 00:00 - 08:00 UTC
            'london': (time(8, 0), time(16, 0)),   # 08:00 - 16:00 UTC
            'ny': (time(13, 0), time(21, 0)),      # 13:00 - 21:00 UTC (overlap with London)
        }

        # Daily observations
        self.daily_observations: Dict[str, SessionObservation] = {}

        # Current session tracking
        self.current_session = None
        self.session_start = None

        # Adaptive thresholds
        self.min_atr_threshold = 80  # Minimum ATR to trade (will adapt)
        self.ma_sensitivity_threshold = 3  # Minimum touches to consider MA dominant

    def get_session(self, timestamp: int) -> str:
        """Determine which session a timestamp belongs to"""
        dt = datetime.fromtimestamp(timestamp / 1000)
        current_time = dt.time()

        # Check each session
        for session_name, (start, end) in self.sessions.items():
            if start <= current_time < end:
                return session_name

        return 'after_hours'

    def should_trade_now(self, timestamp: int, atr: float) -> Tuple[bool, str]:
        """
        Determine if we should trade based on session and volatility

        Returns: (should_trade, reason)
        """
        session = self.get_session(timestamp)

        # Don't trade during Asian session (low liquidity, use for observation)
        if session == 'asian':
            return False, "Asian session - observation only"

        # Don't trade after hours
        if session == 'after_hours':
            return False, "After hours - no trading"

        # Check ATR threshold
        if atr < self.min_atr_threshold:
            return False, f"ATR too low ({atr:.1f} < {self.min_atr_threshold})"

        # All checks passed
        return True, f"{session.capitalize()} session - good to trade"

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)

        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]

        return float(atr) if not pd.isna(atr) else 0.0

    def detect_ma_sensitivity(
        self,
        df: pd.DataFrame,
        current_price: float
    ) -> Tuple[str, Dict[str, int]]:
        """
        Detect which MA price is most sensitive to
        Counts how many times price touched/reacted to each MA
        """
        # Calculate MAs
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean() if len(df) >= 200 else df['ema50']

        # Calculate VWAP
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (df['tp'] * df['volume']).cumsum() / df['volume'].cumsum()

        # Count touches (price within 0.1% of MA)
        touch_threshold = 0.001  # 0.1%

        touches = {
            'ema20': 0,
            'ema50': 0,
            'ema200': 0,
            'vwap': 0
        }

        for idx in range(len(df)):
            price = df['close'].iloc[idx]
            high = df['high'].iloc[idx]
            low = df['low'].iloc[idx]

            # Check if candle touched each MA
            for ma_name in ['ema20', 'ema50', 'ema200', 'vwap']:
                ma_value = df[ma_name].iloc[idx]

                if pd.isna(ma_value):
                    continue

                # Touch if high/low crosses MA or price very close to MA
                if low <= ma_value <= high:
                    touches[ma_name] += 1
                elif abs(price - ma_value) / price < touch_threshold:
                    touches[ma_name] += 1

        # Find dominant MA
        dominant_ma = max(touches, key=touches.get)

        # Only consider dominant if it has significant touches
        if touches[dominant_ma] < self.ma_sensitivity_threshold:
            dominant_ma = "none"

        logger.info(f"[OBSERVER] MA Sensitivity: {touches} | Dominant: {dominant_ma}")

        return dominant_ma, touches

    def build_htf_sr_zones(
        self,
        klines_1m: List,
        klines_5m: List,
        klines_15m: List,
        klines_1h: List,
        current_price: float
    ) -> List[Dict]:
        """
        Build S/R zones from multiple higher timeframes
        Focuses on levels where price found support/resistance
        """
        zones = []

        # Helper function to find swing highs/lows
        def find_swing_points(df: pd.DataFrame, lookback: int = 5):
            highs = []
            lows = []

            for i in range(lookback, len(df) - lookback):
                # Swing high: higher than surrounding candles
                if all(df['high'].iloc[i] >= df['high'].iloc[i-j] for j in range(1, lookback+1)) and \
                   all(df['high'].iloc[i] >= df['high'].iloc[i+j] for j in range(1, lookback+1)):
                    highs.append(df['high'].iloc[i])

                # Swing low: lower than surrounding candles
                if all(df['low'].iloc[i] <= df['low'].iloc[i-j] for j in range(1, lookback+1)) and \
                   all(df['low'].iloc[i] <= df['low'].iloc[i+j] for j in range(1, lookback+1)):
                    lows.append(df['low'].iloc[i])

            return highs, lows

        # Process each timeframe
        timeframes = [
            ('5m', klines_5m, 3, 0.002),    # 5m: lookback=3, zone_size=0.2%
            ('15m', klines_15m, 5, 0.003),  # 15m: lookback=5, zone_size=0.3%
            ('1h', klines_1h, 3, 0.005),    # 1h: lookback=3, zone_size=0.5%
        ]

        for tf_name, klines, lookback, zone_size_pct in timeframes:
            if not klines or len(klines) < lookback * 2 + 1:
                continue

            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'qav', 'num_trades', 'tb_base', 'tb_quote', 'ignore'
            ])

            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)

            # Find swing points
            swing_highs, swing_lows = find_swing_points(df, lookback)

            # Create resistance zones from swing highs
            for level in swing_highs:
                distance_pct = abs(current_price - level) / current_price

                # Only include zones within 2% of current price
                if distance_pct < 0.02:
                    zones.append({
                        'level': float(level),
                        'type': 'resistance',
                        'timeframe': tf_name,
                        'zone_size': level * zone_size_pct,
                        'distance_pct': distance_pct,
                        'strength': 5.0 + (0.02 - distance_pct) * 100  # Closer = stronger
                    })

            # Create support zones from swing lows
            for level in swing_lows:
                distance_pct = abs(current_price - level) / current_price

                if distance_pct < 0.02:
                    zones.append({
                        'level': float(level),
                        'type': 'support',
                        'timeframe': tf_name,
                        'zone_size': level * zone_size_pct,
                        'distance_pct': distance_pct,
                        'strength': 5.0 + (0.02 - distance_pct) * 100
                    })

        # Sort by distance (closest first)
        zones.sort(key=lambda x: x['distance_pct'])

        logger.info(f"[OBSERVER] Built {len(zones)} HTF S/R zones from 5m/15m/1h")

        return zones[:10]  # Return top 10 closest zones

    def observe_session(
        self,
        timestamp: int,
        klines_1m: List,
        klines_5m: List,
        klines_15m: List,
        klines_1h: List,
        current_price: float
    ) -> Optional[SessionObservation]:
        """
        Observe current session and build intelligence
        Call this periodically during Asian session
        """
        session = self.get_session(timestamp)
        dt = datetime.fromtimestamp(timestamp / 1000)

        # Only observe Asian session actively
        if session != 'asian':
            return None

        # Convert 1m klines to DataFrame
        if not klines_1m or len(klines_1m) < 50:
            return None

        df = pd.DataFrame(klines_1m[-200:], columns=[  # Last 200 candles (~3 hours)
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'tb_base', 'tb_quote', 'ignore'
        ])

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        # Detect MA sensitivity
        dominant_ma, touches = self.detect_ma_sensitivity(df, current_price)

        # Calculate ATR
        atr = self.calculate_atr(df)

        # Build HTF S/R zones
        sr_zones = self.build_htf_sr_zones(
            klines_1m[-200:],
            klines_5m,
            klines_15m,
            klines_1h,
            current_price
        )

        # Create observation
        observation = SessionObservation(
            session='asian',
            start_time=dt.replace(hour=0, minute=0, second=0),
            end_time=dt,
            ema20_touches=touches['ema20'],
            ema50_touches=touches['ema50'],
            ema200_touches=touches['ema200'],
            vwap_touches=touches['vwap'],
            dominant_ma=dominant_ma,
            sr_zones=sr_zones,
            avg_atr=atr,
            session_high=float(df['high'].max()),
            session_low=float(df['low'].min()),
            session_range=float(df['high'].max() - df['low'].min())
        )

        # Store for later use
        date_key = dt.strftime('%Y-%m-%d')
        self.daily_observations[date_key] = observation

        logger.info(f"[OBSERVER] Asian session observation complete:")
        logger.info(f"  Dominant MA: {dominant_ma} (touches: {touches})")
        logger.info(f"  ATR: {atr:.2f}")
        logger.info(f"  S/R Zones: {len(sr_zones)} identified")
        logger.info(f"  Range: ${observation.session_low:.2f} - ${observation.session_high:.2f}")

        return observation

    def get_todays_observation(self, timestamp: int) -> Optional[SessionObservation]:
        """Get Asian session observation for today (to use during London/NY)"""
        dt = datetime.fromtimestamp(timestamp / 1000)
        date_key = dt.strftime('%Y-%m-%d')
        return self.daily_observations.get(date_key)

    def should_respect_ma(self, ma_name: str, timestamp: int) -> bool:
        """
        Check if we should pay attention to this MA based on Asian session observations
        """
        observation = self.get_todays_observation(timestamp)

        if not observation:
            return True  # No observation yet, respect all MAs

        # If this MA was dominant in Asian, definitely respect it
        if observation.dominant_ma == ma_name:
            return True

        # Check touch count threshold
        touch_count = getattr(observation, f'{ma_name}_touches', 0)
        return touch_count >= self.ma_sensitivity_threshold
