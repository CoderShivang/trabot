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

        # Determine zone type based on position relative to CURRENT price
        # THIS IS CRITICAL: Zones BELOW price = support, zones ABOVE price = resistance
        # The consolidation created a zone - now determine what role it plays
        # We'll determine this dynamically when checking signals based on current price position
        # For now, mark as 'both' and let signal generation decide based on price position
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
        self._last_regime = None  # Track regime changes

    def _calculate_market_regime(self, df_1d: pd.DataFrame, current_price: float) -> str:
        """
        Calculate market regime based on 100 Day SMA

        User requirement: Price must be 1200-1500+ above/below 100 SMA for regime bias

        Returns: 'bullish_regime', 'bearish_regime', or 'neutral_regime'
        """
        if df_1d is None or len(df_1d) < 100:
            return 'neutral_regime'

        # Calculate 100 day SMA
        sma_100 = df_1d['close'].iloc[-100:].mean()

        # Calculate distance from SMA
        distance = current_price - sma_100
        abs_distance = abs(distance)

        # User requirement: 1200-1500+ distance for regime classification
        if distance > 1200:
            regime = 'bullish_regime'
            logger.info(f"[REGIME-100SMA] BULLISH - Price ${current_price:,.0f} is ${distance:,.0f} above 100 SMA (${sma_100:,.0f})")
        elif distance < -1200:
            regime = 'bearish_regime'
            logger.info(f"[REGIME-100SMA] BEARISH - Price ${current_price:,.0f} is ${abs_distance:,.0f} below 100 SMA (${sma_100:,.0f})")
        else:
            regime = 'neutral_regime'
            if self._analyze_count % 100 == 0:  # Log occasionally
                logger.debug(f"[REGIME-100SMA] NEUTRAL - Price ${current_price:,.0f} is ${abs_distance:,.0f} from 100 SMA (${sma_100:,.0f})")

        return regime

    def _detect_market_regime(self, df: pd.DataFrame, current_price: float) -> str:
        """
        Detect if market is range-bound or trending (SHORT TERM)

        Returns: 'ranging', 'trending_up', or 'trending_down'
        """
        # Use recent 60 bars (1 hour for 1m chart)
        recent = df.tail(60)

        if len(recent) < 30:
            return 'ranging'  # Default to ranging if insufficient data

        # Calculate high/low range
        period_high = recent['high'].max()
        period_low = recent['low'].min()
        range_pct = (period_high - period_low) / period_low

        # Calculate trend using linear regression on closes
        closes = recent['close'].values
        x = np.arange(len(closes))
        slope = np.polyfit(x, closes, 1)[0]
        slope_pct = (slope * len(closes)) / closes[0]

        # Calculate average candle size (volatility indicator)
        candle_ranges = (recent['high'] - recent['low']) / recent['close']
        avg_candle_pct = candle_ranges.mean()

        # Ranging: tight range (<2.5%) AND minimal slope (<1.5%) AND small candles
        # This identifies consolidation periods like 13 Nov 0:45 to 5:45
        if range_pct < 0.025 and abs(slope_pct) < 0.015 and avg_candle_pct < 0.008:
            return 'ranging'

        # Trending: significant slope (>2%) AND wider range (>3%)
        elif slope_pct > 0.02 and range_pct > 0.03:
            return 'trending_up'
        elif slope_pct < -0.02 and range_pct > 0.03:
            return 'trending_down'

        # Default to ranging if unclear
        else:
            return 'ranging'

    def analyze(self, df: pd.DataFrame, current_price: float,
                df_5m: Optional[pd.DataFrame] = None,
                df_15m: Optional[pd.DataFrame] = None,
                df_1d: Optional[pd.DataFrame] = None) -> List[TradeSignal]:
        """
        Analyze market and find trade setups with multi-timeframe confluence

        Args:
            df: 1m OHLCV DataFrame with recent candles
            current_price: Current market price
            df_5m: Optional 5m OHLCV DataFrame for HTF zones
            df_15m: Optional 15m OHLCV DataFrame for HTF zones
            df_1d: Optional daily OHLCV DataFrame for 100 SMA and daily S/R zones

        Returns:
            List of TradeSignal objects (sorted by confidence)
        """
        if len(df) < 50:
            logger.warning("[VWAP] Insufficient data for analysis")
            return []

        # Calculate market regime based on 100 Day SMA
        market_regime = self._calculate_market_regime(df_1d, current_price) if df_1d is not None and len(df_1d) >= 100 else 'neutral'

        # Detect market regime (ranging vs trending)
        regime = self._detect_market_regime(df, current_price)

        # Log regime changes
        if regime != self._last_regime and self._last_regime is not None:
            logger.info(f"[REGIME] Market switched from {self._last_regime} to {regime}")
        elif self._analyze_count == 0:
            logger.info(f"[REGIME] Market is {regime}")
        self._last_regime = regime

        # Update S/R zones for all timeframes including daily
        self.sr_detector.update_zones(df, timeframe='1m', lookback=200)

        if df_5m is not None and len(df_5m) >= 50:
            self.sr_detector.update_zones(df_5m, timeframe='5m', lookback=100)

        if df_15m is not None and len(df_15m) >= 50:
            self.sr_detector.update_zones(df_15m, timeframe='15m', lookback=100)

        if df_1d is not None and len(df_1d) >= 30:
            # Detect daily S/R zones for range identification
            self.sr_detector.update_zones(df_1d, timeframe='1d', lookback=60)

        # Get zones near current price (only active, not invalidated)
        zones_near_price = self.sr_detector.get_zones_near_price(
            current_price,
            timeframes=['1m', '1d'],
            proximity=self.zone_proximity
        )

        # Filter by strength
        strong_zones = [z for z in zones_near_price.get('1m', [])
                       if z.strength >= self.min_zone_strength and not z.invalidated]

        # Get daily zones for counter-trend trade allowance
        daily_zones = [z for z in zones_near_price.get('1d', [])
                      if z.strength >= self.min_zone_strength and not z.invalidated]
        has_daily_sr = len(daily_zones) > 0

        # Debug logging - only log when strong zones exist (reduces spam)
        if strong_zones:
            all_1m_zones = self.sr_detector.zones_by_tf.get('1m', [])
            logger.info(f"[ZONES] Found {len(strong_zones)} strong zones near price")
            for zone in strong_zones[:2]:  # Log first 2
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
        # Market regime filter: In bearish regime, only allow if near daily S/R or high confidence
        long_eligible_zones = strong_zones.copy()
        if market_regime == 'bearish_regime':
            # In bearish regime, be more selective with longs
            if not has_daily_sr:
                # Only high confidence zones (2+ touches) allowed
                long_eligible_zones = [z for z in strong_zones if z.touches >= 2]
                if len(long_eligible_zones) == 0:
                    logger.debug(f"[REGIME-FILTER] Skipping LONGs - bearish regime without daily S/R or high confidence zones")

        if bias in ['bullish_mean_reversion', 'neutral'] and len(long_eligible_zones) > 0:
            dist_to_lower = vwap.distance_to_band(current_price, 'lower_1std')

            if dist_to_lower <= self.band_proximity:
                support_zones = [z for z in long_eligible_zones if z.zone_type in ['support', 'both']]
                if len(support_zones) > 0:
                    logger.info(f"[CHECK-LONG-MR] Found {len(support_zones)} support zones near -1s band (dist:{dist_to_lower:.0f} <= {self.band_proximity})")
            else:
                if len(long_eligible_zones) > 0:
                    logger.info(f"[SKIP-LONG-MR] Distance to -1s band too far: {dist_to_lower:.0f} > {self.band_proximity}")

            if dist_to_lower <= self.band_proximity:

                for zone in long_eligible_zones:
                    # CRITICAL: Check zone position relative to CURRENT price dynamically
                    # For LONG: zone must be BELOW price (acting as support)
                    # Don't rely solely on historical zone_type classification
                    is_support_now = zone.level < current_price or abs(zone.level - current_price) / current_price < 0.002

                    if (zone.zone_type in ['support', 'both'] or is_support_now) and zone.is_near(current_price, self.zone_proximity):
                        # Additional safety: verify zone is below or at current price
                        if zone.level > current_price + 50:
                            logger.debug(f"[SAFETY] Skipping LONG - zone ${zone.level:,.0f} is above price ${current_price:,.0f}")
                            continue

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

                        # Boost confidence for zones with liquidity grabs (fake breakouts = reversals)
                        if zone.liquidity_grabs > 0:
                            confidence += min(15, zone.liquidity_grabs * 5)  # +5 per liquidity grab, max +15

                        # Reduce confidence for zones that broke recently
                        if zone.last_interaction == 'breakout' and zone.breakouts >= 2:
                            confidence -= 20  # Penalize broken zones

                        if confidence >= 50:  # Lowered from 65 for initial testing
                            entry = max(zone.level - 30, current_price - 50)

                            htf_str = " + HTF" if has_htf else ""
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

        # 2. Trend Continuation Long: Price firmly beyond +1σ (strong uptrend)
        # NEW LOGIC: Trigger when price IS beyond 1σ, not waiting for pullback
        # Skip in ranging markets (prioritize S/R mean reversion)
        if current_price > vwap.upper_1std and regime != 'ranging' and market_regime != 'bearish_regime':
            # Price is beyond upper band - strong uptrend
            distance_beyond = current_price - vwap.upper_1std

            # Only enter if significantly beyond (not just touching)
            if distance_beyond >= 50:  # At least $50 beyond the band
                # Calculate confidence based on trend strength
                trend_confidence = min(95, 60 + (distance_beyond / 100))  # 60-95 based on distance

                # Check if market regime supports this (boost confidence in bullish regime)
                if market_regime == 'bullish_regime':
                    trend_confidence += 10

                # Enter at current price or slightly below for limit order
                entry = current_price - 20

                signals.append(TradeSignal(
                    direction='LONG',
                    signal_type='trend_continuation',
                    entry_price=entry,
                    stop_loss=max(entry - self.stop_points, vwap.upper_1std - 50),  # SL below band
                    take_profit=entry + self.target_points,
                    confidence=trend_confidence,
                    reason=f"LONG Trend: Price ${current_price:,.0f} firmly beyond +1std (${vwap.upper_1std:,.0f}) by ${distance_beyond:,.0f}",
                    vwap_band=vwap.upper_1std,
                    sr_zone=None,  # No S/R zone required for trend continuation
                    htf_confluence=market_regime == 'bullish_regime'
                ))

        # === SHORT SETUPS ===

        # 3. Mean Reversion Short: +1σ + Resistance
        # Market regime filter: In bullish regime, only allow if near daily S/R or high confidence
        short_eligible_zones = strong_zones.copy()
        if market_regime == 'bullish_regime':
            # In bullish regime, be more selective with shorts
            if not has_daily_sr:
                # Only high confidence zones (2+ touches) allowed
                short_eligible_zones = [z for z in strong_zones if z.touches >= 2]
                if len(short_eligible_zones) == 0:
                    logger.debug(f"[REGIME-FILTER] Skipping SHORTs - bullish regime without daily S/R or high confidence zones")

        if bias in ['bearish_mean_reversion', 'neutral'] and len(short_eligible_zones) > 0:
            dist_to_upper = vwap.distance_to_band(current_price, 'upper_1std')

            if dist_to_upper <= self.band_proximity:
                for zone in short_eligible_zones:
                    # CRITICAL: Check zone position relative to CURRENT price dynamically
                    # For SHORT: zone must be ABOVE price (acting as resistance)
                    # Don't rely solely on historical zone_type classification
                    is_resistance_now = zone.level > current_price or abs(zone.level - current_price) / current_price < 0.002

                    if (zone.zone_type in ['resistance', 'both'] or is_resistance_now) and zone.is_near(current_price, self.zone_proximity):
                        # Additional safety: verify zone is above or at current price
                        if zone.level < current_price - 50:
                            logger.debug(f"[SAFETY] Skipping SHORT - zone ${zone.level:,.0f} is below price ${current_price:,.0f}")
                            continue

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

                        # Boost confidence for zones with liquidity grabs (fake breakouts = reversals)
                        if zone.liquidity_grabs > 0:
                            confidence += min(15, zone.liquidity_grabs * 5)  # +5 per liquidity grab, max +15

                        # Reduce confidence for zones that broke recently
                        if zone.last_interaction == 'breakout' and zone.breakouts >= 2:
                            confidence -= 20  # Penalize broken zones

                        if confidence >= 50:  # Lowered from 65 for initial testing
                            entry = min(zone.level + 30, current_price + 50)

                            htf_str = " + HTF" if has_htf else ""
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

        # 4. Trend Continuation Short: Price firmly beyond -1σ (strong downtrend)
        # NEW LOGIC: Trigger when price IS beyond 1σ, not waiting for pullback
        # Skip in ranging markets (prioritize S/R mean reversion)
        if current_price < vwap.lower_1std and regime != 'ranging' and market_regime != 'bullish_regime':
            # Price is beyond lower band - strong downtrend
            distance_beyond = vwap.lower_1std - current_price

            # Only enter if significantly beyond (not just touching)
            if distance_beyond >= 50:  # At least $50 beyond the band
                # Calculate confidence based on trend strength
                trend_confidence = min(95, 60 + (distance_beyond / 100))  # 60-95 based on distance

                # Check if market regime supports this (boost confidence in bearish regime)
                if market_regime == 'bearish_regime':
                    trend_confidence += 10

                # Enter at current price or slightly above for limit order
                entry = current_price + 20

                signals.append(TradeSignal(
                    direction='SHORT',
                    signal_type='trend_continuation',
                    entry_price=entry,
                    stop_loss=min(entry + self.stop_points, vwap.lower_1std + 50),  # SL above band
                    take_profit=entry - self.target_points,
                    confidence=trend_confidence,
                    reason=f"SHORT Trend: Price ${current_price:,.0f} firmly beyond -1std (${vwap.lower_1std:,.0f}) by ${distance_beyond:,.0f}",
                    vwap_band=vwap.lower_1std,
                    sr_zone=None,  # No S/R zone required for trend continuation
                    htf_confluence=market_regime == 'bearish_regime'
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
