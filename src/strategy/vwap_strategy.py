"""
VWAP + Enhanced S/R Strategy for 1-Minute Scalping

Based on user's trading approach:
1. Session-based VWAP with ±1σ and ±2σ bands
2. Enhanced S/R zones with multi-timeframe confluence (1m, 5m, 15m)
3. Zone invalidation tracking
4. Choppy/trending area filtering
5. Mean reversion trades at VWAP bands + S/R confluence
6. Trend continuation on pullbacks to bands
7. All orders are LIMIT orders (lower fees)

Entry Types:
- LONG: -1σ + support (mean reversion) OR pullback to +1σ in uptrend
- SHORT: +1σ + resistance (mean reversion) OR pullback to -1σ in downtrend
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
from src.utils.logger import setup_logger
from src.strategy.enhanced_sr_detector import EnhancedSRDetector, EnhancedSRZone

logger = setup_logger(__name__)


@dataclass
class VWAPBands:
    """VWAP with standard deviation bands"""
    vwap: float
    std: float
    upper_1std: float
    lower_1std: float
    upper_2std: float
    lower_2std: float

    def distance_to_band(self, price: float, band: str) -> float:
        """Calculate distance from price to band in dollars"""
        bands = {
            'vwap': self.vwap,
            'upper_1std': self.upper_1std,
            'lower_1std': self.lower_1std,
            'upper_2std': self.upper_2std,
            'lower_2std': self.lower_2std
        }
        return abs(price - bands[band])


@dataclass
class SRZone:
    """Support/Resistance Zone from consolidation"""
    level: float  # Center price
    upper: float  # Upper boundary
    lower: float  # Lower boundary
    zone_type: str  # 'support', 'resistance', 'both'
    strength: int  # 0-100 quality score
    touches: int  # Number of touches
    first_touch_idx: int
    last_touch_idx: int

    def is_near(self, price: float, threshold: float = 150) -> bool:
        """Check if price is near this zone"""
        return abs(price - self.level) <= threshold

    def contains(self, price: float) -> bool:
        """Check if price is within zone boundaries"""
        return self.lower <= price <= self.upper


@dataclass
class TradeSignal:
    """Trade entry signal"""
    direction: str  # 'LONG' or 'SHORT'
    signal_type: str  # 'mean_reversion' or 'trend_continuation'
    entry_price: float  # Limit order price
    stop_loss: float
    take_profit: float
    confidence: float  # 0-100
    reason: str  # Human-readable explanation
    vwap_band: float
    sr_zone: Optional[EnhancedSRZone]
    htf_confluence: bool = False  # Whether 5m/15m confirms zone


class VWAPCalculator:
    """Session-based VWAP calculator"""

    def calculate(self, df: pd.DataFrame) -> VWAPBands:
        """
        Calculate VWAP bands for current session (matching TradingView's method)

        TradingView VWAP uses:
        - Source: hlc3 (typical price)
        - Session reset: Daily (timeframe.change("D"))
        - Stdev: Calculated from RUNNING vwap, not final vwap

        This implementation matches TradingView's ta.vwap() function.
        """
        if len(df) < 1:
            raise ValueError("Insufficient data for VWAP calculation")

        # Filter to TODAY'S session only (session reset like TradingView)
        # Get current date (last bar's date)
        current_date = pd.to_datetime(df.iloc[-1]['timestamp']).date()

        # Filter to bars from today only
        df = df.copy()
        df['date'] = pd.to_datetime(df['timestamp']).dt.date
        session_df = df[df['date'] == current_date].copy()

        if len(session_df) < 2:
            # If not enough session data, use last 50 bars as fallback
            session_df = df.tail(50).copy()

        df = session_df

        # Calculate typical price (hlc3 in TradingView)
        typical_price = (df['high'] + df['low'] + df['close']) / 3

        # VWAP = cumulative(price * volume) / cumulative(volume)
        cumulative_pv = (typical_price * df['volume']).cumsum()
        cumulative_volume = df['volume'].cumsum()

        # Running VWAP at each bar (matches TradingView's progressive calculation)
        running_vwap = cumulative_pv / cumulative_volume

        # Current VWAP (last value)
        vwap = float(running_vwap.iloc[-1])

        # Calculate standard deviation using RUNNING vwap (TradingView method)
        # At each bar, deviation is from the VWAP value at that bar, not final VWAP
        squared_diff = (typical_price - running_vwap) ** 2
        cumulative_variance = (squared_diff * df['volume']).cumsum() / cumulative_volume
        std = float(np.sqrt(cumulative_variance.iloc[-1]))

        return VWAPBands(
            vwap=vwap,
            std=std,
            upper_1std=vwap + std,
            lower_1std=vwap - std,
            upper_2std=vwap + (std * 2),
            lower_2std=vwap - (std * 2)
        )


class SimpleConsolidationDetector:
    """
    Detects S/R zones from consolidation periods
    Based on user's chart examples (white boxes)
    """

    def __init__(self, min_bars: int = 20, max_range_pct: float = 0.015):
        self.min_bars = min_bars
        self.max_range_pct = max_range_pct

    def detect_zones(self, df: pd.DataFrame, lookback: int = 200) -> List[SRZone]:
        """
        Detect S/R zones from price consolidations

        Args:
            df: OHLCV DataFrame
            lookback: How many bars to analyze

        Returns:
            List of SRZone objects
        """
        if len(df) < self.min_bars:
            return []

        # Use recent data
        recent_df = df.tail(lookback).copy()
        recent_df.reset_index(drop=True, inplace=True)

        # Find consolidation periods
        consolidations = self._find_consolidations(recent_df)

        # Extract zones from consolidations
        zones = []
        for start, end in consolidations:
            zone = self._extract_zone(recent_df, start, end)
            if zone:
                zones.append(zone)

        # Merge overlapping zones
        zones = self._merge_zones(zones)

        logger.debug(f"[VWAP-SR] Detected {len(zones)} consolidation zones")

        return zones

    def _find_consolidations(self, df: pd.DataFrame) -> List[Tuple[int, int]]:
        """Find consolidation periods (tight ranges)"""
        consolidations = []
        i = 0

        while i < len(df) - self.min_bars:
            window = df.iloc[i:i+self.min_bars]

            high = window['high'].max()
            low = window['low'].min()
            mid = (high + low) / 2
            range_pct = (high - low) / mid

            # Check if range is tight enough
            if range_pct <= self.max_range_pct:
                # Extend consolidation forward
                end = i + self.min_bars

                while end < len(df):
                    extended = df.iloc[i:end+1]
                    ext_high = extended['high'].max()
                    ext_low = extended['low'].min()
                    ext_mid = (ext_high + ext_low) / 2
                    ext_range = (ext_high - ext_low) / ext_mid

                    if ext_range <= self.max_range_pct * 1.3:
                        end += 1
                    else:
                        break

                if end - i >= self.min_bars:
                    consolidations.append((i, end))
                    i = end
                    continue

            i += 1

        return consolidations

    def _extract_zone(self, df: pd.DataFrame, start: int, end: int) -> Optional[SRZone]:
        """Extract S/R zone from consolidation period"""
        window = df.iloc[start:end]

        if len(window) < self.min_bars:
            return None

        # Calculate zone boundaries
        upper = float(window['high'].quantile(0.75))
        lower = float(window['low'].quantile(0.25))
        level = (upper + lower) / 2

        # Count touches
        touches = 0
        for _, row in window.iterrows():
            if lower <= row['low'] <= upper or lower <= row['high'] <= upper:
                touches += 1

        if touches < 3:  # Need at least 3 touches
            return None

        # Determine zone type based on position
        close_prices = window['close']
        if close_prices.mean() < level:
            zone_type = 'resistance'
        elif close_prices.mean() > level:
            zone_type = 'support'
        else:
            zone_type = 'both'

        # Calculate strength
        strength = min(100, int((touches / len(window)) * 100 + (end - start) / 2))

        return SRZone(
            level=level,
            upper=upper,
            lower=lower,
            zone_type=zone_type,
            strength=strength,
            touches=touches,
            first_touch_idx=start,
            last_touch_idx=end
        )

    def _merge_zones(self, zones: List[SRZone]) -> List[SRZone]:
        """Merge overlapping zones"""
        if not zones:
            return []

        zones = sorted(zones, key=lambda z: z.level)
        merged = [zones[0]]

        for zone in zones[1:]:
            last = merged[-1]

            # Check for overlap
            if abs(zone.level - last.level) / last.level < 0.005:  # Within 0.5%
                # Merge
                merged[-1] = SRZone(
                    level=(last.level + zone.level) / 2,
                    upper=max(last.upper, zone.upper),
                    lower=min(last.lower, zone.lower),
                    zone_type=last.zone_type if last.strength >= zone.strength else zone.zone_type,
                    strength=max(last.strength, zone.strength),
                    touches=last.touches + zone.touches,
                    first_touch_idx=min(last.first_touch_idx, zone.first_touch_idx),
                    last_touch_idx=max(last.last_touch_idx, zone.last_touch_idx)
                )
            else:
                merged.append(zone)

        return merged


class VWAPStrategy:
    """
    VWAP + Enhanced S/R Strategy

    Trading Rules:
    1. Mean Reversion LONG: Price near -1σ + at support zone (with HTF confluence)
    2. Mean Reversion SHORT: Price near +1σ + at resistance zone (with HTF confluence)
    3. Trend Continuation LONG: Price > all bands, pullback to +1σ
    4. Trend Continuation SHORT: Price < all bands, pullback to -1σ
    5. Zone invalidation tracking to avoid failed zones
    """

    def __init__(self, config=None):
        self.config = config or {}

        # Components
        self.vwap_calc = VWAPCalculator()
        self.sr_detector = EnhancedSRDetector(
            min_consolidation_bars=8,  # Reduced from 10 for more zones
            max_consolidation_range_pct=0.03,  # Increased from 2.5% to 3% for BTC volatility
            min_touches=2,  # Reduced from 3 to allow zones with fewer touches
            min_strength=20,  # Lowered from 30 to allow weaker zones
            max_volatility=0.015,  # Increased from 1.2% to 1.5% to be less strict
            max_trend_slope=0.10  # Increased from 5% to 10% to allow more trending areas
        )

        # Parameters (can be tuned)
        self.target_points = self.config.get('target_points', 200)  # TP in dollars
        self.stop_points = self.config.get('stop_points', 150)  # SL in dollars
        self.band_proximity = self.config.get('band_proximity', 300)  # How close to band (increased for BTC volatility)
        self.zone_proximity = self.config.get('zone_proximity', 500)  # How close to S/R (increased for BTC)
        self.min_zone_strength = self.config.get('min_zone_strength', 20)  # Min zone quality (lowered to match detector)
        self.require_htf_confluence = self.config.get('require_htf_confluence', False)  # Require 5m/15m confirmation

        # State
        self.current_zones = []
        self._analyze_count = 0  # For periodic logging

    def analyze(self, df: pd.DataFrame, current_price: float,
                df_5m: Optional[pd.DataFrame] = None,
                df_15m: Optional[pd.DataFrame] = None) -> List[TradeSignal]:
        """
        Analyze market and find trade setups with multi-timeframe confluence

        Args:
            df: 1m OHLCV DataFrame with recent candles
            current_price: Current market price
            df_5m: Optional 5m OHLCV DataFrame for HTF zones
            df_15m: Optional 15m OHLCV DataFrame for HTF zones

        Returns:
            List of TradeSignal objects (sorted by confidence)
        """
        if len(df) < 50:
            logger.warning("[VWAP] Insufficient data for analysis")
            return []

        # Update S/R zones for all timeframes
        self.sr_detector.update_zones(df, timeframe='1m', lookback=200)

        if df_5m is not None and len(df_5m) >= 50:
            self.sr_detector.update_zones(df_5m, timeframe='5m', lookback=100)

        if df_15m is not None and len(df_15m) >= 50:
            self.sr_detector.update_zones(df_15m, timeframe='15m', lookback=100)

        # Get zones near current price (only active, not invalidated)
        zones_near_price = self.sr_detector.get_zones_near_price(
            current_price,
            timeframes=['1m'],
            proximity=self.zone_proximity
        )

        # Filter by strength
        strong_zones = [z for z in zones_near_price.get('1m', [])
                       if z.strength >= self.min_zone_strength and not z.invalidated]

        # Debug logging - always log zone stats
        all_1m_zones = self.sr_detector.zones_by_tf.get('1m', [])
        logger.info(f"[VWAP-SR] Total 1m zones: {len(all_1m_zones)} | Near price (+/-${self.zone_proximity}): {len(zones_near_price.get('1m', []))} | Strong (>={self.min_zone_strength}): {len(strong_zones)}")

        if strong_zones:
            for zone in strong_zones[:3]:  # Log first 3
                logger.info(f"  Zone @ ${zone.level:,.0f} ({zone.zone_type}, str:{zone.strength})")

        # Calculate VWAP
        try:
            vwap = self.vwap_calc.calculate(df)
        except ValueError as e:
            logger.error(f"[VWAP] Error calculating VWAP: {e}")
            return []

        # Determine market bias
        bias = self._determine_bias(current_price, vwap)

        # Debug VWAP info - always log when zones exist
        self._analyze_count += 1
        if len(strong_zones) > 0:
            dist_to_lower = vwap.distance_to_band(current_price, 'lower_1std')
            dist_to_upper = vwap.distance_to_band(current_price, 'upper_1std')
            logger.info(f"[VWAP] Price: ${current_price:,.0f} | VWAP: ${vwap.vwap:,.0f} | -1s: ${vwap.lower_1std:,.0f} (dist:{dist_to_lower:.0f}) | +1s: ${vwap.upper_1std:,.0f} (dist:{dist_to_upper:.0f}) | Bias: {bias}")

        # Find trade setups
        signals = []

        # === LONG SETUPS ===

        # 1. Mean Reversion Long: -1s + Support
        if bias in ['bullish_mean_reversion', 'neutral']:
            dist_to_lower = vwap.distance_to_band(current_price, 'lower_1std')

            if dist_to_lower <= self.band_proximity:
                support_zones = [z for z in strong_zones if z.zone_type in ['support', 'both']]
                if len(support_zones) > 0:
                    logger.info(f"[CHECK-LONG-MR] Found {len(support_zones)} support zones near -1s band (dist:{dist_to_lower:.0f} <= {self.band_proximity})")
            else:
                if len(strong_zones) > 0:
                    logger.info(f"[SKIP-LONG-MR] Distance to -1s band too far: {dist_to_lower:.0f} > {self.band_proximity}")

            if dist_to_lower <= self.band_proximity:

                for zone in strong_zones:
                    if zone.zone_type in ['support', 'both'] and zone.is_near(current_price, self.zone_proximity):
                        # Check HTF confluence
                        has_htf = self.sr_detector.has_htf_confluence(
                            current_price,
                            zone_type='support',
                            proximity=self.zone_proximity
                        )

                        # Skip if HTF required but not present
                        if self.require_htf_confluence and not has_htf:
                            logger.debug(f"[VWAP-SR] Skipping LONG at ${zone.level:,.0f} - no HTF confluence")
                            continue

                        confidence = self._calculate_confluence(zone, bias, dist_to_lower, has_htf)

                        if confidence >= 50:  # Lowered from 65 for initial testing
                            entry = max(zone.level - 30, current_price - 50)

                            htf_str = " + HTF✓" if has_htf else ""
                            signals.append(TradeSignal(
                                direction='LONG',
                                signal_type='mean_reversion',
                                entry_price=entry,
                                stop_loss=entry - self.stop_points,
                                take_profit=entry + self.target_points,
                                confidence=confidence,
                                reason=f"LONG Mean Reversion: -1std (${vwap.lower_1std:,.0f}) + Support ${zone.level:,.0f} (str:{zone.strength}){htf_str}",
                                vwap_band=vwap.lower_1std,
                                sr_zone=zone,
                                htf_confluence=has_htf
                            ))

        # 2. Trend Continuation Long: Uptrend + Pullback to +1σ
        if bias == 'strong_bullish':
            dist_to_upper = vwap.distance_to_band(current_price, 'upper_1std')

            if dist_to_upper <= self.band_proximity:
                for zone in strong_zones:
                    if zone.is_near(current_price, self.zone_proximity):
                        # Check HTF confluence (less strict for trend continuation)
                        has_htf = self.sr_detector.has_htf_confluence(
                            current_price,
                            zone_type='support',
                            proximity=self.zone_proximity
                        )

                        confidence = self._calculate_confluence(zone, bias, dist_to_upper, has_htf)

                        if confidence >= 50:  # Lowered from 60 for initial testing
                            entry = min(vwap.upper_1std, zone.level) - 20

                            htf_str = " + HTF✓" if has_htf else ""
                            signals.append(TradeSignal(
                                direction='LONG',
                                signal_type='trend_continuation',
                                entry_price=entry,
                                stop_loss=entry - self.stop_points,
                                take_profit=entry + self.target_points,
                                confidence=confidence,
                                reason=f"LONG Trend: Pullback to +1std (${vwap.upper_1std:,.0f}) in uptrend{htf_str}",
                                vwap_band=vwap.upper_1std,
                                sr_zone=zone,
                                htf_confluence=has_htf
                            ))

        # === SHORT SETUPS ===

        # 3. Mean Reversion Short: +1σ + Resistance
        if bias in ['bearish_mean_reversion', 'neutral']:
            dist_to_upper = vwap.distance_to_band(current_price, 'upper_1std')

            if dist_to_upper <= self.band_proximity:
                for zone in strong_zones:
                    if zone.zone_type in ['resistance', 'both'] and zone.is_near(current_price, self.zone_proximity):
                        # Check HTF confluence
                        has_htf = self.sr_detector.has_htf_confluence(
                            current_price,
                            zone_type='resistance',
                            proximity=self.zone_proximity
                        )

                        # Skip if HTF required but not present
                        if self.require_htf_confluence and not has_htf:
                            logger.debug(f"[VWAP-SR] Skipping SHORT at ${zone.level:,.0f} - no HTF confluence")
                            continue

                        confidence = self._calculate_confluence(zone, bias, dist_to_upper, has_htf)

                        if confidence >= 50:  # Lowered from 65 for initial testing
                            entry = min(zone.level + 30, current_price + 50)

                            htf_str = " + HTF✓" if has_htf else ""
                            signals.append(TradeSignal(
                                direction='SHORT',
                                signal_type='mean_reversion',
                                entry_price=entry,
                                stop_loss=entry + self.stop_points,
                                take_profit=entry - self.target_points,
                                confidence=confidence,
                                reason=f"SHORT Mean Reversion: +1std (${vwap.upper_1std:,.0f}) + Resistance ${zone.level:,.0f} (str:{zone.strength}){htf_str}",
                                vwap_band=vwap.upper_1std,
                                sr_zone=zone,
                                htf_confluence=has_htf
                            ))

        # 4. Trend Continuation Short: Downtrend + Pullback to -1σ
        if bias == 'strong_bearish':
            dist_to_lower = vwap.distance_to_band(current_price, 'lower_1std')

            if dist_to_lower <= self.band_proximity:
                for zone in strong_zones:
                    if zone.is_near(current_price, self.zone_proximity):
                        # Check HTF confluence (less strict for trend continuation)
                        has_htf = self.sr_detector.has_htf_confluence(
                            current_price,
                            zone_type='resistance',
                            proximity=self.zone_proximity
                        )

                        confidence = self._calculate_confluence(zone, bias, dist_to_lower, has_htf)

                        if confidence >= 50:  # Lowered from 60 for initial testing
                            entry = max(vwap.lower_1std, zone.level) + 20

                            htf_str = " + HTF✓" if has_htf else ""
                            signals.append(TradeSignal(
                                direction='SHORT',
                                signal_type='trend_continuation',
                                entry_price=entry,
                                stop_loss=entry + self.stop_points,
                                take_profit=entry - self.target_points,
                                confidence=confidence,
                                reason=f"SHORT Trend: Pullback to -1std (${vwap.lower_1std:,.0f}) in downtrend{htf_str}",
                                vwap_band=vwap.lower_1std,
                                sr_zone=zone,
                                htf_confluence=has_htf
                            ))

        # Sort by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)

        return signals

    def _determine_bias(self, price: float, vwap: VWAPBands) -> str:
        """Determine market bias from price position relative to VWAP bands"""
        if price > vwap.upper_1std:
            return 'strong_bullish'
        elif price < vwap.lower_1std:
            return 'strong_bearish'
        elif vwap.lower_1std <= price <= vwap.vwap:
            return 'bullish_mean_reversion'
        elif vwap.vwap <= price <= vwap.upper_1std:
            return 'bearish_mean_reversion'
        else:
            return 'neutral'

    def _calculate_confluence(self, zone: EnhancedSRZone, bias: str, distance: float, htf_confluence: bool = False) -> float:
        """
        Calculate confluence score (0-100)

        Factors:
        - Zone strength
        - Distance to zone
        - Market bias alignment
        - HTF confluence (5m/15m confirmation)
        """
        # Base score from zone strength
        score = zone.strength * 0.5

        # Distance penalty (closer = better)
        distance_score = max(0, 30 - (distance / 10))
        score += distance_score

        # Bias bonus
        bias_bonus = 0
        if 'bullish' in bias and zone.zone_type == 'support':
            bias_bonus = 15
        elif 'bearish' in bias and zone.zone_type == 'resistance':
            bias_bonus = 15
        elif zone.zone_type == 'both':
            bias_bonus = 10

        score += bias_bonus

        # HTF confluence bonus (major boost for aligned higher timeframes)
        if htf_confluence:
            score += 20

        return min(100, score)
