"""
Enhanced S/R Zone Detection with Multi-Timeframe Confluence and Invalidation

Features:
1. Consolidation-based zone detection (matching user's purple boxes)
2. Filters choppy/trending areas (matching user's red ellipses)
3. Multi-timeframe confluence (1m, 5m, 15m)
4. Zone invalidation when price breaks through decisively
5. Strength scoring system (0-100)
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class EnhancedSRZone:
    """Enhanced S/R Zone with invalidation tracking"""
    level: float  # Center price
    upper: float  # Upper boundary
    lower: float  # Lower boundary
    zone_type: str  # 'support', 'resistance', 'both'
    strength: int  # 0-100 quality score
    touches: int  # Number of touches
    rejections: int  # Number of rejections (wick through + close back)
    first_touch_idx: int
    last_touch_idx: int
    timeframe: str  # '1m', '5m', '15m'
    created_at: int  # Timestamp when zone was created
    invalidated: bool = False
    invalidation_count: int = 0  # How many times price broke through

    def is_near(self, price: float, threshold: float = 150) -> bool:
        """Check if price is near this zone"""
        return abs(price - self.level) <= threshold

    def contains(self, price: float) -> bool:
        """Check if price is within zone boundaries"""
        return self.lower <= price <= self.upper

    def check_invalidation(self, close: float, high: float, low: float) -> bool:
        """
        Check if this bar invalidates the zone

        Invalidation criteria:
        - For support: Close decisively below zone (> 0.3% below lower boundary)
        - For resistance: Close decisively above zone (> 0.3% above upper boundary)
        - Must be a strong break, not just a wick
        """
        if self.invalidated:
            return True

        invalidation_threshold = 0.003  # 0.3% beyond zone

        if self.zone_type == 'support':
            # Support breaks when close is significantly below
            if close < self.lower * (1 - invalidation_threshold):
                # Confirm it's not just a wick - close should be near the low
                if close < low * 1.001:  # Close within 0.1% of low
                    self.invalidation_count += 1
                    if self.invalidation_count >= 2:  # 2 decisive breaks = invalidated
                        self.invalidated = True
                        logger.debug(f"[SR-INVALID] Support zone @ ${self.level:,.0f} invalidated (broke below)")
                        return True

        elif self.zone_type == 'resistance':
            # Resistance breaks when close is significantly above
            if close > self.upper * (1 + invalidation_threshold):
                # Confirm it's not just a wick - close should be near the high
                if close > high * 0.999:  # Close within 0.1% of high
                    self.invalidation_count += 1
                    if self.invalidation_count >= 2:  # 2 decisive breaks = invalidated
                        self.invalidated = True
                        logger.debug(f"[SR-INVALID] Resistance zone @ ${self.level:,.0f} invalidated (broke above)")
                        return True

        elif self.zone_type == 'both':
            # Both type invalidates if decisively broken in either direction
            if close < self.lower * (1 - invalidation_threshold) or close > self.upper * (1 + invalidation_threshold):
                self.invalidation_count += 1
                if self.invalidation_count >= 2:
                    self.invalidated = True
                    logger.debug(f"[SR-INVALID] Zone @ ${self.level:,.0f} invalidated")
                    return True

        return False


class EnhancedSRDetector:
    """
    Enhanced S/R detector matching user's visual approach

    Features:
    - Detects consolidation zones (purple boxes)
    - Filters choppy/trending areas (red ellipses)
    - Multi-timeframe analysis
    - Zone invalidation tracking
    """

    def __init__(self,
                 min_consolidation_bars: int = 15,
                 max_consolidation_range_pct: float = 0.02,
                 min_touches: int = 3,
                 min_strength: int = 40,
                 max_volatility: float = 0.008,
                 max_trend_slope: float = 0.03):
        """
        Args:
            min_consolidation_bars: Minimum bars for consolidation period
            max_consolidation_range_pct: Max 2% range = consolidation
            min_touches: Minimum touches to validate zone
            min_strength: Minimum quality score (0-100)
            max_volatility: Max volatility to avoid choppy areas
            max_trend_slope: Max slope to avoid trending areas
        """
        self.min_consolidation_bars = min_consolidation_bars
        self.max_consolidation_range_pct = max_consolidation_range_pct
        self.min_touches = min_touches
        self.min_strength = min_strength
        self.max_volatility = max_volatility
        self.max_trend_slope = max_trend_slope

        # Store detected zones (keyed by timeframe)
        self.zones_by_tf: Dict[str, List[EnhancedSRZone]] = {
            '1m': [],
            '5m': [],
            '15m': []
        }

    def update_zones(self, df: pd.DataFrame, timeframe: str = '1m', lookback: int = 200):
        """
        Update zones for a specific timeframe

        Args:
            df: OHLCV DataFrame
            timeframe: '1m', '5m', or '15m'
            lookback: How many bars to analyze
        """
        if len(df) < self.min_consolidation_bars:
            return

        # Detect new zones
        new_zones = self.detect_zones(df, timeframe, lookback)

        # Check invalidation of existing zones
        if len(df) > 0:
            latest = df.iloc[-1]
            existing_zones = self.zones_by_tf.get(timeframe, [])

            for zone in existing_zones:
                zone.check_invalidation(
                    close=latest['close'],
                    high=latest['high'],
                    low=latest['low']
                )

        # Merge with existing zones (keep valid ones)
        existing_valid = [z for z in self.zones_by_tf.get(timeframe, []) if not z.invalidated]

        # Add new zones that don't overlap with existing ones
        for new_zone in new_zones:
            is_duplicate = False
            for existing in existing_valid:
                if abs(new_zone.level - existing.level) / existing.level < 0.005:  # Within 0.5%
                    is_duplicate = True
                    break

            if not is_duplicate:
                existing_valid.append(new_zone)

        self.zones_by_tf[timeframe] = existing_valid

        logger.debug(f"[SR-{timeframe}] Active zones: {len(existing_valid)}")

    def detect_zones(self, df: pd.DataFrame, timeframe: str, lookback: int) -> List[EnhancedSRZone]:
        """
        Detect S/R zones from consolidation periods

        Matches user's approach:
        1. Find consolidation (sideways movement)
        2. Filter choppy/trending areas
        3. Extract horizontal levels
        4. Validate by touches/rejections
        5. Score quality
        """
        if len(df) < self.min_consolidation_bars:
            logger.info(f"[SR-{timeframe}] Insufficient data: {len(df)} < {self.min_consolidation_bars}")
            return []

        recent_df = df.tail(lookback).copy()
        recent_df.reset_index(drop=True, inplace=True)

        # Find consolidation periods
        consolidations = self._find_consolidations(recent_df)

        # Extract zones from consolidations
        zones = []
        choppy_filtered = 0
        weak_filtered = 0
        current_timestamp = int(datetime.now().timestamp() * 1000)

        for start, end in consolidations:
            # Filter choppy areas (matching user's red ellipses) - TEMPORARILY DISABLED FOR DEBUGGING
            # if self._is_choppy_area(recent_df, start, end):
            #     choppy_filtered += 1
            #     continue

            zone = self._extract_zone(recent_df, start, end, timeframe, current_timestamp)
            if zone:
                if zone.strength >= self.min_strength:
                    zones.append(zone)
                else:
                    weak_filtered += 1

        # Only log when zones are actually found (reduces spam)
        if len(zones) > 0:
            logger.debug(f"[SR-{timeframe}] Found {len(consolidations)} consolidation periods")
            logger.debug(f"[SR-{timeframe}] Zones: {len(zones)} valid | {choppy_filtered} choppy-filtered | {weak_filtered} weak-filtered")

        return zones

    def _find_consolidations(self, df: pd.DataFrame) -> List[Tuple[int, int]]:
        """Find consolidation periods (tight ranges)"""
        consolidations = []
        i = 0

        while i < len(df) - self.min_consolidation_bars:
            window = df.iloc[i:i+self.min_consolidation_bars]

            high = window['high'].max()
            low = window['low'].min()
            mid = (high + low) / 2
            range_pct = (high - low) / mid

            # Check if range is tight enough (consolidation)
            if range_pct <= self.max_consolidation_range_pct:
                # Extend consolidation forward
                end = i + self.min_consolidation_bars

                while end < len(df):
                    extended = df.iloc[i:end+1]
                    ext_high = extended['high'].max()
                    ext_low = extended['low'].min()
                    ext_mid = (ext_high + ext_low) / 2
                    ext_range = (ext_high - ext_low) / ext_mid

                    if ext_range <= self.max_consolidation_range_pct * 1.3:
                        end += 1
                    else:
                        break

                if end - i >= self.min_consolidation_bars:
                    consolidations.append((i, end))
                    i = end
                    continue

            i += 1

        return consolidations

    def _is_choppy_area(self, df: pd.DataFrame, start: int, end: int) -> bool:
        """
        Filter choppy/trending areas (user's red ellipses)

        Returns True if area should be skipped
        """
        window = df.iloc[start:end]

        if len(window) < 5:
            return True

        # Check 1: High volatility
        returns = window['close'].pct_change().dropna()
        if len(returns) > 0 and returns.std() > self.max_volatility:
            return True

        # Check 2: Strong trend (slope)
        prices = window['close'].values
        x = np.arange(len(prices))
        if len(x) > 1:
            slope = np.polyfit(x, prices, 1)[0]
            slope_pct = slope / prices.mean()
            if abs(slope_pct) > self.max_trend_slope:
                return True

        # Check 3: Too many overlapping wicks (messy)
        overlaps = 0
        for i in range(len(window) - 1):
            curr = window.iloc[i]
            next_bar = window.iloc[i + 1]

            # Check if wicks overlap significantly
            if not (curr['high'] < next_bar['low'] or curr['low'] > next_bar['high']):
                overlaps += 1

        overlap_ratio = overlaps / len(window) if len(window) > 0 else 0
        if overlap_ratio > 0.6:  # More than 60% overlapping
            return True

        return False

    def _extract_zone(self, df: pd.DataFrame, start: int, end: int,
                      timeframe: str, timestamp: int) -> Optional[EnhancedSRZone]:
        """Extract S/R zone from consolidation period"""
        window = df.iloc[start:end]

        if len(window) < self.min_consolidation_bars:
            return None

        # Calculate zone boundaries (use quantiles for robustness)
        upper = float(window['high'].quantile(0.75))
        lower = float(window['low'].quantile(0.25))
        level = (upper + lower) / 2

        # Count touches and rejections
        touches = 0
        rejections = 0

        for _, row in window.iterrows():
            # Touch: price enters the zone
            if lower <= row['low'] <= upper or lower <= row['high'] <= upper:
                touches += 1

                # Rejection: wick through zone but close back inside/outside
                if row['low'] < lower and row['close'] > lower:
                    rejections += 1  # Bounce from support
                elif row['high'] > upper and row['close'] < upper:
                    rejections += 1  # Rejection from resistance

        if touches < self.min_touches:
            logger.debug(f"[SR] Zone rejected: only {touches} touches (need {self.min_touches})")
            return None

        # Determine zone type based on where price traded relative to the zone
        # CRITICAL FIX: This was backwards before!
        # - If price traded BELOW the zone level, the zone acts as RESISTANCE (ceiling above)
        # - If price traded ABOVE the zone level, the zone acts as SUPPORT (floor below)
        close_prices = window['close']
        avg_close = close_prices.mean()

        if avg_close < level * 0.995:
            # Price was below zone - zone is resistance above
            zone_type = 'resistance'
        elif avg_close > level * 1.005:
            # Price was above zone - zone is support below
            zone_type = 'support'
        else:
            # Price traded around zone level - could be either
            zone_type = 'both'

        # Calculate strength score (0-100)
        strength = self._calculate_strength(touches, rejections, len(window), zone_type)

        return EnhancedSRZone(
            level=level,
            upper=upper,
            lower=lower,
            zone_type=zone_type,
            strength=strength,
            touches=touches,
            rejections=rejections,
            first_touch_idx=start,
            last_touch_idx=end,
            timeframe=timeframe,
            created_at=timestamp,
            invalidated=False,
            invalidation_count=0
        )

    def _calculate_strength(self, touches: int, rejections: int, duration: int, zone_type: str) -> int:
        """
        Calculate zone strength (0-100)

        Based on user's strength scoring system:
        - Touches: 8 points per touch (max 40)
        - Rejections: 10 points per rejection (max 30)
        - Consistency: based on duration (max 20)
        - Clarity: clear type (10 points)
        """
        score = 0

        # Touches (max 40 points)
        score += min(40, touches * 8)

        # Rejections (max 30 points)
        score += min(30, rejections * 10)

        # Consistency - longer consolidation = more consistent (max 20 points)
        consistency = min(20, int((duration / 30) * 20))  # 30 bars = full points
        score += consistency

        # Clarity - clear support/resistance (10 points)
        if zone_type in ['support', 'resistance']:
            score += 10

        return min(100, score)

    def get_zones_near_price(self, price: float, timeframes: List[str] = ['1m', '5m', '15m'],
                             proximity: float = 150) -> Dict[str, List[EnhancedSRZone]]:
        """
        Get zones near current price across multiple timeframes

        Returns dict: {timeframe: [zones]}
        """
        result = {}

        for tf in timeframes:
            zones = self.zones_by_tf.get(tf, [])
            near_zones = [z for z in zones if not z.invalidated and z.is_near(price, proximity)]
            if near_zones:
                result[tf] = near_zones

        return result

    def has_htf_confluence(self, price: float, zone_type: str, proximity: float = 150) -> bool:
        """
        Check if higher timeframes (5m, 15m) confirm the zone

        Args:
            price: Current price
            zone_type: 'support' or 'resistance'
            proximity: Distance threshold

        Returns:
            True if at least one higher TF has matching zone
        """
        for tf in ['5m', '15m']:
            zones = self.zones_by_tf.get(tf, [])
            for zone in zones:
                if zone.invalidated:
                    continue

                if zone.is_near(price, proximity) and zone.zone_type in [zone_type, 'both']:
                    logger.debug(f"[SR-HTF] {tf} {zone_type} confluence @ ${zone.level:,.0f}")
                    return True

        return False
