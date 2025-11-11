"""
Trade Explainability System - Explains WHY the algo took each trade.

Provides human-readable explanations of:
- Which signals were detected
- Why the score was high/low
- What the algo "saw" in the market
- ML predictions and confidence
"""

from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TradeExplanation:
    """Complete explanation of why a trade was taken"""

    # Basic info
    symbol: str
    direction: str
    entry_price: float
    timestamp: int

    # CLC breakdown
    total_score: float
    context_score: float
    location_score: float
    confirmation_score: float
    big_orders_score: float

    # What the algo saw
    context_reasons: List[str]
    location_reasons: List[str]
    confirmation_signals: List[str]
    big_orders_detected: List[str]
    warnings: List[str]

    # Location details
    at_location: bool
    zone_details: Dict
    zone_methods: List[str]  # Which methods detected the zone
    zone_confluence: int  # How many methods agreed

    # ML prediction (if available)
    ml_enabled: bool
    ml_win_probability: float
    ml_decision: str

    # Human feedback context
    similar_setups_rated: int
    avg_human_rating: float

    def to_markdown(self) -> str:
        """Generate markdown explanation for display"""

        md = f"## {self.direction} {self.symbol} @ ${self.entry_price:,.2f}\n\n"
        md += f"**Time:** {datetime.fromtimestamp(self.timestamp/1000).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"

        # Score breakdown
        md += "### 📊 Score Breakdown\n\n"
        md += f"**Total Score:** {self.total_score:.1f}/100\n\n"

        md += "| Component | Score | Weight | Contribution |\n"
        md += "|-----------|-------|--------|-------------|\n"
        md += f"| Context | {self.context_score:.1f} | 25% | {self.context_score*0.25:.1f} |\n"
        md += f"| Location | {self.location_score:.1f} | 30% | {self.location_score*0.30:.1f} |\n"
        md += f"| Confirmation | {self.confirmation_score:.1f} | 25% | {self.confirmation_score*0.25:.1f} |\n"
        md += f"| Big Orders | {self.big_orders_score:.1f} | 20% | {self.big_orders_score*0.20:.1f} |\n\n"

        # Context analysis
        md += "### 🌍 Context Analysis (Market Structure)\n\n"
        if self.context_reasons:
            for reason in self.context_reasons:
                md += f"- ✓ {reason}\n"
        else:
            md += "- No context signals\n"
        md += "\n"

        # Location analysis
        md += "### 📍 Location Analysis (S/R Zones)\n\n"
        if self.at_location:
            md += f"**At Key Level:** YES ✓\n\n"

            if self.zone_details:
                zone = self.zone_details
                md += f"- **Level:** ${zone.get('level', 0):,.2f}\n"
                md += f"- **Type:** {zone.get('zone_type', 'unknown').upper()}\n"
                md += f"- **Strength:** {zone.get('strength', 0):.1f}/10.0\n"
                md += f"- **Confluence:** {self.zone_confluence} methods detected this level\n"

                if self.zone_methods:
                    md += f"- **Detection Methods:** {', '.join(self.zone_methods)}\n"

            md += "\n**Why This Level:**\n"
            for reason in self.location_reasons:
                md += f"- ✓ {reason}\n"
        else:
            md += "**At Key Level:** NO ✗\n"
            md += "- Trade taken without strong location signal\n"
        md += "\n"

        # Order flow confirmation
        md += "### ⚡ Order Flow Confirmation (Tape Reading)\n\n"
        if self.confirmation_signals:
            md += f"**Signals Detected:** {len(self.confirmation_signals)}\n\n"
            for signal in self.confirmation_signals:
                # Format signal nicely
                if ":" in signal:
                    signal_type, value = signal.split(":", 1)
                    md += f"- **{signal_type.replace('_', ' ').title()}:** {value}\n"
                else:
                    md += f"- ✓ {signal.replace('_', ' ').title()}\n"
        else:
            md += "- No confirmation signals detected\n"
        md += "\n"

        # Big orders / institutional activity
        md += "### 🐋 Big Orders (Institutional Activity)\n\n"
        if self.big_orders_detected:
            for order in self.big_orders_detected:
                md += f"- 🚨 {order}\n"
        else:
            md += "- No large orders detected\n"
        md += "\n"

        # Warnings
        if self.warnings:
            md += "### ⚠️ Warnings\n\n"
            for warning in self.warnings:
                md += f"- ⚠️ {warning}\n"
            md += "\n"

        # ML prediction
        if self.ml_enabled:
            md += "### 🤖 ML Prediction\n\n"
            md += f"**Win Probability:** {self.ml_win_probability*100:.1f}%\n\n"
            md += f"**Decision:** {self.ml_decision}\n\n"

        # Human feedback context
        if self.similar_setups_rated > 0:
            md += "### 👤 Human Feedback Context\n\n"
            md += f"- You've rated {self.similar_setups_rated} similar setups\n"
            md += f"- Average rating: {self.avg_human_rating:.1f}/5.0 stars\n"
            md += "\n"

        return md

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON storage"""

        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'timestamp': self.timestamp,
            'scores': {
                'total': self.total_score,
                'context': self.context_score,
                'location': self.location_score,
                'confirmation': self.confirmation_score,
                'big_orders': self.big_orders_score
            },
            'reasons': {
                'context': self.context_reasons,
                'location': self.location_reasons,
                'confirmation': self.confirmation_signals,
                'big_orders': self.big_orders_detected,
                'warnings': self.warnings
            },
            'location': {
                'at_location': self.at_location,
                'zone_details': self.zone_details,
                'zone_methods': self.zone_methods,
                'zone_confluence': self.zone_confluence
            },
            'ml': {
                'enabled': self.ml_enabled,
                'win_probability': self.ml_win_probability,
                'decision': self.ml_decision
            },
            'human_feedback': {
                'similar_setups_rated': self.similar_setups_rated,
                'avg_rating': self.avg_human_rating
            }
        }


def create_trade_explanation(
    symbol: str,
    direction: str,
    entry_price: float,
    timestamp: int,
    clc_score,
    ml_prediction: Dict = None,
    human_context: Dict = None
) -> TradeExplanation:
    """
    Create a complete trade explanation from CLC score and other data.

    Args:
        symbol: Trading pair
        direction: LONG or SHORT
        entry_price: Entry price
        timestamp: Entry timestamp (ms)
        clc_score: CLCScore object from strategy
        ml_prediction: Dict with ML prediction data (optional)
        human_context: Dict with human feedback context (optional)

    Returns:
        TradeExplanation object
    """

    # Extract zone details
    zone_details = {}
    zone_methods = []
    zone_confluence = 0

    if hasattr(clc_score, 'location_type') and clc_score.location_type:
        # There's a best zone
        if hasattr(clc_score, 'best_zone') and clc_score.best_zone:
            zone = clc_score.best_zone
            zone_details = {
                'level': getattr(zone, 'level', 0),
                'zone_type': getattr(zone, 'zone_type', 'unknown'),
                'strength': getattr(zone, 'strength', 0)
            }
            zone_methods = [m.value for m in getattr(zone, 'methods', [])]
            zone_confluence = len(zone_methods)

    # ML prediction
    ml_enabled = False
    ml_win_prob = 0.5
    ml_decision = "Not used"

    if ml_prediction:
        ml_enabled = ml_prediction.get('enabled', False)
        ml_win_prob = ml_prediction.get('win_probability', 0.5)
        ml_decision = ml_prediction.get('decision', "Not used")

    # Human feedback context
    similar_rated = 0
    avg_rating = 0.0

    if human_context:
        similar_rated = human_context.get('similar_setups_rated', 0)
        avg_rating = human_context.get('avg_rating', 0.0)

    return TradeExplanation(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        timestamp=timestamp,
        total_score=clc_score.total_score,
        context_score=clc_score.context_score,
        location_score=clc_score.location_score,
        confirmation_score=clc_score.confirmation_score,
        big_orders_score=clc_score.big_orders_score,
        context_reasons=clc_score.reasons if hasattr(clc_score, 'reasons') else [],
        location_reasons=[],  # Will be populated from location_detector
        confirmation_signals=clc_score.confirmation_signals if hasattr(clc_score, 'confirmation_signals') else [],
        big_orders_detected=clc_score.big_orders_detected if hasattr(clc_score, 'big_orders_detected') else [],
        warnings=clc_score.warnings if hasattr(clc_score, 'warnings') else [],
        at_location=clc_score.at_location if hasattr(clc_score, 'at_location') else False,
        zone_details=zone_details,
        zone_methods=zone_methods,
        zone_confluence=zone_confluence,
        ml_enabled=ml_enabled,
        ml_win_probability=ml_win_prob,
        ml_decision=ml_decision,
        similar_setups_rated=similar_rated,
        avg_human_rating=avg_rating
    )


def format_trade_summary(explanation: TradeExplanation) -> str:
    """Create a concise one-line summary of the trade"""

    summary_parts = []

    # Direction and price
    summary_parts.append(f"{explanation.direction} @ ${explanation.entry_price:,.2f}")

    # Score
    summary_parts.append(f"Score: {explanation.total_score:.0f}")

    # Key signals
    if explanation.at_location:
        summary_parts.append(f"At {explanation.zone_details.get('zone_type', 'zone')}")

    if len(explanation.confirmation_signals) > 0:
        summary_parts.append(f"{len(explanation.confirmation_signals)} signals")

    if len(explanation.big_orders_detected) > 0:
        summary_parts.append("Big orders")

    # ML
    if explanation.ml_enabled:
        summary_parts.append(f"ML: {explanation.ml_win_probability*100:.0f}%")

    return " | ".join(summary_parts)


def format_trade_emoji(explanation: TradeExplanation) -> str:
    """Get emoji indicator for trade quality"""

    if explanation.total_score >= 85:
        return "🟢"  # Excellent
    elif explanation.total_score >= 75:
        return "🟡"  # Good
    elif explanation.total_score >= 65:
        return "🟠"  # Fair
    else:
        return "🔴"  # Poor


def explain_why_rejected(
    symbol: str,
    direction: str,
    current_price: float,
    clc_score,
    rejection_reason: str
) -> str:
    """Explain why a potential trade was rejected"""

    explanation = f"## Trade Rejected: {direction} {symbol} @ ${current_price:,.2f}\n\n"
    explanation += f"**Reason:** {rejection_reason}\n\n"

    explanation += f"### Score Breakdown\n\n"
    explanation += f"- **Total Score:** {clc_score.total_score:.1f} (need ≥75)\n"
    explanation += f"- **At Location:** {'YES' if clc_score.at_location else 'NO'}\n"
    explanation += f"- **Confirmation Signals:** {len(clc_score.confirmation_signals)} (need ≥2)\n\n"

    if clc_score.total_score < 75:
        explanation += "❌ **Score too low** - Not enough confluence\n\n"

    if not clc_score.at_location:
        explanation += "❌ **Not at key level** - Wait for price to reach S/R zone\n\n"

    if len(clc_score.confirmation_signals) < 2:
        explanation += "❌ **Insufficient confirmation** - Need more order flow signals\n\n"

    return explanation
