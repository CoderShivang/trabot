"""
Adaptive feedback system (refined / conservative)
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List
from utils.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class ManualZone:
    zone_id: str
    price_level: float
    upper_bound: float
    lower_bound: float
    zone_type: str
    confidence: float
    created_at: int
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

