"""
Enhanced Location Detector with 6 S/R detection methods and confluence scoring.

Methods:
1. Frequency-based (swing highs/lows)
2. Volume Profile (high volume nodes)
3. Liquidity Heatmap (stop clusters)
4. Fibonacci retracements
5. Psychological levels (round numbers)
6. Manual zones (human-marked)
"""

import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SRDetectionMethod(Enum):
    """S/R detection methods"""
    FREQUENCY = "frequency"
    VOLUME_PROFILE = "volume_profile"
    LIQUIDITY_HEATMAP = "liquidity"
    FIBONACCI = "fibonacci"
    PSYCHOLOGICAL = "psychological"
    MANUAL = "manual"


@dataclass
class SRZone:
    """Support/Resistance zone with metadata"""
    level: float
    zone_type: str  # 'support', 'resistance', 'both'
    strength: float  # 0-10 confidence score
    methods: List[SRDetectionMethod]
    upper_bound: float
    lower_bound: float

    # Historical tracking
    touches: int = 0
    bounces: int = 0
    breaks: int = 0
    last_test_time: int = 0

    # Method-specific data
    volume_at_level: float = 0.0
    liquidity_score: float = 0.0
    fib_ratio: Optional[float] = None

    # Human feedback
    manual_override: bool = False
    human_confidence: Optional[float] = None
    weight: float = 1.0


class LocationDetector:
    """Enhanced location detector with multiple detection methods"""

    def __init__(self, config, binance_client, feedback_system=None, klines_cache=None):
        self.config = config
        self.client = binance_client
        self.feedback_system = feedback_system
        self.zone_cache = {}  # Cache for performance
        self.klines_cache = klines_cache or {}  # Cached klines from backtest

    async def _get_klines(self, symbol: str, interval: str, limit: int):
        """Get klines from cache if available (backtest), otherwise fetch from API (live)"""
        # Check cache first (backtest mode)
        if symbol in self.klines_cache and interval in self.klines_cache[symbol]:
            cached = self.klines_cache[symbol][interval]
            # Return last N candles from cache
            return cached[-limit:] if len(cached) > limit else cached

        # Fallback to API (live mode)
        return await self.client.get_klines(symbol, interval, limit)

    async def get_all_locations(self, symbol: str, current_price: float) -> Dict:
        """
        Detect all S/R zones using 6 methods, then consolidate with confluence scoring.

        Returns dict with:
        - all_zones: List of consolidated zones
        - at_location: Boolean if price is at a zone
        - best_zone: The strongest zone near current price
        - location_score: Score for CLC engine (0-100)
        """

        # Check cache (S/R zones don't change every candle, cache for performance)
        import time
        cache_key = symbol
        current_time = time.time()

        if cache_key in self.zone_cache:
            cached_data, cached_time = self.zone_cache[cache_key]
            # Cache S/R zones for 5 minutes (zones don't change much in 5min)
            if current_time - cached_time < 300:  # 5 minutes = 300 seconds
                # Still use cached zones, just update proximity check for current price
                cached_zones = cached_data['consolidated_zones']
                at_location, best_zone, location_score = self._check_at_location(
                    cached_zones, current_price
                )

                # Use cached MTF zones (no need to recalculate)
                mtf_zones = cached_data.get('mtf_zones', {'5m': [], '15m': []})

                return {
                    'all_zones': cached_zones,
                    'at_location': at_location,
                    'best_zone': best_zone,
                    'location_score': location_score,
                    'vwap_15m': cached_data.get('vwap_15m'),
                    'ema_levels': cached_data.get('ema_levels', {}),
                    'sr_zones': cached_zones,
                    'mtf_sr_zones': mtf_zones
                }

        all_zones = []

        # Method 1: Frequency-based (swing highs/lows)
        logger.info(f"[LOCATION] Starting Method 1: Frequency-based detection for {symbol}")
        freq_zones = await self._detect_frequency_based(symbol)
        logger.info(f"[LOCATION] Method 1 complete: {len(freq_zones)} frequency zones detected")
        all_zones.extend(freq_zones)

        # Method 2: Volume Profile (high volume nodes)
        logger.info(f"[LOCATION] Starting Method 2: Volume Profile detection for {symbol}")
        volume_zones = await self._detect_volume_profile(symbol)
        logger.info(f"[LOCATION] Method 2 complete: {len(volume_zones)} volume zones detected")
        all_zones.extend(volume_zones)

        # Method 3: Liquidity Heatmap (stop clusters)
        logger.info(f"[LOCATION] Starting Method 3: Liquidity Heatmap detection for {symbol}")
        liquidity_zones = await self._detect_liquidity_levels(symbol, current_price)
        logger.info(f"[LOCATION] Method 3 complete: {len(liquidity_zones)} liquidity zones detected")
        all_zones.extend(liquidity_zones)

        # Method 4: Fibonacci retracements
        logger.info(f"[LOCATION] Starting Method 4: Fibonacci detection for {symbol}")
        fib_zones = await self._detect_fibonacci_levels(symbol, current_price)
        logger.info(f"[LOCATION] Method 4 complete: {len(fib_zones)} fibonacci zones detected")
        all_zones.extend(fib_zones)

        # Method 5: Psychological levels (round numbers)
        logger.info(f"[LOCATION] Starting Method 5: Psychological levels detection for {symbol}")
        psych_zones = self._detect_psychological_levels(symbol, current_price)
        logger.info(f"[LOCATION] Method 5 complete: {len(psych_zones)} psychological zones detected")
        all_zones.extend(psych_zones)

        # Method 6: Manual zones (human-marked)
        logger.info(f"[LOCATION] Starting Method 6: Manual zones detection for {symbol}")
        manual_zones = self._get_manual_zones(symbol, current_price)
        logger.info(f"[LOCATION] Method 6 complete: {len(manual_zones)} manual zones detected")
        all_zones.extend(manual_zones)

        # Consolidate overlapping zones
        logger.info(f"[LOCATION] Starting zone consolidation for {symbol}")
        consolidated = self._consolidate_zones(all_zones, current_price)
        logger.info(f"[LOCATION] Zone consolidation complete: {len(consolidated)} consolidated zones")

        # Score by confluence (how many methods detected it)
        logger.info(f"[LOCATION] Starting confluence scoring for {symbol}")
        scored_zones = self._score_zones_by_confluence(consolidated)
        logger.info(f"[LOCATION] Confluence scoring complete")

        # Apply human feedback weights
        logger.info(f"[LOCATION] Applying human feedback weights for {symbol}")
        final_zones = self._apply_human_feedback_weights(scored_zones, symbol)
        logger.info(f"[LOCATION] Human feedback weights applied")

        # Check if current price is at a zone
        logger.info(f"[LOCATION] Checking if price ${current_price:.2f} is at a zone")
        at_location, best_zone, location_score = self._check_at_location(
            final_zones, current_price
        )
        logger.info(f"[LOCATION] Location check complete: at_location={at_location}, score={location_score:.1f}")

        # Also get VWAP and EMA levels for additional context
        logger.info(f"[LOCATION] Fetching 15m klines for VWAP/EMA calculation")
        klines = await self._get_klines(symbol, '15m', 200)
        logger.info(f"[LOCATION] Calculating VWAP and EMA levels")
        vwap_data = self._calculate_vwap_levels(klines) if klines else {}
        ema_data = self._calculate_ema_levels(klines) if klines else {}
        logger.info(f"[LOCATION] VWAP/EMA calculation complete")

        # Get multi-timeframe S/R zones (5min and 15min)
        logger.info(f"[LOCATION] Detecting multi-timeframe S/R zones for {symbol}")
        mtf_zones = await self._detect_mtf_sr_zones(symbol, current_price)
        logger.info(f"[LOCATION] Multi-timeframe S/R detection complete")

        result = {
            'all_zones': final_zones,
            'at_location': at_location,
            'best_zone': best_zone,
            'location_score': location_score,
            'vwap_15m': vwap_data.get('vwap'),
            'vwap_bands': vwap_data.get('bands'),
            'emas_15m': ema_data,
            'sr_zones': final_zones,  # For backward compatibility
            'mtf_sr_zones': mtf_zones  # 5min and 15min S/R zones for mean reversion
        }

        # Cache the results (zones are expensive to compute, cache for 5 minutes)
        cache_data = {
            'consolidated_zones': final_zones,
            'vwap_15m': vwap_data.get('vwap'),
            'ema_levels': ema_data,
            'mtf_zones': mtf_zones  # Cache MTF zones to avoid expensive recalculation
        }
        self.zone_cache[cache_key] = (cache_data, current_time)

        return result

    async def _detect_frequency_based(self, symbol: str) -> List[SRZone]:
        """Method 1: Detect S/R from swing highs/lows"""

        klines = await self._get_klines(symbol, '15m', 500)
        if not klines:
            return []

        df = self._klines_to_df(klines)
        zones = []
        window = 20

        # Find local highs (resistance)
        for i in range(window, len(df) - window):
            if df['high'].iloc[i] == max(df['high'].iloc[i-window:i+window]):
                level = float(df['high'].iloc[i])
                zones.append(SRZone(
                    level=level,
                    zone_type='resistance',
                    strength=3.0,
                    methods=[SRDetectionMethod.FREQUENCY],
                    upper_bound=level * 1.001,
                    lower_bound=level * 0.999,
                    touches=1
                ))

        # Find local lows (support)
        for i in range(window, len(df) - window):
            if df['low'].iloc[i] == min(df['low'].iloc[i-window:i+window]):
                level = float(df['low'].iloc[i])
                zones.append(SRZone(
                    level=level,
                    zone_type='support',
                    strength=3.0,
                    methods=[SRDetectionMethod.FREQUENCY],
                    upper_bound=level * 1.001,
                    lower_bound=level * 0.999,
                    touches=1
                ))

        return zones

    async def _detect_volume_profile(self, symbol: str) -> List[SRZone]:
        """Method 2: Detect S/R from volume profile (POC, high volume nodes)"""

        klines = await self._get_klines(symbol, '15m', 200)
        if not klines:
            return []

        df = self._klines_to_df(klines)

        # Build volume profile
        price_volume_map = {}
        bucket_size = 100 if symbol == "BTCUSDT" else 10

        for idx, row in df.iterrows():
            high = row['high']
            low = row['low']
            volume = row['volume']

            # Distribute volume across price range
            price_range = high - low
            if price_range == 0:
                continue

            num_buckets = int(price_range / bucket_size) + 1
            volume_per_bucket = volume / max(num_buckets, 1)

            for i in range(num_buckets):
                price = low + (i * bucket_size)
                bucket = round(price / bucket_size) * bucket_size
                price_volume_map[bucket] = price_volume_map.get(bucket, 0) + volume_per_bucket

        # Find top 5 volume nodes
        if not price_volume_map:
            return []

        sorted_nodes = sorted(price_volume_map.items(), key=lambda x: x[1], reverse=True)
        top_nodes = sorted_nodes[:5]

        zones = []
        for level, volume in top_nodes:
            zones.append(SRZone(
                level=level,
                zone_type='both',  # High volume = both S/R
                strength=5.0,
                methods=[SRDetectionMethod.VOLUME_PROFILE],
                upper_bound=level + bucket_size,
                lower_bound=level - bucket_size,
                volume_at_level=volume
            ))

        return zones

    async def _detect_liquidity_levels(self, symbol: str, current_price: float) -> List[SRZone]:
        """Method 3: Detect where stop-loss clusters likely are (liquidity pools)"""

        klines = await self._get_klines(symbol, '15m', 100)
        if not klines:
            return []

        df = self._klines_to_df(klines)
        zones = []
        window = 10

        # Stops typically cluster above swing highs and below swing lows
        stop_offset = 50 if symbol == "BTCUSDT" else 5

        # Find swing highs → stops above
        for i in range(window, len(df) - window):
            if df['high'].iloc[i] == max(df['high'].iloc[i-window:i+window]):
                swing_high = float(df['high'].iloc[i])
                stop_cluster = swing_high + stop_offset

                # Only include if near current price (within 2%)
                if abs(stop_cluster - current_price) / current_price <= 0.02:
                    zones.append(SRZone(
                        level=stop_cluster,
                        zone_type='resistance',
                        strength=4.0,
                        methods=[SRDetectionMethod.LIQUIDITY_HEATMAP],
                        upper_bound=stop_cluster + stop_offset/2,
                        lower_bound=stop_cluster - stop_offset/2,
                        liquidity_score=7.0
                    ))

        # Find swing lows → stops below
        for i in range(window, len(df) - window):
            if df['low'].iloc[i] == min(df['low'].iloc[i-window:i+window]):
                swing_low = float(df['low'].iloc[i])
                stop_cluster = swing_low - stop_offset

                if abs(stop_cluster - current_price) / current_price <= 0.02:
                    zones.append(SRZone(
                        level=stop_cluster,
                        zone_type='support',
                        strength=4.0,
                        methods=[SRDetectionMethod.LIQUIDITY_HEATMAP],
                        upper_bound=stop_cluster + stop_offset/2,
                        lower_bound=stop_cluster - stop_offset/2,
                        liquidity_score=7.0
                    ))

        return zones

    async def _detect_fibonacci_levels(self, symbol: str, current_price: float) -> List[SRZone]:
        """Method 4: Calculate Fibonacci retracement levels from recent swing"""

        klines = await self._get_klines(symbol, '1h', 100)
        if not klines:
            return []

        df = self._klines_to_df(klines)

        # Find recent significant swing (last 50 candles)
        recent_df = df.tail(50)
        swing_high = float(recent_df['high'].max())
        swing_low = float(recent_df['low'].min())
        fib_range = swing_high - swing_low

        if fib_range == 0:
            return []

        # Determine trend direction
        if current_price > (swing_high + swing_low) / 2:
            # Uptrend: retracement levels are support
            base = swing_low
            zone_type = 'support'
        else:
            # Downtrend: retracement levels are resistance
            base = swing_high
            zone_type = 'resistance'

        # Fibonacci ratios and their strengths
        fib_levels = {
            0.236: 3.0,
            0.382: 5.0,
            0.500: 6.0,  # Also psychological 50%
            0.618: 7.0,  # Golden ratio (strongest)
            0.786: 4.0
        }

        zones = []
        for ratio, strength in fib_levels.items():
            if zone_type == 'support':
                level = base + (fib_range * ratio)
            else:
                level = base - (fib_range * ratio)

            # Only include levels near current price (within 2%)
            if abs(level - current_price) / current_price <= 0.02:
                zones.append(SRZone(
                    level=level,
                    zone_type=zone_type,
                    strength=strength,
                    methods=[SRDetectionMethod.FIBONACCI],
                    upper_bound=level * 1.002,
                    lower_bound=level * 0.998,
                    fib_ratio=ratio
                ))

        return zones

    def _detect_psychological_levels(self, symbol: str, current_price: float) -> List[SRZone]:
        """Method 5: Detect psychological levels (round numbers)"""

        zones = []

        if symbol == "BTCUSDT":
            round_to = 1000  # Round to thousands
            half_step = 500
        elif symbol == "ETHUSDT":
            round_to = 100   # Round to hundreds
            half_step = 50
        else:
            round_to = 100
            half_step = 50

        # Find base level
        base = round(current_price / round_to) * round_to

        # Check levels above and below
        for offset in [-2, -1, 0, 1, 2]:
            level = base + (offset * round_to)

            # Only include if within 1.5% of current price
            distance_pct = abs(level - current_price) / current_price
            if distance_pct <= 0.015:
                zones.append(SRZone(
                    level=level,
                    zone_type='both',
                    strength=8.0 if offset == 0 else 6.0,  # Current round number is strongest
                    methods=[SRDetectionMethod.PSYCHOLOGICAL],
                    upper_bound=level + round_to * 0.005,
                    lower_bound=level - round_to * 0.005
                ))

            # Add half-levels (e.g., $50,500 for BTC)
            half_level = level + half_step
            half_distance_pct = abs(half_level - current_price) / current_price

            if half_distance_pct <= 0.015:
                zones.append(SRZone(
                    level=half_level,
                    zone_type='both',
                    strength=5.0,
                    methods=[SRDetectionMethod.PSYCHOLOGICAL],
                    upper_bound=half_level + half_step * 0.01,
                    lower_bound=half_level - half_step * 0.01
                ))

        return zones

    def _get_manual_zones(self, symbol: str, current_price: float) -> List[SRZone]:
        """Method 6: Get human-marked zones from feedback system"""

        if not self.feedback_system:
            return []

        zones = []

        for zone_id, zone_data in self.feedback_system.manual_zones.items():
            if zone_data.symbol != symbol:
                continue

            # Only include zones within 3% of current price
            distance_pct = abs(zone_data.price_level - current_price) / current_price
            if distance_pct > 0.03:
                continue

            # Human zones start with high strength and adjust based on performance
            base_strength = zone_data.confidence * 2  # 5 stars = 10.0 strength
            adjusted_strength = base_strength * zone_data.adjusted_weight

            zones.append(SRZone(
                level=zone_data.price_level,
                zone_type=zone_data.zone_type,
                strength=min(10.0, adjusted_strength),
                methods=[SRDetectionMethod.MANUAL],
                upper_bound=zone_data.upper_bound,
                lower_bound=zone_data.lower_bound,
                touches=zone_data.hits,
                bounces=zone_data.successful_bounces,
                breaks=zone_data.false_breaks,
                manual_override=True,
                human_confidence=zone_data.confidence,
                weight=zone_data.adjusted_weight
            ))

        return zones

    def _consolidate_zones(self, all_zones: List[SRZone], current_price: float) -> List[SRZone]:
        """Merge overlapping zones detected by multiple methods"""

        if not all_zones:
            return []

        consolidated = []
        used_indices = set()

        for i, zone1 in enumerate(all_zones):
            if i in used_indices:
                continue

            # Find all zones within 0.3% of this one
            cluster = [zone1]
            used_indices.add(i)

            for j, zone2 in enumerate(all_zones):
                if j in used_indices or i == j:
                    continue

                distance_pct = abs(zone1.level - zone2.level) / zone1.level

                if distance_pct <= 0.003:  # Within 0.3%
                    cluster.append(zone2)
                    used_indices.add(j)

            # Merge cluster into single zone
            if cluster:
                # Average level
                avg_level = sum(z.level for z in cluster) / len(cluster)

                # Combine methods
                all_methods = []
                for z in cluster:
                    all_methods.extend(z.methods)
                unique_methods = list(set(all_methods))

                # Strongest base strength
                base_strength = max(z.strength for z in cluster)

                # Combine zone type
                types = [z.zone_type for z in cluster]
                if 'both' in types:
                    zone_type = 'both'
                elif 'support' in types and 'resistance' in types:
                    zone_type = 'both'
                else:
                    zone_type = cluster[0].zone_type

                # Combine bounds
                upper = max(z.upper_bound for z in cluster)
                lower = min(z.lower_bound for z in cluster)

                # Combine metadata
                total_touches = sum(z.touches for z in cluster)
                total_bounces = sum(z.bounces for z in cluster)
                total_breaks = sum(z.breaks for z in cluster)
                total_volume = sum(z.volume_at_level for z in cluster)
                max_liquidity = max((z.liquidity_score for z in cluster), default=0.0)

                # Manual override check
                manual = any(z.manual_override for z in cluster)
                human_conf = max((z.human_confidence for z in cluster if z.human_confidence), default=None)

                merged_zone = SRZone(
                    level=avg_level,
                    zone_type=zone_type,
                    strength=base_strength,  # Will be adjusted in scoring
                    methods=unique_methods,
                    upper_bound=upper,
                    lower_bound=lower,
                    touches=total_touches,
                    bounces=total_bounces,
                    breaks=total_breaks,
                    volume_at_level=total_volume,
                    liquidity_score=max_liquidity,
                    manual_override=manual,
                    human_confidence=human_conf
                )

                consolidated.append(merged_zone)

        return consolidated

    def _score_zones_by_confluence(self, zones: List[SRZone]) -> List[SRZone]:
        """Increase strength score based on confluence (multiple detection methods)"""

        for zone in zones:
            num_methods = len(zone.methods)

            # Confluence bonuses
            if num_methods >= 4:
                zone.strength = min(10.0, zone.strength * 1.5)  # 4+ methods = 50% bonus
            elif num_methods >= 3:
                zone.strength = min(10.0, zone.strength * 1.3)  # 3 methods = 30% bonus
            elif num_methods >= 2:
                zone.strength = min(10.0, zone.strength * 1.15)  # 2 methods = 15% bonus

            # Historical performance bonus
            if zone.touches > 0:
                success_rate = zone.bounces / zone.touches
                if success_rate > 0.7:  # 70%+ success rate
                    zone.strength = min(10.0, zone.strength * 1.2)
                elif success_rate < 0.3:  # Weak zone
                    zone.strength *= 0.8

            # Manual override priority
            if zone.manual_override:
                zone.strength = min(10.0, zone.strength * 1.5)  # Human marks get 50% boost

            # Human confidence adjustment
            if zone.human_confidence:
                # 5 stars = 1.3×, 3 stars = 1.0×, 1 star = 0.7×
                confidence_multiplier = 0.7 + (zone.human_confidence - 1) * 0.15
                zone.strength *= confidence_multiplier

        return zones

    def _apply_human_feedback_weights(self, zones: List[SRZone], symbol: str) -> List[SRZone]:
        """Adjust zone strengths based on human feedback learning"""

        if not self.feedback_system or not self.feedback_system.learning_enabled:
            return zones

        # Get learned adjustments from feedback system
        adjustments = self.feedback_system.get_sr_zone_adjustments(symbol)

        for zone in zones:
            # Check if this zone has learned adjustments
            for adj in adjustments:
                if abs(zone.level - adj['level']) / zone.level < 0.005:  # Same zone
                    zone.strength *= adj['multiplier']
                    zone.strength = min(10.0, zone.strength)
                    break

        return zones

    def _check_at_location(
        self,
        zones: List[SRZone],
        current_price: float
    ) -> tuple[bool, Optional[SRZone], float]:
        """Check if current price is at a zone and calculate location score"""

        max_distance_pct = getattr(self.config.clc_strategy.location, 'max_distance_from_level_pct', 0.005)

        at_location = False
        best_zone = None
        location_score = 0

        # Sort zones by strength
        sorted_zones = sorted(zones, key=lambda z: z.strength, reverse=True)

        for zone in sorted_zones:
            distance_pct = abs(current_price - zone.level) / current_price

            if distance_pct <= max_distance_pct:  # Within threshold
                at_location = True
                best_zone = zone

                # Score based on zone strength (max 40 points)
                location_score = 40 * (zone.strength / 10.0)

                logger.debug(f"[LOCATION] At zone: ${zone.level:.2f} ({zone.zone_type}), "
                            f"strength {zone.strength:.1f}/10, methods: {[m.value for m in zone.methods]}")
                break

        return at_location, best_zone, location_score

    async def _detect_mtf_sr_zones(self, symbol: str, current_price: float) -> Dict:
        """Detect S/R zones on 5min and 15min timeframes for mean reversion entries"""

        mtf_zones = {
            '5m': [],
            '15m': []
        }

        if not self.config.clc_strategy.location.use_5min_sr and not self.config.clc_strategy.location.use_15min_sr:
            return mtf_zones

        lookback = self.config.clc_strategy.location.mtf_sr_lookback
        min_touches = self.config.clc_strategy.location.mtf_sr_min_touches

        # Detect 5min S/R zones
        if self.config.clc_strategy.location.use_5min_sr:
            klines_5m = await self._get_klines(symbol, '5m', lookback)
            if klines_5m:
                zones_5m = self._detect_sr_from_klines(klines_5m, min_touches, timeframe='5m')
                mtf_zones['5m'] = zones_5m

        # Detect 15min S/R zones
        if self.config.clc_strategy.location.use_15min_sr:
            klines_15m = await self._get_klines(symbol, '15m', lookback)
            if klines_15m:
                zones_15m = self._detect_sr_from_klines(klines_15m, min_touches, timeframe='15m')
                mtf_zones['15m'] = zones_15m

        return mtf_zones

    def _detect_sr_from_klines(self, klines, min_touches: int, timeframe: str) -> List[SRZone]:
        """Detect S/R zones from kline data (swing highs/lows with min touches)"""

        df = self._klines_to_df(klines)
        zones = []
        window = 10  # Smaller window for faster timeframes

        # Track touches for each level
        level_touches = {}

        # Find swing highs (resistance)
        for i in range(window, len(df) - window):
            if df['high'].iloc[i] == max(df['high'].iloc[i-window:i+window+1]):
                level = float(df['high'].iloc[i])
                level_key = round(level / 10) * 10  # Cluster nearby levels

                if level_key not in level_touches:
                    level_touches[level_key] = {'resistance': 0, 'support': 0, 'prices': []}

                level_touches[level_key]['resistance'] += 1
                level_touches[level_key]['prices'].append(level)

        # Find swing lows (support)
        for i in range(window, len(df) - window):
            if df['low'].iloc[i] == min(df['low'].iloc[i-window:i+window+1]):
                level = float(df['low'].iloc[i])
                level_key = round(level / 10) * 10

                if level_key not in level_touches:
                    level_touches[level_key] = {'resistance': 0, 'support': 0, 'prices': []}

                level_touches[level_key]['support'] += 1
                level_touches[level_key]['prices'].append(level)

        # Create zones from levels with min touches
        for level_key, data in level_touches.items():
            total_touches = data['resistance'] + data['support']

            if total_touches >= min_touches:
                avg_level = sum(data['prices']) / len(data['prices'])

                # Determine zone type
                if data['resistance'] > data['support']:
                    zone_type = 'resistance'
                elif data['support'] > data['resistance']:
                    zone_type = 'support'
                else:
                    zone_type = 'both'

                zones.append(SRZone(
                    level=avg_level,
                    zone_type=zone_type,
                    strength=min(total_touches, 10),  # Cap at 10
                    methods=[SRDetectionMethod.FREQUENCY],
                    upper_bound=avg_level * 1.002,
                    lower_bound=avg_level * 0.998,
                    touches=total_touches
                ))

        return zones

    def _calculate_vwap_levels(self, klines) -> Dict:
        """Calculate VWAP and bands for additional context"""

        df = self._klines_to_df(klines)
        tp = (df['high'] + df['low'] + df['close']) / 3
        vwap = float((tp * df['volume']).sum() / df['volume'].sum())
        vwap_std = float(tp.std())

        return {
            'vwap': vwap,
            'bands': {
                'upper_1std': vwap + vwap_std,
                'lower_1std': vwap - vwap_std,
                'upper_2std': vwap + 2 * vwap_std,
                'lower_2std': vwap - 2 * vwap_std
            }
        }

    def _calculate_ema_levels(self, klines) -> Dict:
        """Calculate EMA levels for additional context"""

        df = self._klines_to_df(klines)

        return {
            20: float(df['close'].ewm(span=20).mean().iloc[-1]),
            50: float(df['close'].ewm(span=50).mean().iloc[-1]),
            200: float(df['close'].ewm(span=200).mean().iloc[-1]) if len(df) >= 200 else None
        }

    def _klines_to_df(self, klines):
        """Convert klines to pandas DataFrame"""
        df = pd.DataFrame(
            klines,
            columns=['open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'qav', 'num_trades', 'tb_base', 'tb_quote', 'ignore']
        )
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
