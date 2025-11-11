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

        # Price vs VWAP
        if current_price > ctx.vwap:
            bias_votes += 1
            if direction == "LONG":
                score_ctx += 20
                reasons.append("Above VWAP (bullish for LONG)")
                logger.debug(f"[CLC] {direction}: Price > VWAP, adding 20 points (now {score_ctx})")
            else:
                score_ctx += 5
                reasons.append("Above VWAP (bearish for SHORT)")
                logger.debug(f"[CLC] {direction}: Price > VWAP (counter-trend), adding 5 points (now {score_ctx})")
        else:
            bias_votes -= 1
            if direction == "SHORT":
                score_ctx += 20
                reasons.append("Below VWAP (bearish for SHORT)")
                logger.debug(f"[CLC] {direction}: Price < VWAP, adding 20 points (now {score_ctx})")
            else:
                score_ctx += 5
                reasons.append("Below VWAP (bullish for LONG)")
                logger.debug(f"[CLC] {direction}: Price < VWAP (counter-trend), adding 5 points (now {score_ctx})")

        # EMA trend
        if ctx.ema50 > ctx.ema200:
            bias_votes += 1
            if direction == "LONG":
                score_ctx += 25
                reasons.append("EMA50 > EMA200 (bullish for LONG)")
                logger.debug(f"[CLC] {direction}: EMA50 > EMA200, adding 25 points (now {score_ctx})")
            else:
                score_ctx += 10
                reasons.append("EMA50 > EMA200 (bearish for SHORT)")
                logger.debug(f"[CLC] {direction}: EMA50 > EMA200 (counter-trend), adding 10 points (now {score_ctx})")
        else:
            bias_votes -= 1
            if direction == "SHORT":
                score_ctx += 25
                reasons.append("EMA50 < EMA200 (bearish for SHORT)")
                logger.debug(f"[CLC] {direction}: EMA50 < EMA200, adding 25 points (now {score_ctx})")
            else:
                score_ctx += 10
                reasons.append("EMA50 < EMA200 (bullish for LONG)")
                logger.debug(f"[CLC] {direction}: EMA50 < EMA200 (counter-trend), adding 10 points (now {score_ctx})")

        # Determine bias
        if bias_votes >= 2:
            bias = ContextBias.BULLISH
        elif bias_votes <= -2:
            bias = ContextBias.BEARISH

        # 2) location
        locations = await self.location_detector.get_all_locations(symbol, current_price)
        at_location = False; loc_type=None; score_loc=0.0; loc_reasons=[]
        sr_zones = locations.get('sr_zones', [])
        max_dist = self.config.clc_strategy.location.get('max_distance_from_level_pct', 0.005) if isinstance(self.config.clc_strategy.location, dict) else 0.005
        for z in sr_zones:
            # SRZone is a dataclass, access attributes not dict keys
            dist = abs(current_price - z.level)/current_price
            if dist <= max_dist:
                at_location = True
                score_loc += 40 * (z.strength / 10.0)  # Normalize strength (0-10) to weight (0-1)
                loc_type = LocationType.SR_ZONE
                loc_reasons.append(f"At SR {z.level}")
                break
        # VWAP bands
        vwap = locations.get('vwap_15m')
        if vwap:
            dist = abs(current_price - vwap)/current_price
            if dist <= max_dist:
                at_location = True
                score_loc += 15
                loc_type = LocationType.VWAP_BAND
                loc_reasons.append("At VWAP 15m")

        # 3) confirmation
        conf = self.confirmation_analyzer.analyze(symbol, orderbook, recent_trades)
        conf_score = 0.0; conf_signals=[]; conf_warnings=[]
        # use multiple signals: imbalance, delta, tape velocity, divergence, absorption
        if conf['imbalance'] >= self.config.clc_strategy.confirmation.get('imbalance_threshold',0.7):
            conf_score += 25; conf_signals.append(f"imbalance:{conf['imbalance']:.2f}")
        if conf['delta'] >= self.config.clc_strategy.confirmation.get('delta_threshold',0.6):
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

