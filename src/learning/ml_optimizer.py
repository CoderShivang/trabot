"""
ML Optimizer - Lightweight Random Forest for trade filtering and parameter optimization.

Uses scikit-learn Random Forest to:
1. Predict win probability for each trade setup
2. Filter low-quality setups (below 55% win probability)
3. Identify which features matter most
4. Suggest parameter adjustments

Designed to be VPS-friendly (CPU-only, no GPU needed).
"""

import os
import pickle
import time
from typing import Dict, List, Optional
from datetime import datetime

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

from utils.logger import setup_logger

logger = setup_logger(__name__)


class MLParameterOptimizer:
    """Lightweight ML for parameter tuning and trade filtering"""

    def __init__(self, config):
        self.config = config
        self.model: Optional[RandomForestClassifier] = None
        self.scaler = StandardScaler()
        self.feature_names = [
            'total_score', 'context_score', 'location_score', 'confirmation_score',
            'big_orders_score', 'hour', 'day_of_week', 'spread_bps', 'volume_ratio',
            'atr', 'trend_strength', 'timeframe_aligned', 'num_confirmations',
            'at_psych_level', 'distance_from_level', 'zone_strength',
            'direction', 'symbol'
        ]
        self.model_path = 'data/ml_model.pkl'
        self.min_samples = 100  # Need 100 trades before training
        self.last_trained_count = 0
        self.training_enabled = self.config.learning.get('enable_ml', False)

        # Load existing model if available
        if os.path.exists(self.model_path):
            self.load_model()

    def extract_features(self, trade_data: Dict) -> np.ndarray:
        """
        Extract 18 features from trade setup.

        Features:
        - CLC scores (5)
        - Time features (2)
        - Market microstructure (3)
        - Context details (3)
        - Location details (3)
        - Trade specifics (2)
        """

        clc_score = trade_data.get('clc_score', {})

        features = [
            # CLC scores
            clc_score.get('total_score', 0),
            clc_score.get('context_score', 0),
            clc_score.get('location_score', 0),
            clc_score.get('confirmation_score', 0),
            clc_score.get('big_orders_score', 0),

            # Time features (market sessions matter)
            self._get_hour_of_day(trade_data.get('timestamp', 0)),
            self._get_day_of_week(trade_data.get('timestamp', 0)),

            # Market microstructure
            trade_data.get('spread_bps', 0),
            trade_data.get('volume_ratio', 1.0),  # Current vol / avg vol
            trade_data.get('atr', 0),

            # Context details
            trade_data.get('trend_strength', 0),
            int(trade_data.get('timeframe_aligned', False)),
            len(clc_score.get('confirmation_signals', [])),

            # Location details
            int(trade_data.get('at_psychological_level', False)),
            trade_data.get('distance_from_level_pct', 0),
            trade_data.get('zone_strength', 0),

            # Trade specifics
            1 if trade_data['direction'] == 'LONG' else -1,
            1 if trade_data['symbol'] == 'BTCUSDT' else 0
        ]

        return np.array(features)

    def train_model(self, historical_trades: List[Dict]) -> bool:
        """
        Train Random Forest classifier to predict winning trades.

        Returns True if training successful, False otherwise.
        """

        if not self.training_enabled:
            logger.info("[ML] Training disabled in config")
            return False

        if len(historical_trades) < self.min_samples:
            logger.info(f"[ML] Insufficient data: {len(historical_trades)}/{self.min_samples} trades")
            return False

        try:
            logger.info(f"[ML] Training model on {len(historical_trades)} trades...")

            # Extract features and labels
            X = []
            y = []

            for trade in historical_trades:
                try:
                    features = self.extract_features(trade)
                    label = 1 if trade.get('pnl', 0) > 0 else 0  # Win = 1, Loss = 0

                    X.append(features)
                    y.append(label)
                except Exception as e:
                    logger.warning(f"[ML] Error extracting features from trade: {e}")
                    continue

            if len(X) < self.min_samples:
                logger.warning(f"[ML] Only {len(X)} valid trades after feature extraction")
                return False

            X = np.array(X)
            y = np.array(y)

            # Handle any NaN or inf values
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

            # Split for validation
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y if len(np.unique(y)) > 1 else None
            )

            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            # Train Random Forest (lightweight, no GPU needed)
            self.model = RandomForestClassifier(
                n_estimators=50,  # Small ensemble for speed
                max_depth=10,
                min_samples_split=10,
                min_samples_leaf=5,
                random_state=42,
                n_jobs=-1  # Use all CPU cores
            )

            self.model.fit(X_train_scaled, y_train)

            # Evaluate
            train_score = self.model.score(X_train_scaled, y_train)
            test_score = self.model.score(X_test_scaled, y_test)

            # Calculate win rate
            win_rate = np.mean(y) * 100

            logger.info(f"[ML] Model trained successfully:")
            logger.info(f"[ML]   Train accuracy: {train_score*100:.1f}%")
            logger.info(f"[ML]   Test accuracy: {test_score*100:.1f}%")
            logger.info(f"[ML]   Baseline win rate: {win_rate:.1f}%")

            # Check for overfitting
            if train_score - test_score > 0.15:  # More than 15% gap
                logger.warning(f"[ML] Possible overfitting detected (train-test gap: {(train_score-test_score)*100:.1f}%)")

            # Save model
            self.save_model()
            self.last_trained_count = len(historical_trades)

            return True

        except Exception as e:
            logger.error(f"[ML] Training failed: {e}", exc_info=True)
            return False

    def predict_trade_quality(self, trade_data: Dict) -> float:
        """
        Predict probability this trade will win (0-1).

        Returns 0.5 (neutral) if model not trained.
        """

        if self.model is None:
            return 0.5  # No prediction available

        try:
            features = self.extract_features(trade_data)
            features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
            features_scaled = self.scaler.transform(features.reshape(1, -1))

            # Get probability of winning (class 1)
            prob_win = self.model.predict_proba(features_scaled)[0][1]

            return float(prob_win)

        except Exception as e:
            logger.error(f"[ML] Prediction error: {e}", exc_info=True)
            return 0.5

    def should_take_trade(self, trade_data: Dict) -> tuple[bool, float, str]:
        """
        Decide if trade should be taken based on ML prediction.

        Returns:
        - should_take: bool
        - probability: float (0-1)
        - reason: str
        """

        if not self.training_enabled or self.model is None:
            return True, 0.5, "ML not enabled"

        min_prob = self.config.scoring.get('ml_min_win_probability', 0.55)
        prob_win = self.predict_trade_quality(trade_data)

        should_take = prob_win >= min_prob

        if should_take:
            reason = f"ML approves: {prob_win*100:.1f}% win probability"
        else:
            reason = f"ML rejects: {prob_win*100:.1f}% < {min_prob*100:.0f}% threshold"

        return should_take, prob_win, reason

    def get_feature_importance(self) -> Dict[str, float]:
        """Get which features matter most for predictions"""

        if self.model is None:
            return {}

        try:
            importances = self.model.feature_importances_
            importance_dict = dict(zip(self.feature_names, importances))

            # Sort by importance
            sorted_importance = dict(
                sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
            )

            return sorted_importance

        except Exception as e:
            logger.error(f"[ML] Error getting feature importance: {e}")
            return {}

    def suggest_threshold_adjustment(self, recent_trades: List[Dict], window: int = 50) -> Dict:
        """
        Suggest parameter adjustments based on recent performance.

        Analyzes last N trades to recommend changes.
        """

        if len(recent_trades) < 20:
            return {'message': 'Need at least 20 trades for suggestions'}

        # Use last N trades
        trades_to_analyze = recent_trades[-window:]

        wins = [t for t in trades_to_analyze if t.get('pnl', 0) > 0]
        losses = [t for t in trades_to_analyze if t.get('pnl', 0) <= 0]

        win_rate = len(wins) / len(trades_to_analyze) if trades_to_analyze else 0
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 0

        suggestions = {
            'current_win_rate': f"{win_rate*100:.1f}%",
            'num_trades_analyzed': len(trades_to_analyze),
            'adjustments': []
        }

        # Suggest increasing threshold if win rate too low
        if win_rate < 0.45:
            suggestions['adjustments'].append({
                'parameter': 'min_entry_score',
                'current': self.config.scoring.min_entry_score,
                'suggested': self.config.scoring.min_entry_score + 5,
                'reason': f'Win rate below 45% ({win_rate*100:.1f}%), increase quality threshold'
            })

        # Suggest decreasing threshold if win rate good but few trades
        elif win_rate > 0.60 and len(trades_to_analyze) < 30:
            suggestions['adjustments'].append({
                'parameter': 'min_entry_score',
                'current': self.config.scoring.min_entry_score,
                'suggested': max(70, self.config.scoring.min_entry_score - 3),
                'reason': f'High win rate ({win_rate*100:.1f}%) but low frequency, can take slightly more trades'
            })

        # Get feature importance
        if self.model is not None:
            importance = self.get_feature_importance()
            top_features = list(importance.keys())[:3]

            suggestions['top_predictive_features'] = top_features
            suggestions['feature_importance'] = importance

            logger.info(f"[ML] Top predictive features: {', '.join(top_features)}")

        return suggestions

    def should_retrain(self, total_trades: int) -> bool:
        """Check if model should be retrained"""

        if not self.training_enabled:
            return False

        if self.model is None and total_trades >= self.min_samples:
            return True  # Initial training

        retrain_interval = self.config.learning.get('ml_retrain_every_n_trades', 100)

        if total_trades - self.last_trained_count >= retrain_interval:
            return True

        return False

    def save_model(self):
        """Save model to disk (efficient pickle format)"""

        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

            with open(self.model_path, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'scaler': self.scaler,
                    'feature_names': self.feature_names,
                    'last_trained_count': self.last_trained_count,
                    'trained_at': datetime.now().isoformat()
                }, f)

            logger.info(f"[ML] Model saved to {self.model_path}")

        except Exception as e:
            logger.error(f"[ML] Error saving model: {e}")

    def load_model(self):
        """Load model from disk"""

        try:
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)
                self.model = data['model']
                self.scaler = data['scaler']
                self.feature_names = data['feature_names']
                self.last_trained_count = data.get('last_trained_count', 0)

            logger.info(f"[ML] Model loaded from {self.model_path}")
            logger.info(f"[ML] Last trained on {self.last_trained_count} trades")

            # Show feature importance
            importance = self.get_feature_importance()
            if importance:
                top_3 = list(importance.items())[:3]
                logger.info(f"[ML] Top features: {', '.join([f'{k} ({v:.3f})' for k, v in top_3])}")

        except Exception as e:
            logger.error(f"[ML] Error loading model: {e}")
            self.model = None

    def _get_hour_of_day(self, timestamp_ms: int) -> int:
        """Extract hour from timestamp (0-23 UTC)"""
        if timestamp_ms == 0:
            return 0
        return datetime.fromtimestamp(timestamp_ms / 1000).hour

    def _get_day_of_week(self, timestamp_ms: int) -> int:
        """Extract day of week from timestamp (0=Monday, 6=Sunday)"""
        if timestamp_ms == 0:
            return 0
        return datetime.fromtimestamp(timestamp_ms / 1000).weekday()

    def generate_training_report(self, historical_trades: List[Dict]) -> Dict:
        """Generate detailed training report for analysis"""

        if not historical_trades:
            return {'error': 'No trades to analyze'}

        wins = [t for t in historical_trades if t.get('pnl', 0) > 0]
        losses = [t for t in historical_trades if t.get('pnl', 0) <= 0]

        report = {
            'total_trades': len(historical_trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': f"{(len(wins)/len(historical_trades))*100:.1f}%",
            'avg_win': f"${np.mean([t['pnl'] for t in wins]):.2f}" if wins else "$0.00",
            'avg_loss': f"${np.mean([t['pnl'] for t in losses]):.2f}" if losses else "$0.00",
            'model_trained': self.model is not None,
            'model_path': self.model_path,
            'min_samples_required': self.min_samples,
            'ready_for_training': len(historical_trades) >= self.min_samples
        }

        if self.model is not None:
            # Add feature importance
            importance = self.get_feature_importance()
            report['feature_importance'] = importance
            report['top_5_features'] = list(importance.keys())[:5]

        return report
