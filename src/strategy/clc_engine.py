"""
CLC strategy engine - integrates context, location, confirmation, big orders and feedback adjustments.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ContextBias(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

class LocationType(Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"
    VWAP_BAND = "vwap_band"
    EMA_LEVEL = "ema_level"
    SR_ZONE = "sr_zone"

@dataclass
class CLCScore:
    total_score: float
    context_score: float
    location_score: float
    confirmation_score: float
    big_orders_score: float
    context_bias: ContextBias
    at_location: bool
    location_type: Optional[LocationType]
    confirmation_signals: List[str]
    big_orders_detected: List[str]
    reasons: List[str]
    warnings: List[str]

    def meets_entry_criteria(self, min_score: float, min_confirmation_signals: int = 2) -> bool:
        return (
            self.total_score >= min_score and
            self.at_location and
            len(self.confirmation_signals) >= min_confirmation_signals
        )

class CLCEngine:
    def __init__(self, config, context_analyzer, location_detector, confirmation_analyzer, big_orders_detector, feedback_system=None):
        self.config = config
        self.context_analyzer = context_analyzer
        self.location_detector = location_detector
        self.confirmation_analyzer = confirmation_analyzer
        self.big_orders_detector = big_orders_detector
        self.feedback_system = feedback_system

    async def evaluate_trade(self, symbol: str, direction: str, current_price: float, orderbook, recent_trades) -> CLCScore:
        # 1) context - adjusted for direction
        ctx = await self.context_analyzer.get_context(symbol, "1h", current_price)
        bias = ContextBias.NEUTRAL
        score_ctx = 0.0
        reasons = []
        bias_votes = 0

        # DEBUG: Log entry parameters
        logger.debug(f"[CLC] Evaluating {direction} @ price={current_price:.2f}, vwap={ctx.vwap:.2f}, ema50={ctx.ema50:.2f}, ema200={ctx.ema200:.2f}")
        logger.info(f"[REGIME] Market regime: {ctx.regime.upper()} (ADX={ctx.adx:.1f})")

        # NEW APPROACH: Calculate bullish and bearish signals, then score based on direction
        # This ensures LONG and SHORT never get the same scores in the same market conditions

        bullish_score = 0
        bearish_score = 0

        # Price vs VWAP
        if current_price > ctx.vwap:
            bullish_score += 25
            bias_votes += 1
            reasons.append("Price > VWAP (bullish)")
        else:
            bearish_score += 25
            bias_votes -= 1
            reasons.append("Price < VWAP (bearish)")

        # EMA trend
        if ctx.ema50 > ctx.ema200:
            bullish_score += 35
            bias_votes += 1
            reasons.append("EMA50 > EMA200 (bullish)")
        else:
            bearish_score += 35
            bias_votes -= 1
            reasons.append("EMA50 < EMA200 (bearish)")

        # ADAPTIVE SCORING BASED ON MARKET REGIME
        # Trending market: Use trend-following logic
        # Choppy/Ranging market: Use mean reversion logic

        if ctx.regime == "trending":
            # TREND-FOLLOWING MODE: Align with trend direction
            reasons.append(f"Regime: TRENDING (ADX={ctx.adx:.1f})")

            if direction == "LONG":
                score_ctx = bullish_score
                # Penalize counter-trend LONGs heavily
                if bearish_score > bullish_score:
                    score_ctx *= 0.3
                    reasons.append("LONG counter-trend penalty")
            else:  # SHORT
                score_ctx = bearish_score
                # Penalize counter-trend SHORTs heavily
                if bullish_score > bearish_score:
                    score_ctx *= 0.3
                    reasons.append("SHORT counter-trend penalty")

        elif ctx.regime in ["choppy", "ranging"]:
            # MEAN REVERSION MODE: Trade range boundaries
            reasons.append(f"Regime: {ctx.regime.upper()} - Mean reversion mode")

            # Check if price is near range boundaries
            near_range_high = False
            near_range_low = False

            if ctx.range_high > 0 and ctx.range_low > 0:
                range_size = ctx.range_high - ctx.range_low
                high_threshold = ctx.range_high - (range_size * 0.1)  # Within 10% of range high
                low_threshold = ctx.range_low + (range_size * 0.1)   # Within 10% of range low

                if current_price >= high_threshold:
                    near_range_high = True
                    reasons.append(f"Near range high: {ctx.range_high:.2f}")
                elif current_price <= low_threshold:
                    near_range_low = True
                    reasons.append(f"Near range low: {ctx.range_low:.2f}")

            # Mean reversion scoring: SHORT at range high, LONG at range low
            if direction == "SHORT" and near_range_high:
                score_ctx = 50.0  # High score for shorting at range high
                reasons.append("Mean reversion SHORT at range high")
            elif direction == "LONG" and near_range_low:
                score_ctx = 50.0  # High score for buying at range low
                reasons.append("Mean reversion LONG at range low")
            else:
                # Not at a range boundary - skip trade
                score_ctx = 0.0
                reasons.append(f"Skip: Not at range boundary ({direction} needs {'high' if direction == 'SHORT' else 'low'})")

        else:
            # Unknown regime - use default trending logic
            if direction == "LONG":
                score_ctx = bullish_score
            else:
                score_ctx = bearish_score

        logger.debug(f"[CLC] {direction}: bullish={bullish_score}, bearish={bearish_score}, final_ctx={score_ctx:.1f}")

        # Determine bias
        if bias_votes >= 2:
            bias = ContextBias.BULLISH
        elif bias_votes <= -2:
            bias = ContextBias.BEARISH

        # 2) location
        locations = await self.location_detector.get_all_locations(symbol, current_price)
        at_location = False; loc_type=None; score_loc=0.0; loc_reasons=[]
        sr_zones = locations.get('sr_zones', [])
        max_dist = getattr(self.config.clc_strategy.location, 'max_distance_from_level_pct', 0.005)

        # Check main S/R zones
        for z in sr_zones:
            # SRZone is a dataclass, access attributes not dict keys
            dist = abs(current_price - z.level)/current_price
            if dist <= max_dist:
                at_location = True
                score_loc += 40 * (z.strength / 10.0)  # Normalize strength (0-10) to weight (0-1)
                loc_type = LocationType.SR_ZONE
                loc_reasons.append(f"At SR {z.level:.2f}")
                break

        # Check 5min and 15min S/R zones (for mean reversion in choppy markets)
        mtf_zones = locations.get('mtf_sr_zones', {})

        # 5min S/R zones
        zones_5m = mtf_zones.get('5m', [])
        for z in zones_5m:
            dist = abs(current_price - z.level)/current_price
            if dist <= max_dist * 1.5:  # Slightly wider tolerance for faster timeframes
                at_location = True
                score_loc += 20 * (z.strength / 10.0)
                loc_reasons.append(f"At 5m SR {z.level:.2f}")
                break

        # 15min S/R zones
        zones_15m = mtf_zones.get('15m', [])
        for z in zones_15m:
            dist = abs(current_price - z.level)/current_price
            if dist <= max_dist * 1.2:
                at_location = True
                score_loc += 25 * (z.strength / 10.0)
                loc_reasons.append(f"At 15m SR {z.level:.2f}")
                break

        # VWAP bands
        vwap = locations.get('vwap_15m')
        if vwap:
            dist = abs(current_price - vwap)/current_price
            if dist <= max_dist:
                at_location = True
                score_loc += 15
                loc_type = LocationType.VWAP_BAND
                loc_reasons.append(f"At VWAP 15m: {vwap:.2f}")

        # 3) confirmation
        conf = self.confirmation_analyzer.analyze(symbol, orderbook, recent_trades)
        conf_score = 0.0; conf_signals=[]; conf_warnings=[]
        # use multiple signals: imbalance, delta, tape velocity, divergence, absorption
        if conf['imbalance'] >= getattr(self.config.clc_strategy.confirmation, 'imbalance_threshold', 0.7):
            conf_score += 25; conf_signals.append(f"imbalance:{conf['imbalance']:.2f}")
        if conf['delta'] >= getattr(self.config.clc_strategy.confirmation, 'delta_threshold', 0.6):
            conf_score += 25; conf_signals.append(f"delta:{conf['delta']:.2f}")
        if conf.get('tape_velocity',0) > 10:
            conf_score += 10; conf_signals.append("high_tape_velocity")
        if conf.get('divergence'):
            conf_score += 5; conf_warnings.append("delta/price divergence")
        if conf.get('absorption_detected'):
            conf_score += 25; conf_signals.append("absorption")

        # require at least 2 confirmation signals - handled in meets_entry_criteria

        # 4) big orders
        bo = self.big_orders_detector.analyze(symbol, orderbook, recent_trades)
        bo_score = 0.0; bo_detected=[]
        if bo.get('large_market_orders'):
            bo_score += 30
            for o in bo['large_market_orders'][:2]:
                bo_detected.append(f"market:{o.side}@{o.price}")
        if bo.get('large_limit_orders'):
            bo_score += 20
            for o in bo['large_limit_orders'][:2]:
                bo_detected.append(f"limit:{o.side}@{o.price}")
        if bo.get('iceberg_detected'):
            bo_score += 30; bo_detected.append("iceberg")

        # Combine weighted score
        weights = self.config.scoring
        # Safe attribute access with defaults
        context_w = getattr(weights, 'context_weight', 0.25)
        location_w = getattr(weights, 'location_weight', 0.40)
        confirmation_w = getattr(weights, 'confirmation_weight', 0.25)
        big_orders_w = getattr(weights, 'big_orders_weight', 0.10)

        total = (score_ctx * context_w +
                 score_loc * location_w +
                 conf_score * confirmation_w +
                 bo_score * big_orders_w)

        # DEBUG: Log score calculation
        logger.debug(f"[CLC] {direction} Final: ctx={score_ctx:.1f}*{context_w} + loc={score_loc:.1f}*{location_w} + conf={conf_score:.1f}*{confirmation_w} + bo={bo_score:.1f}*{big_orders_w} = {total:.1f}")

        # Apply feedback-adjusted threshold logic if available
        adjusted_threshold = getattr(self.config.scoring, 'min_entry_score', 75.0)
        if self.feedback_system and self.feedback_system.learning_enabled:
            adjusted_threshold = self.feedback_system.get_adjusted_threshold(direction, adjusted_threshold)

        # assemble CLCScore
        clc = CLCScore(
            total_score=total,
            context_score=score_ctx,
            location_score=score_loc,
            confirmation_score=conf_score,
            big_orders_score=bo_score,
            context_bias=bias,
            at_location=at_location,
            location_type=loc_type,
            confirmation_signals=conf_signals,
            big_orders_detected=bo_detected,
            reasons=reasons + loc_reasons + conf_signals + bo_detected,
            warnings=conf_warnings
        )

        # dynamic rule: penalize counter-bias trades
        expected_bias = ContextBias.BULLISH if direction=="LONG" else ContextBias.BEARISH
        if clc.context_bias != expected_bias and clc.context_bias != ContextBias.NEUTRAL:
            clc.total_score *= 0.7
            clc.warnings.append("counter-trend penalty applied")

        return clc

