"""
ML Optimizer for VWAP Strategy - Ensemble of 3 Models with Walk-Forward Analysis

Features:
1. Three models: Gradient Boosting, XGBoost, Random Forest
2. Walk-forward analysis to prevent look-ahead bias
3. Feature extraction from VWAP signals
4. Win probability prediction and trade filtering (target: 60%+ win rate)

Author: Claude Code
"""

import os
import pickle
import time
import warnings
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import xgboost as xgb

from src.utils.logger import setup_logger

warnings.filterwarnings('ignore')
logger = setup_logger(__name__)


class VWAPMLOptimizer:
    """
    ML-based trade filter for VWAP strategy using ensemble of 3 models.
    Uses walk-forward analysis to prevent look-ahead bias.
    """

    def __init__(self, min_win_probability: float = 0.60):
        """
        Initialize ML optimizer.

        Args:
            min_win_probability: Minimum win probability threshold (default: 0.60 for 60% win rate)
        """
        self.min_win_probability = min_win_probability
        self.models = {}
        self.scaler = StandardScaler()
        self.feature_names = [
            # VWAP features
            'vwap_distance_pct',
            'vwap_band_distance',
            'vwap_band_position',  # -2 to +2 (which band: -2σ, -1σ, VWAP, +1σ, +2σ)

            # S/R zone features
            'zone_strength',
            'zone_touches',
            'zone_distance_pct',
            'zone_type',  # 0=support, 1=resistance, 2=both

            # Market structure
            'price_structure',  # -1=bearish, 0=neutral, 1=bullish
            'htf_confluence',  # 0=no, 1=yes
            'local_sr_present',  # 0=no, 1=yes

            # Signal features
            'signal_type',  # 0=mean_reversion, 1=trend_continuation
            'confidence',
            'direction',  # -1=short, 1=long

            # Time features
            'hour_of_day',
            'day_of_week',

            # Market conditions
            'volatility',  # ATR-based
            'volume_ratio',  # current volume / avg volume
            'spread_bps',

            # Additional context
            'rapid_momentum',  # 0=no, 1=yes
            'regime_filter',  # -1=bearish, 0=neutral, 1=bullish
        ]

        self.model_path = 'data/vwap_ml_models.pkl'
        self.is_trained = False

    def extract_features(self, signal: Dict, market_data: Dict) -> np.ndarray:
        """
        Extract features from VWAP signal for ML prediction.

        Args:
            signal: VWAP signal dictionary
            market_data: Current market data (price, volume, etc.)

        Returns:
            Feature vector as numpy array
        """
        features = []

        # Convert TradeSignal dataclass to dict if needed
        if hasattr(signal, '__dataclass_fields__'):
            # It's a dataclass, convert to dict
            from dataclasses import asdict
            signal_dict = asdict(signal)
        else:
            # It's already a dict
            signal_dict = signal

        # VWAP features
        vwap_state = signal_dict.get('vwap_state', {})
        features.append(signal_dict.get('vwap_distance_pct', 0))
        features.append(signal_dict.get('vwap_band_distance', 0))

        # Calculate band position
        band_position = 0  # Default: at VWAP
        if 'vwap_band' in signal_dict:
            price = market_data.get('price', 0)
            vwap = vwap_state.get('vwap', price) if vwap_state else price
            sigma = vwap_state.get('sigma', 0) if vwap_state else 0

            if sigma > 0:
                band_position = (price - vwap) / sigma
                band_position = np.clip(band_position, -2.5, 2.5)

        features.append(band_position)

        # S/R zone features
        sr_zone = signal_dict.get('sr_zone', {})
        features.append(sr_zone.get('strength', 0) if sr_zone else 0)
        features.append(sr_zone.get('touches', 0) if sr_zone else 0)
        features.append(signal_dict.get('zone_distance_pct', 0))

        # Zone type encoding
        zone_type = sr_zone.get('zone_type', 'both') if sr_zone else 'both'
        zone_type_encoded = {'support': 0, 'resistance': 1, 'both': 2}.get(zone_type, 2)
        features.append(zone_type_encoded)

        # Market structure
        price_structure = signal_dict.get('price_structure', 'neutral')
        structure_encoded = {'bearish': -1, 'neutral': 0, 'bullish': 1}.get(price_structure, 0)
        features.append(structure_encoded)

        features.append(int(signal_dict.get('htf_confluence', False)))
        features.append(int(signal_dict.get('local_sr_present', False)))

        # Signal features
        signal_type = signal_dict.get('signal_type', 'mean_reversion')
        signal_type_encoded = 0 if signal_type == 'mean_reversion' else 1
        features.append(signal_type_encoded)

        features.append(signal_dict.get('confidence', 50) / 100.0)  # Normalize to 0-1

        direction = signal_dict.get('direction', 'LONG')
        direction_encoded = 1 if direction == 'LONG' else -1
        features.append(direction_encoded)

        # Time features
        timestamp = market_data.get('timestamp', time.time() * 1000)
        dt = datetime.fromtimestamp(timestamp / 1000)
        features.append(dt.hour)
        features.append(dt.weekday())

        # Market conditions
        features.append(market_data.get('volatility', 0))
        features.append(market_data.get('volume_ratio', 1.0))
        features.append(market_data.get('spread_bps', 0))

        # Additional context
        features.append(int(signal_dict.get('rapid_momentum', False)))

        regime = signal_dict.get('regime_filter', 'neutral')
        regime_encoded = {'bearish': -1, 'neutral': 0, 'bullish': 1}.get(regime, 0)
        features.append(regime_encoded)

        return np.array(features, dtype=float)

    def train_models(self, historical_signals: List[Dict], historical_outcomes: List[int]) -> Dict[str, float]:
        """
        Train all three models using walk-forward analysis.

        Args:
            historical_signals: List of signal dictionaries with 'signal' and 'market_data' keys
            historical_outcomes: List of outcomes (1 for win, 0 for loss)

        Returns:
            Dictionary with training metrics
        """
        if len(historical_signals) < 100:
            logger.warning(f"[VWAP-ML] Insufficient data: {len(historical_signals)}/100 minimum")
            return {}

        logger.info(f"[VWAP-ML] Training models on {len(historical_signals)} historical signals...")

        # Extract features
        X = []
        for sig in historical_signals:
            features = self.extract_features(sig['signal'], sig['market_data'])
            X.append(features)

        X = np.array(X)
        y = np.array(historical_outcomes)

        # Handle NaN/inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Walk-forward validation (5 folds)
        tscv = TimeSeriesSplit(n_splits=5)

        metrics = {
            'rf': {'accuracy': [], 'precision': [], 'recall': [], 'f1': []},
            'gb': {'accuracy': [], 'precision': [], 'recall': [], 'f1': []},
            'xgb': {'accuracy': [], 'precision': [], 'recall': [], 'f1': []}
        }

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X_scaled)):
            X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            # Skip if test set has only one class
            if len(np.unique(y_test)) < 2:
                continue

            # Train Random Forest
            rf = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42 + fold,
                n_jobs=-1
            )
            rf.fit(X_train, y_train)
            y_pred_rf = rf.predict(X_test)

            metrics['rf']['accuracy'].append(accuracy_score(y_test, y_pred_rf))
            metrics['rf']['precision'].append(precision_score(y_test, y_pred_rf, zero_division=0))
            metrics['rf']['recall'].append(recall_score(y_test, y_pred_rf, zero_division=0))
            metrics['rf']['f1'].append(f1_score(y_test, y_pred_rf, zero_division=0))

            # Train Gradient Boosting
            gb = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42 + fold
            )
            gb.fit(X_train, y_train)
            y_pred_gb = gb.predict(X_test)

            metrics['gb']['accuracy'].append(accuracy_score(y_test, y_pred_gb))
            metrics['gb']['precision'].append(precision_score(y_test, y_pred_gb, zero_division=0))
            metrics['gb']['recall'].append(recall_score(y_test, y_pred_gb, zero_division=0))
            metrics['gb']['f1'].append(f1_score(y_test, y_pred_gb, zero_division=0))

            # Train XGBoost
            xgb_model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                min_child_weight=2,
                random_state=42 + fold,
                n_jobs=-1,
                eval_metric='logloss'
            )
            xgb_model.fit(X_train, y_train)
            y_pred_xgb = xgb_model.predict(X_test)

            metrics['xgb']['accuracy'].append(accuracy_score(y_test, y_pred_xgb))
            metrics['xgb']['precision'].append(precision_score(y_test, y_pred_xgb, zero_division=0))
            metrics['xgb']['recall'].append(recall_score(y_test, y_pred_xgb, zero_division=0))
            metrics['xgb']['f1'].append(f1_score(y_test, y_pred_xgb, zero_division=0))

            logger.info(f"[VWAP-ML] Fold {fold+1}/5 - RF: {metrics['rf']['accuracy'][-1]:.3f}, "
                       f"GB: {metrics['gb']['accuracy'][-1]:.3f}, XGB: {metrics['xgb']['accuracy'][-1]:.3f}")

        # Train final models on all data
        logger.info("[VWAP-ML] Training final models on all data...")

        self.models['rf'] = RandomForestClassifier(
            n_estimators=100, max_depth=10, min_samples_split=5,
            min_samples_leaf=2, random_state=42, n_jobs=-1
        )
        self.models['rf'].fit(X_scaled, y)

        self.models['gb'] = GradientBoostingClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            min_samples_split=5, min_samples_leaf=2, random_state=42
        )
        self.models['gb'].fit(X_scaled, y)

        self.models['xgb'] = xgb.XGBClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            min_child_weight=2, random_state=42, n_jobs=-1, eval_metric='logloss'
        )
        self.models['xgb'].fit(X_scaled, y)

        self.is_trained = True

        # Calculate average metrics
        avg_metrics = {}
        for model_name in ['rf', 'gb', 'xgb']:
            avg_metrics[model_name] = {
                'accuracy': np.mean(metrics[model_name]['accuracy']),
                'precision': np.mean(metrics[model_name]['precision']),
                'recall': np.mean(metrics[model_name]['recall']),
                'f1': np.mean(metrics[model_name]['f1'])
            }

        logger.info("[VWAP-ML] Training complete!")
        logger.info(f"  Random Forest   - Acc: {avg_metrics['rf']['accuracy']:.3f}, "
                   f"Prec: {avg_metrics['rf']['precision']:.3f}, "
                   f"Rec: {avg_metrics['rf']['recall']:.3f}, F1: {avg_metrics['rf']['f1']:.3f}")
        logger.info(f"  Gradient Boost  - Acc: {avg_metrics['gb']['accuracy']:.3f}, "
                   f"Prec: {avg_metrics['gb']['precision']:.3f}, "
                   f"Rec: {avg_metrics['gb']['recall']:.3f}, F1: {avg_metrics['gb']['f1']:.3f}")
        logger.info(f"  XGBoost         - Acc: {avg_metrics['xgb']['accuracy']:.3f}, "
                   f"Prec: {avg_metrics['xgb']['precision']:.3f}, "
                   f"Rec: {avg_metrics['xgb']['recall']:.3f}, F1: {avg_metrics['xgb']['f1']:.3f}")

        # Save models
        self.save_models()

        return avg_metrics

    def predict_win_probability(self, signal: Dict, market_data: Dict) -> Tuple[float, Dict[str, float]]:
        """
        Predict win probability using ensemble of all three models.

        Args:
            signal: VWAP signal dictionary
            market_data: Current market data

        Returns:
            Tuple of (ensemble_probability, individual_probabilities)
        """
        if not self.is_trained:
            logger.warning("[VWAP-ML] Models not trained, returning neutral probability")
            return 0.5, {'rf': 0.5, 'gb': 0.5, 'xgb': 0.5}

        # Extract features
        features = self.extract_features(signal, market_data)
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
        features_scaled = self.scaler.transform(features.reshape(1, -1))

        # Get probabilities from each model
        prob_rf = self.models['rf'].predict_proba(features_scaled)[0][1]
        prob_gb = self.models['gb'].predict_proba(features_scaled)[0][1]
        prob_xgb = self.models['xgb'].predict_proba(features_scaled)[0][1]

        # Ensemble: weighted average (XGBoost gets slightly higher weight)
        ensemble_prob = (prob_rf * 0.3 + prob_gb * 0.3 + prob_xgb * 0.4)

        individual_probs = {
            'rf': prob_rf,
            'gb': prob_gb,
            'xgb': prob_xgb
        }

        return ensemble_prob, individual_probs

    def should_take_trade(self, signal: Dict, market_data: Dict) -> Tuple[bool, float, Dict]:
        """
        Determine if trade should be taken based on ML prediction.

        Args:
            signal: VWAP signal dictionary
            market_data: Current market data

        Returns:
            Tuple of (should_take, win_probability, model_details)
        """
        win_prob, individual_probs = self.predict_win_probability(signal, market_data)

        should_take = win_prob >= self.min_win_probability

        details = {
            'ensemble_probability': win_prob,
            'individual_probabilities': individual_probs,
            'threshold': self.min_win_probability,
            'decision': 'TAKE' if should_take else 'SKIP'
        }

        return should_take, win_prob, details

    def save_models(self):
        """Save trained models and scaler to disk"""
        os.makedirs('data', exist_ok=True)

        model_data = {
            'models': self.models,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'min_win_probability': self.min_win_probability,
            'timestamp': time.time()
        }

        with open(self.model_path, 'wb') as f:
            pickle.dump(model_data, f)

        logger.info(f"[VWAP-ML] Models saved to {self.model_path}")

    def load_models(self) -> bool:
        """Load trained models from disk"""
        if not os.path.exists(self.model_path):
            logger.warning(f"[VWAP-ML] Model file not found: {self.model_path}")
            return False

        try:
            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)

            self.models = model_data['models']
            self.scaler = model_data['scaler']
            self.feature_names = model_data['feature_names']
            self.min_win_probability = model_data.get('min_win_probability', 0.60)
            self.is_trained = True

            logger.info(f"[VWAP-ML] Models loaded from {self.model_path}")
            return True
        except Exception as e:
            logger.error(f"[VWAP-ML] Error loading models: {e}")
            return False

    def get_feature_importance(self) -> Dict[str, Dict[str, float]]:
        """Get feature importance from all models"""
        if not self.is_trained:
            return {}

        importance = {}

        # Random Forest importance
        rf_importance = self.models['rf'].feature_importances_
        importance['rf'] = dict(zip(self.feature_names, rf_importance))

        # Gradient Boosting importance
        gb_importance = self.models['gb'].feature_importances_
        importance['gb'] = dict(zip(self.feature_names, gb_importance))

        # XGBoost importance
        xgb_importance = self.models['xgb'].feature_importances_
        importance['xgb'] = dict(zip(self.feature_names, xgb_importance))

        return importance
