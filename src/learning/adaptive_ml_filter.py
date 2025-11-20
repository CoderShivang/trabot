"""
Adaptive ML Filter with False Negative Analysis

Key Innovation:
- Tracks BOTH accepted and rejected signals
- Simulates outcomes for rejected signals
- Adjusts threshold if rejecting too many profitable trades
- Maintains strict filter for signals that would have lost

This prevents the ML from being TOO conservative and missing good setups!
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class RejectedSignal:
    """Track rejected signal for later analysis"""
    signal: Dict
    market_data: Dict
    ml_win_prob: float
    rejection_reason: str
    timestamp: datetime

    # Simulated outcome (filled after window)
    simulated_outcome: int = None  # 1 = would have won, 0 = would have lost
    simulated_pnl: float = None
    opportunity_cost: float = None  # PnL we missed by rejecting


class AdaptiveMLFilter:
    """
    Adaptive ML filter that learns from rejected signals

    Features:
    1. Tracks all rejected signals with market conditions
    2. Simulates what would have happened if we took them
    3. Calculates false negative rate (good trades we rejected)
    4. Adaptively adjusts win probability threshold
    5. Maintains bounds to prevent being too permissive
    """

    def __init__(
        self,
        initial_min_win_prob: float = 0.60,
        min_threshold: float = 0.48,  # Never go below this
        max_threshold: float = 0.70,  # Never go above this
        adjustment_step: float = 0.02,  # Adjust by 2% at a time
        false_negative_tolerance: float = 0.25,  # Tolerate 25% false negatives
        min_opportunity_cost: float = 5.0  # Only adjust if missing >$5 in profits
    ):
        self.current_threshold = initial_min_win_prob
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.adjustment_step = adjustment_step
        self.false_negative_tolerance = false_negative_tolerance
        self.min_opportunity_cost = min_opportunity_cost

        # Tracking
        self.rejected_signals: List[RejectedSignal] = []
        self.threshold_history: List[Dict] = []

        # Statistics
        self.total_false_negatives = 0
        self.total_true_negatives = 0
        self.total_opportunity_cost = 0.0

    def record_rejection(
        self,
        signal: Dict,
        market_data: Dict,
        ml_win_prob: float,
        reason: str = "Below threshold"
    ):
        """Record a rejected signal for later analysis"""
        rejected = RejectedSignal(
            signal=signal,
            market_data=market_data,
            ml_win_prob=ml_win_prob,
            rejection_reason=reason,
            timestamp=datetime.now()
        )
        self.rejected_signals.append(rejected)

    def simulate_rejected_outcomes(
        self,
        window_num: int,
        actual_trades: List[Dict]
    ) -> Dict:
        """
        Simulate what would have happened if we took rejected signals

        Args:
            window_num: Current window number
            actual_trades: List of trades that were actually executed

        Returns:
            Analysis dict with false negative metrics
        """
        if not self.rejected_signals:
            logger.info(f"[ADAPTIVE] Window #{window_num}: No rejected signals to analyze")
            return {
                'false_negatives': 0,
                'true_negatives': 0,
                'false_negative_rate': 0.0,
                'opportunity_cost': 0.0
            }

        logger.info(f"\n[ADAPTIVE] Analyzing {len(self.rejected_signals)} rejected signals from window #{window_num}...")

        false_negatives = 0  # Rejected signals that would have won
        true_negatives = 0   # Rejected signals that would have lost (correct rejection)
        total_opportunity_cost = 0.0

        for rejected in self.rejected_signals:
            # Simulate outcome using similar market conditions from actual trades
            # For simplicity, we'll use the signal's features to estimate outcome
            simulated_outcome = self._simulate_trade_outcome(rejected, actual_trades)

            rejected.simulated_outcome = simulated_outcome['outcome']
            rejected.simulated_pnl = simulated_outcome['pnl']

            if rejected.simulated_outcome == 1:
                # This was a FALSE NEGATIVE - we rejected a winner!
                false_negatives += 1
                rejected.opportunity_cost = rejected.simulated_pnl
                total_opportunity_cost += rejected.simulated_pnl

                logger.debug(f"  [FN] Rejected winner: Win prob {rejected.ml_win_prob:.1%} | "
                           f"Would have made ${rejected.simulated_pnl:.2f}")
            else:
                # This was a TRUE NEGATIVE - correct rejection
                true_negatives += 1

        total_rejected = len(self.rejected_signals)
        false_negative_rate = false_negatives / total_rejected if total_rejected > 0 else 0.0

        # Update cumulative stats
        self.total_false_negatives += false_negatives
        self.total_true_negatives += true_negatives
        self.total_opportunity_cost += total_opportunity_cost

        logger.info(f"[ADAPTIVE] Analysis Results:")
        logger.info(f"  Total Rejected: {total_rejected}")
        logger.info(f"  False Negatives (rejected winners): {false_negatives} ({false_negative_rate:.1%})")
        logger.info(f"  True Negatives (rejected losers): {true_negatives}")
        logger.info(f"  Opportunity Cost: ${total_opportunity_cost:.2f}")

        # Clear rejected signals for next window
        self.rejected_signals = []

        return {
            'false_negatives': false_negatives,
            'true_negatives': true_negatives,
            'false_negative_rate': false_negative_rate,
            'opportunity_cost': total_opportunity_cost,
            'total_rejected': total_rejected
        }

    def _simulate_trade_outcome(
        self,
        rejected: RejectedSignal,
        actual_trades: List[Dict]
    ) -> Dict:
        """
        Estimate what outcome the rejected signal would have had

        Strategy:
        1. Find actual trades with similar conditions
        2. Use their average outcome as estimate
        3. Apply conservative bias (assume slightly worse than similar trades)
        """
        if not actual_trades:
            # No actual trades to compare against - assume loss
            return {'outcome': 0, 'pnl': -1.0}

        # Extract features from rejected signal
        signal = rejected.signal
        market_data = rejected.market_data

        # Find similar trades based on:
        # - Same direction
        # - Similar confidence level
        # - Similar market conditions
        similar_trades = []
        for trade in actual_trades:
            # Check direction match
            if trade.get('direction') != signal.get('direction'):
                continue

            # Check signal type match
            trade_signal = trade.get('signal', {})
            if trade_signal.get('signal_type') != signal.get('signal_type'):
                continue

            # Check confidence similarity (within 10%)
            confidence_diff = abs(trade_signal.get('confidence', 0) - signal.get('confidence', 0))
            if confidence_diff <= 10:
                similar_trades.append(trade)

        if similar_trades:
            # Use average outcome of similar trades
            # Calculate net PnL (gross - fees)
            net_pnls = []
            for trade in similar_trades:
                gross_pnl = trade.get('pnl', 0)
                fees = trade.get('total_fees', 0)
                net_pnl = gross_pnl - fees
                net_pnls.append(net_pnl)

            avg_pnl = np.mean(net_pnls)

            # Apply conservative bias - assume 80% of actual performance
            # (rejected signal might not have been as good)
            estimated_pnl = avg_pnl * 0.8

            # Determine outcome
            outcome = 1 if estimated_pnl > 0 else 0

            return {'outcome': outcome, 'pnl': estimated_pnl}
        else:
            # No similar trades - use ML win probability as estimate
            # If win prob was close to threshold, give it benefit of doubt
            if rejected.ml_win_prob >= self.current_threshold - 0.05:
                # Close call - assume small win
                return {'outcome': 1, 'pnl': 0.5}
            else:
                # Clearly below threshold - assume loss
                return {'outcome': 0, 'pnl': -0.5}

    def adjust_threshold(
        self,
        window_num: int,
        analysis: Dict
    ) -> bool:
        """
        Adjust win probability threshold based on false negative analysis

        Args:
            window_num: Current window number
            analysis: Analysis dict from simulate_rejected_outcomes()

        Returns:
            True if threshold was adjusted
        """
        false_negative_rate = analysis['false_negative_rate']
        opportunity_cost = analysis['opportunity_cost']

        old_threshold = self.current_threshold
        adjusted = False

        # Decision logic
        if false_negative_rate > self.false_negative_tolerance and opportunity_cost > self.min_opportunity_cost:
            # We're rejecting too many good trades - be MORE permissive
            new_threshold = max(
                self.min_threshold,
                self.current_threshold - self.adjustment_step
            )

            if new_threshold != self.current_threshold:
                self.current_threshold = new_threshold
                adjusted = True

                logger.warning(f"[ADAPTIVE] LOWERING threshold: {old_threshold:.1%} -> {new_threshold:.1%}")
                logger.warning(f"           Reason: {false_negative_rate:.1%} false negatives, "
                             f"${opportunity_cost:.2f} opportunity cost")

        elif false_negative_rate < self.false_negative_tolerance * 0.5 and opportunity_cost < self.min_opportunity_cost * 0.5:
            # We're doing well - could afford to be slightly MORE strict
            # But only if we're not already at max
            new_threshold = min(
                self.max_threshold,
                self.current_threshold + self.adjustment_step * 0.5  # Smaller increase
            )

            if new_threshold != self.current_threshold:
                self.current_threshold = new_threshold
                adjusted = True

                logger.info(f"[ADAPTIVE] RAISING threshold: {old_threshold:.1%} -> {new_threshold:.1%}")
                logger.info(f"           Reason: Low false negatives ({false_negative_rate:.1%}), "
                          f"can be more selective")

        # Record threshold history
        self.threshold_history.append({
            'window': window_num,
            'threshold': self.current_threshold,
            'false_negative_rate': false_negative_rate,
            'opportunity_cost': opportunity_cost,
            'adjusted': adjusted
        })

        return adjusted

    def get_current_threshold(self) -> float:
        """Get current adaptive threshold"""
        return self.current_threshold

    def get_stats(self) -> Dict:
        """Get cumulative statistics"""
        total_analyzed = self.total_false_negatives + self.total_true_negatives

        return {
            'current_threshold': self.current_threshold,
            'total_false_negatives': self.total_false_negatives,
            'total_true_negatives': self.total_true_negatives,
            'cumulative_fn_rate': self.total_false_negatives / total_analyzed if total_analyzed > 0 else 0.0,
            'total_opportunity_cost': self.total_opportunity_cost,
            'threshold_adjustments': len([h for h in self.threshold_history if h['adjusted']]),
            'threshold_history': self.threshold_history
        }

    def get_report(self) -> str:
        """Generate human-readable report"""
        stats = self.get_stats()

        report = f"""
╔══════════════════════════════════════════════════════════════╗
║         ADAPTIVE ML FILTER - PERFORMANCE REPORT              ║
╚══════════════════════════════════════════════════════════════╝

Current Settings:
   Win Probability Threshold: {stats['current_threshold']:.1%}
   Threshold Range: {self.min_threshold:.1%} - {self.max_threshold:.1%}

Cumulative Analysis:
   Total False Negatives: {stats['total_false_negatives']} (rejected winners)
   Total True Negatives: {stats['total_true_negatives']} (rejected losers)
   False Negative Rate: {stats['cumulative_fn_rate']:.1%}
   Total Opportunity Cost: ${stats['total_opportunity_cost']:.2f}

Threshold Adjustments:
   Total Adjustments: {stats['threshold_adjustments']}

Threshold History:
"""
        for h in stats['threshold_history'][-5:]:  # Last 5 windows
            arrow = "v" if h['adjusted'] and h['threshold'] < self.current_threshold else "^" if h['adjusted'] else "-"
            report += f"   Window #{h['window']:2d}: {h['threshold']:.1%} {arrow} | FN Rate: {h['false_negative_rate']:.1%} | Cost: ${h['opportunity_cost']:.2f}\n"

        return report


# Example usage
if __name__ == "__main__":
    # Create adaptive filter
    adaptive_filter = AdaptiveMLFilter(
        initial_min_win_prob=0.60,
        min_threshold=0.48,
        max_threshold=0.70,
        false_negative_tolerance=0.25
    )

    # Simulate window 1
    print("Window 1:")
    adaptive_filter.record_rejection(
        signal={'direction': 'LONG', 'signal_type': 'mean_reversion', 'confidence': 70},
        market_data={'volatility': 0.01},
        ml_win_prob=0.58,
        reason="Below 0.60 threshold"
    )

    # After window, analyze
    actual_trades = [
        {'direction': 'LONG', 'signal': {'signal_type': 'mean_reversion', 'confidence': 72}, 'pnl': 3.0, 'total_fees': 0.5}
    ]

    analysis = adaptive_filter.simulate_rejected_outcomes(1, actual_trades)
    adjusted = adaptive_filter.adjust_threshold(1, analysis)

    print(adaptive_filter.get_report())
