"""
Advanced Support/Resistance Zone Detection
Mimics manual trader's approach: consolidation-based, not just pivots

Key Characteristics:
1. Zones are HORIZONTAL RANGES, not single price levels
2. Only marked in CONSOLIDATION (not trending/choppy markets)
3. Zones where price "spent time" (multiple touches, sideways action)
4. Validated by subsequent reactions (bounces/breaks)
5. Avoid marking in choppy areas (no clear range)
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional
from dataclasses import dataclass
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class SRZone:
    """Support/Resistance zone with validation metrics"""
    upper: float
    lower: float
    center: float
    strength: int  # Number of touches
    zone_type: str  # 'support', 'resistance', 'range'
    time_spent: int  # Bars spent in zone
    volume_at_zone: float  # Total volume traded at this level
    first_touch: int  # Bar index
    last_touch: int  # Bar index
    validated: bool = False  # Has price reacted to it after formation?
    confidence: float = 0.0  # 0-1, based on multiple factors


class ConsolidationSRDetector:
    """
    Detects S/R zones matching manual trading style:
    1. Find consolidation periods (low volatility, range-bound)
    2. Extract price ranges from consolidations
    3. Filter out choppy/trending markets
    4. Validate zones by future price action
    """

    def __init__(self,
                 min_consolidation_bars: int = 15,
                 max_consolidation_range_pct: float = 0.02,
                 min_touches: int = 3,
                 atr_period: int = 14):
        """
        Args:
            min_consolidation_bars: Minimum candles for valid consolidation
            max_consolidation_range_pct: Max price range % for consolidation (2% = tight range)
            min_touches: Minimum price touches to confirm zone
            atr_period: Period for ATR calculation (volatility)
        """
        self.min_consolidation_bars = min_consolidation_bars
        self.max_consolidation_range_pct = max_consolidation_range_pct
        self.min_touches = min_touches
        self.atr_period = atr_period

    def detect_zones(self, df: pd.DataFrame) -> List[SRZone]:
        """
        Main detection pipeline

        Args:
            df: OHLCV DataFrame with columns: ['open', 'high', 'low', 'close', 'volume']

        Returns:
            List of validated S/R zones
        """
        if len(df) < self.min_consolidation_bars * 2:
            logger.warning("[SR] Not enough data for consolidation detection")
            return []

        # Step 1: Calculate market regime indicators
        df = self._add_regime_indicators(df)

        # Step 2: Identify consolidation periods
        consolidations = self._find_consolidation_periods(df)

        logger.info(f"[SR] Found {len(consolidations)} consolidation periods")

        # Step 3: Extract zones from consolidations
        zones = []
        for consol in consolidations:
            zone = self._extract_zone_from_consolidation(df, consol)
            if zone:
                zones.append(zone)

        logger.info(f"[SR] Extracted {len(zones)} zones from consolidations")

        # Step 4: Merge overlapping zones
        zones = self._merge_overlapping_zones(zones)

        logger.info(f"[SR] After merging: {len(zones)} zones")

        # Step 5: Validate zones with future price action
        zones = self._validate_zones(df, zones)

        # Step 6: Filter by confidence
        zones = [z for z in zones if z.confidence >= 0.6]

        logger.info(f"[SR] Final high-confidence zones: {len(zones)}")

        return sorted(zones, key=lambda z: z.confidence, reverse=True)

    def _add_regime_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add indicators to detect market regime"""
        df = df.copy()

        # ATR for volatility
        high = df['high']
        low = df['low']
        close = df['close']
        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(self.atr_period).mean()

        # Normalized ATR (ATR as % of price)
        df['atr_pct'] = df['atr'] / df['close']

        # Rolling range
        lookback = 20
        df['range_high'] = df['high'].rolling(lookback).max()
        df['range_low'] = df['low'].rolling(lookback).min()
        df['range_pct'] = (df['range_high'] - df['range_low']) / df['close']

        # EMA for trend detection
        df['ema20'] = df['close'].ewm(span=20).mean()
        df['ema50'] = df['close'].ewm(span=50).mean()

        # Trend strength
        df['trend_strength'] = abs(df['ema20'] - df['ema50']) / df['close']

        return df

    def _find_consolidation_periods(self, df: pd.DataFrame) -> List[Tuple[int, int]]:
        """Find consolidation periods (tight ranges, not choppy)"""
        consolidations = []
        i = 0

        while i < len(df) - self.min_consolidation_bars:
            if self._is_consolidation_start(df, i):
                end = self._find_consolidation_end(df, i)

                if end - i >= self.min_consolidation_bars:
                    consolidations.append((i, end))
                    logger.debug(f"[SR] Consolidation found: bars {i}-{end} ({end-i} candles)")
                    i = end
                else:
                    i += 1
            else:
                i += 1

        return consolidations

    def _is_consolidation_start(self, df: pd.DataFrame, idx: int) -> bool:
        """Check if index could be start of consolidation"""
        if idx + 10 >= len(df):
            return False

        window = df.iloc[idx:idx+10]

        # Check criteria
        avg_atr_pct = window['atr_pct'].mean()
        range_pct = (window['high'].max() - window['low'].min()) / window['close'].mean()
        avg_trend_strength = window['trend_strength'].mean()

        # Consolidation = low volatility + tight range + weak trend
        is_low_volatility = avg_atr_pct < 0.01
        is_tight_range = range_pct < self.max_consolidation_range_pct
        is_weak_trend = avg_trend_strength < 0.005

        return is_low_volatility and is_tight_range and is_weak_trend

    def _find_consolidation_end(self, df: pd.DataFrame, start: int) -> int:
        """Find where consolidation ends"""
        end = start + self.min_consolidation_bars

        baseline_window = df.iloc[start:start+10]
        baseline_atr_pct = baseline_window['atr_pct'].mean()
        baseline_center = (baseline_window['high'].max() + baseline_window['low'].min()) / 2

        while end < len(df):
            current = df.iloc[end]

            atr_spike = current['atr_pct'] > baseline_atr_pct * 2
            range_break = (current['close'] > baseline_center * 1.02) or \
                         (current['close'] < baseline_center * 0.98)
            trend_formed = current['trend_strength'] > 0.015

            if atr_spike or range_break or trend_formed:
                break

            end += 1

        return end

    def _extract_zone_from_consolidation(self, df: pd.DataFrame,
                                        consol: Tuple[int, int]) -> Optional[SRZone]:
        """Extract S/R zone from consolidation period"""
        start, end = consol
        window = df.iloc[start:end]

        if len(window) < self.min_consolidation_bars:
            return None

        # Calculate zone boundaries using percentiles
        upper = window['high'].quantile(0.75)
        lower = window['low'].quantile(0.25)

        # VWAP as center
        typical_price = (window['high'] + window['low'] + window['close']) / 3
        vwap = (typical_price * window['volume']).sum() / window['volume'].sum()

        # Count touches
        touches = self._count_zone_touches(df, lower, upper, start, end)

        if touches < self.min_touches:
            return None

        time_spent = end - start
        volume_at_zone = window['volume'].sum()

        # Determine zone type
        close_prices = window['close'].values
        if np.mean(close_prices) > vwap:
            zone_type = 'resistance'
        elif np.mean(close_prices) < vwap:
            zone_type = 'support'
        else:
            zone_type = 'range'

        confidence = self._calculate_initial_confidence(
            touches, time_spent, len(df), volume_at_zone
        )

        return SRZone(
            upper=upper,
            lower=lower,
            center=vwap,
            strength=touches,
            zone_type=zone_type,
            time_spent=time_spent,
            volume_at_zone=volume_at_zone,
            first_touch=start,
            last_touch=end,
            confidence=confidence
        )

    def _count_zone_touches(self, df: pd.DataFrame, lower: float, upper: float,
                           start: int, end: int) -> int:
        """Count how many times price touched this zone"""
        window = df.iloc[start:end]
        touches = 0

        for _, row in window.iterrows():
            if (lower <= row['high'] <= upper) or (lower <= row['low'] <= upper):
                touches += 1

        return touches

    def _merge_overlapping_zones(self, zones: List[SRZone]) -> List[SRZone]:
        """Merge zones that overlap significantly"""
        if not zones:
            return []

        zones = sorted(zones, key=lambda z: z.center)

        merged = []
        current = zones[0]

        for next_zone in zones[1:]:
            overlap = self._calculate_overlap(current, next_zone)

            if overlap > 0.5:
                current = self._merge_two_zones(current, next_zone)
            else:
                merged.append(current)
                current = next_zone

        merged.append(current)
        return merged

    def _calculate_overlap(self, zone1: SRZone, zone2: SRZone) -> float:
        """Calculate overlap ratio between two zones"""
        overlap_upper = min(zone1.upper, zone2.upper)
        overlap_lower = max(zone1.lower, zone2.lower)

        if overlap_upper <= overlap_lower:
            return 0.0

        overlap_size = overlap_upper - overlap_lower
        zone1_size = zone1.upper - zone1.lower
        zone2_size = zone2.upper - zone2.lower
        avg_size = (zone1_size + zone2_size) / 2

        return overlap_size / avg_size

    def _merge_two_zones(self, zone1: SRZone, zone2: SRZone) -> SRZone:
        """Merge two overlapping zones"""
        return SRZone(
            upper=max(zone1.upper, zone2.upper),
            lower=min(zone1.lower, zone2.lower),
            center=(zone1.center + zone2.center) / 2,
            strength=zone1.strength + zone2.strength,
            zone_type=zone1.zone_type if zone1.strength >= zone2.strength else zone2.zone_type,
            time_spent=max(zone1.time_spent, zone2.time_spent),
            volume_at_zone=zone1.volume_at_zone + zone2.volume_at_zone,
            first_touch=min(zone1.first_touch, zone2.first_touch),
            last_touch=max(zone1.last_touch, zone2.last_touch),
            confidence=(zone1.confidence + zone2.confidence) / 2
        )

    def _validate_zones(self, df: pd.DataFrame, zones: List[SRZone]) -> List[SRZone]:
        """Validate zones by checking future price action"""
        for zone in zones:
            future_data = df.iloc[zone.last_touch:]

            if len(future_data) < 5:
                continue

            bounces, breaks = self._check_zone_reactions(future_data, zone)

            if bounces > 0 or breaks > 0:
                zone.validated = True
                zone.confidence = min(1.0, zone.confidence + (bounces * 0.1) - (breaks * 0.05))

        return zones

    def _check_zone_reactions(self, df: pd.DataFrame, zone: SRZone) -> Tuple[int, int]:
        """Check how price reacted to zone after formation"""
        bounces = 0
        breaks = 0

        for i in range(len(df) - 1):
            current = df.iloc[i]
            next_candle = df.iloc[i + 1]

            touched = (zone.lower <= current['low'] <= zone.upper) or \
                     (zone.lower <= current['high'] <= zone.upper)

            if not touched:
                continue

            if zone.zone_type == 'support' or zone.zone_type == 'range':
                if next_candle['close'] > current['close']:
                    bounces += 1
                elif next_candle['close'] < zone.lower:
                    breaks += 1

            elif zone.zone_type == 'resistance':
                if next_candle['close'] < current['close']:
                    bounces += 1
                elif next_candle['close'] > zone.upper:
                    breaks += 1

        return bounces, breaks

    def _calculate_initial_confidence(self, touches: int, time_spent: int,
                                     total_bars: int, volume: float) -> float:
        """Calculate initial confidence score (0-1)"""
        touch_score = min(1.0, touches / 10)
        time_score = min(1.0, time_spent / 50)
        recency_score = 0.7
        volume_score = 0.6

        confidence = (
            touch_score * 0.3 +
            time_score * 0.3 +
            recency_score * 0.2 +
            volume_score * 0.2
        )

        return confidence
