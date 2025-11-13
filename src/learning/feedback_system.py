"""
Adaptive feedback system (refined / conservative)
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class ManualZone:
    zone_id: str
    symbol: str = ""  # Added symbol field
    price_level: float = 0.0
    upper_bound: float = 0.0
    lower_bound: float = 0.0
    zone_type: str = "both"
    confidence: float = 3.0
    created_at: int = 0
    hits: int = 0
    successful_bounces: int = 0
    false_breaks: int = 0

    @property
    def success_rate(self):
        if self.hits == 0:
            return 0.5
        return self.successful_bounces / self.hits

    @property
    def adjusted_weight(self):
        if self.hits < 5:
            return 0.7
        s = self.success_rate
        if s >= 0.7:
            return 1.5
        elif s >= 0.5:
            return 1.0
        elif s >= 0.3:
            return 0.5
        else:
            return 0.2

class AdaptiveFeedbackSystem:
    def __init__(self, config):
        self.config = config
        self.feedback_history = []
        self.manual_zones: Dict[str, ManualZone] = {}
        self.missed_setups = []  # Track missed trading opportunities
        self.parameter_adjustments = {}
        self.learning_enabled = False
        self.total_feedback_count = 0
        self.feedback_quality_score = 0.5
        self._load()

    def _load(self):
        Path('data').mkdir(exist_ok=True)
        try:
            with open(self.config.learning.feedback_file, 'r') as f:
                data = json.load(f)
                self.feedback_history = data.get('feedback', [])
                self.missed_setups = data.get('missed_setups', [])
                self.parameter_adjustments = data.get('parameter_adjustments', {})
                self.learning_enabled = data.get('learning_enabled', False)
                self.feedback_quality_score = data.get('feedback_quality_score', 0.5)
                self.total_feedback_count = data.get('total_feedback_count', len(self.feedback_history))
        except FileNotFoundError:
            pass
        try:
            with open('data/manual_zones.json','r') as f:
                mz = json.load(f)
                for zid, z in mz.items():
                    self.manual_zones[zid] = ManualZone(**z)
        except FileNotFoundError:
            pass

    def add_feedback(self, trade_id: str, feedback_type: str, notes: str = "", trade_outcome: Optional[str] = None, actual_pnl: float = 0.0):
        rec = {'trade_id': trade_id, 'feedback_type': feedback_type, 'notes': notes, 'timestamp': int(time.time()*1000), 'trade_outcome': trade_outcome, 'actual_pnl': actual_pnl}
        self.feedback_history.append(rec)
        self.total_feedback_count += 1
        # update quality if outcome provided
        if trade_outcome is not None:
            is_positive_feedback = feedback_type in ('good_long','good_short')
            is_positive_outcome = actual_pnl > 0
            aligned = is_positive_feedback == is_positive_outcome
            alpha = 0.1
            self.feedback_quality_score = (1-alpha)*self.feedback_quality_score + alpha*(1.0 if aligned else 0.0)
        self._maybe_enable_learning()
        self._save()

    def add_manual_zone(self, price_level: float, zone_type: str, size_pct: float = 0.003):
        zid = f"manual_{int(time.time()*1000)}"
        zone = ManualZone(zone_id=zid, price_level=price_level, upper_bound=price_level*(1+size_pct), lower_bound=price_level*(1-size_pct), zone_type=zone_type, confidence=0.5, created_at=int(time.time()*1000))
        self.manual_zones[zid] = zone
        self._save_manual_zones()
        return zone

    def update_zone_validation(self, zone_id: str, price_touched: bool, bounced: bool, broke_through: bool):
        if zone_id not in self.manual_zones:
            return
        z = self.manual_zones[zone_id]
        if price_touched:
            z.hits += 1
            if bounced:
                z.successful_bounces += 1
            if broke_through:
                z.false_breaks += 1
        self._save_manual_zones()

    def get_adjusted_threshold(self, direction: str, base_threshold: float) -> float:
        if not self.learning_enabled:
            return base_threshold
        adj = self.parameter_adjustments.get(f"{direction.lower()}_threshold_adjustment", 0.0)
        return base_threshold + adj

    def _maybe_enable_learning(self):
        if self.total_feedback_count >= 30 and self.feedback_quality_score >= 0.4:
            if not self.learning_enabled:
                logger.info("[FEEDBACK] Learning enabled")
            self.learning_enabled = True

    def _save(self):
        try:
            with open(self.config.learning.feedback_file, 'w') as f:
                json.dump({
                    'feedback': self.feedback_history,
                    'missed_setups': self.missed_setups,
                    'parameter_adjustments': self.parameter_adjustments,
                    'learning_enabled': self.learning_enabled,
                    'feedback_quality_score': self.feedback_quality_score,
                    'total_feedback_count': self.total_feedback_count
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving feedback: {e}")

    def _save_manual_zones(self):
        try:
            with open('data/manual_zones.json', 'w') as f:
                json.dump({zid: z.__dict__ for zid,z in self.manual_zones.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving manual zones: {e}")

    def add_trade_feedback(self, trade_id: str, rating: int, notes: str = "", trade_data: dict = None):
        """
        Add human rating for a specific trade (1-5 stars).

        Args:
            trade_id: Unique trade identifier
            rating: 1-5 stars
            notes: Optional notes about why this rating
            trade_data: Full trade data for analysis
        """
        feedback = {
            'trade_id': trade_id,
            'rating': rating,
            'notes': notes,
            'timestamp': int(time.time() * 1000),
            'trade_data': trade_data
        }

        self.feedback_history.append(feedback)
        self.total_feedback_count += 1

        # Update quality score
        if trade_data and 'pnl' in trade_data:
            is_positive_rating = rating >= 4  # 4-5 stars = good
            is_positive_outcome = trade_data['pnl'] > 0
            aligned = is_positive_rating == is_positive_outcome

            alpha = 0.1
            self.feedback_quality_score = (1-alpha)*self.feedback_quality_score + alpha*(1.0 if aligned else 0.0)

        self._maybe_enable_learning()
        self._save()

        logger.info(f"[FEEDBACK] Trade {trade_id} rated {rating}/5 stars")

    def mark_missed_setup(self, symbol: str, direction: str, entry_price: float,
                         reasons: List[str], expected_outcome: str, notes: str = ""):
        """
        Mark a trading opportunity that the algo missed.

        Args:
            symbol: Trading pair
            direction: LONG or SHORT
            entry_price: Where trade should have been entered
            reasons: List of why this was a good setup
            expected_outcome: "Would have won", "Would have lost", or "Uncertain"
            notes: Additional notes
        """
        missed = {
            'symbol': symbol,
            'direction': direction,
            'entry_price': entry_price,
            'reasons': reasons,
            'expected_outcome': expected_outcome,
            'notes': notes,
            'timestamp': int(time.time() * 1000)
        }

        self.missed_setups.append(missed)
        self._save()

        logger.info(f"[FEEDBACK] Missed setup marked: {direction} {symbol} @ {entry_price}")

    def analyze_missed_setups(self) -> Dict:
        """
        Analyze patterns in missed trading opportunities.

        Returns dict with:
        - total_missed: Total count
        - by_direction: Breakdown by LONG/SHORT
        - common_reasons: Most common reasons
        - would_have_won: Count of expected winners
        - top_missing_pattern: Most common pattern
        """
        if len(self.missed_setups) < 5:
            return {'message': 'Need at least 5 missed setups for analysis'}

        analysis = {
            'total_missed': len(self.missed_setups),
            'by_direction': {'LONG': 0, 'SHORT': 0},
            'common_reasons': {},
            'would_have_won': 0,
            'would_have_lost': 0,
            'uncertain': 0
        }

        for missed in self.missed_setups:
            # Count by direction
            analysis['by_direction'][missed['direction']] += 1

            # Count reasons
            for reason in missed['reasons']:
                analysis['common_reasons'][reason] = analysis['common_reasons'].get(reason, 0) + 1

            # Count outcomes
            outcome = missed['expected_outcome'].lower()
            if 'won' in outcome:
                analysis['would_have_won'] += 1
            elif 'lost' in outcome:
                analysis['would_have_lost'] += 1
            else:
                analysis['uncertain'] += 1

        # Find most common pattern
        if analysis['common_reasons']:
            most_common = max(analysis['common_reasons'].items(), key=lambda x: x[1])
            analysis['top_missing_pattern'] = most_common[0]
            analysis['top_missing_count'] = most_common[1]

        return analysis

    def get_sr_zone_adjustments(self, symbol: str) -> List[Dict]:
        """
        Get learned multipliers for S/R zones based on feedback.

        Returns list of dicts with:
        - level: Price level
        - multiplier: Strength multiplier (0.7-1.3)
        - num_ratings: How many times rated
        - avg_quality: Average rating quality
        """
        adjustments = []

        # Analyze feedback for zones
        zone_ratings = [
            f for f in self.feedback_history
            if f.get('rating') and f.get('trade_data') and f['trade_data'].get('symbol') == symbol
        ]

        if not zone_ratings:
            return adjustments

        # Group by similar price levels
        level_groups = {}

        for rating in zone_ratings:
            trade_data = rating['trade_data']
            entry_price = trade_data.get('entry_price', 0)

            if entry_price == 0:
                continue

            # Find or create group
            found_group = False
            for group_level in level_groups:
                if abs(entry_price - group_level) / entry_price < 0.005:  # Within 0.5%
                    level_groups[group_level].append(rating)
                    found_group = True
                    break

            if not found_group:
                level_groups[entry_price] = [rating]

        # Calculate adjustments
        for level, ratings in level_groups.items():
            if len(ratings) < 3:  # Need at least 3 ratings
                continue

            avg_rating = sum(r['rating'] for r in ratings) / len(ratings)

            # Convert 1-5 star rating to multiplier
            # 5 stars = 1.3×, 3 stars = 1.0×, 1 star = 0.7×
            multiplier = 0.7 + (avg_rating - 1) * 0.15

            adjustments.append({
                'level': level,
                'multiplier': multiplier,
                'num_ratings': len(ratings),
                'avg_quality': avg_rating
            })

        return adjustments

