"""
ML Strategy Filter
==================

Integrates trained ML model into VWAP + S/R strategy to filter trade signals.

Usage in strategy:
    from ml_strategy_filter import MLFilter

    ml_filter = MLFilter('models/vwap_ml_model.pkl')

    # Before taking a trade
    features = extract_features(df, zone, vwap_bands)
    result = ml_filter.should_take_trade(features)

    if result['should_trade']:
        execute_trade()
"""

import pickle
import pandas as pd
import numpy as np
from typing import Dict, Optional
from pathlib import Path
from dataclasses import dataclass


@dataclass
class MLPrediction:
    """ML prediction result"""
    should_trade: bool
    reason: str
    confidence_score: float
    success_probability: float


class MLFilter:
    """ML-based trade filter for VWAP + S/R strategy"""

    def __init__(self, model_path: str, enabled: bool = True):
        """
        Initialize ML filter

        Args:
            model_path: Path to trained model (.pkl file)
            enabled: Whether ML filter is active (False = pass all trades)
        """
        self.model_path = model_path
        self.enabled = enabled
        self.model = None
        self.scaler = None
        self.feature_names = []
        self.min_confidence = 0.65
        self.is_loaded = False

        if enabled:
            self._load_model()

    def _load_model(self) -> None:
        """Load trained model from file"""
        try:
            model_file = Path(self.model_path)
            if not model_file.exists():
                print(f"⚠️ ML model not found at {self.model_path}")
                print(f"   ML filter disabled. Train model first:")
                print(f"   python train_ml_model.py --input data.csv --output {self.model_path}")
                self.enabled = False
                return

            with open(self.model_path, 'rb') as f:
                model_state = pickle.load(f)

            self.model = model_state['model']
            self.scaler = model_state['scaler']
            self.feature_names = model_state['feature_names']
            self.min_confidence = model_state.get('min_confidence', 0.65)

            self.is_loaded = True
            print(f"✅ ML model loaded from {self.model_path}")
            print(f"   - Features: {len(self.feature_names)}")
            print(f"   - Min confidence: {self.min_confidence:.1%}")

        except Exception as e:
            print(f"❌ Error loading ML model: {e}")
            self.enabled = False

    def should_take_trade(self, features: pd.Series) -> MLPrediction:
        """
        Determine if trade should be taken based on ML prediction

        Args:
            features: Feature Series with same columns as training data

        Returns:
            MLPrediction with decision and reasoning
        """
        # If ML filter is disabled, approve all trades
        if not self.enabled or not self.is_loaded:
            return MLPrediction(
                should_trade=True,
                reason="ML filter disabled",
                confidence_score=1.0,
                success_probability=0.5
            )

        try:
            # Prepare features (handle missing features gracefully)
            feature_values = []
            missing_features = []

            for feature_name in self.feature_names:
                if feature_name in features.index:
                    val = features[feature_name]
                    # Handle NaN and inf
                    if pd.isna(val) or np.isinf(val):
                        val = 0.0
                    feature_values.append(val)
                else:
                    missing_features.append(feature_name)
                    feature_values.append(0.0)  # Default to 0

            if missing_features:
                print(f"⚠️ Missing features (defaulting to 0): {missing_features[:5]}")

            # Reshape and scale
            X = np.array(feature_values).reshape(1, -1)
            X_scaled = self.scaler.transform(X)

            # Predict
            proba = self.model.predict_proba(X_scaled)[0]
            success_prob = proba[1]  # Probability of winning trade
            confidence = max(proba)  # Model confidence (max probability)

            # Decision logic
            # Philosophy: Conservative filtering to improve win rate
            # - success_prob >= 30%: With 2:1 R:R, this is breakeven
            # - confidence >= min_confidence: Model is confident in prediction
            should_trade = (
                success_prob >= 0.30 and
                confidence >= self.min_confidence
            )

            # Generate reason
            if should_trade:
                reason = f"ML approved (prob={success_prob:.1%}, conf={confidence:.1%})"
            else:
                if success_prob < 0.30:
                    reason = f"Low success probability: {success_prob:.1%} < 30%"
                elif confidence < self.min_confidence:
                    reason = f"Low confidence: {confidence:.1%} < {self.min_confidence:.1%}"
                else:
                    reason = "ML rejected trade"

            return MLPrediction(
                should_trade=should_trade,
                reason=reason,
                confidence_score=confidence,
                success_probability=success_prob
            )

        except Exception as e:
            print(f"❌ ML prediction error: {e}")
            # On error, be conservative and reject trade
            return MLPrediction(
                should_trade=False,
                reason=f"ML error: {str(e)}",
                confidence_score=0.0,
                success_probability=0.5
            )

    def extract_features_from_signal(
        self,
        df: pd.DataFrame,
        zone,
        vwap_bands,
        signal_type: str,
        current_price: float
    ) -> pd.Series:
        """
        Extract ML features from trade signal context

        This mirrors the feature extraction in ml_training_data_collector.py

        Args:
            df: DataFrame with market data (1m timeframe)
            zone: SupportResistanceZone object
            vwap_bands: VWAPBands object
            signal_type: 'LONG' or 'SHORT'
            current_price: Current market price

        Returns:
            Feature Series ready for ML prediction
        """
        features = {}
        current_time = pd.to_datetime(df.iloc[-1]['timestamp'])

        # ============================================================
        # VWAP FEATURES (15 features)
        # ============================================================
        vwap = vwap_bands.vwap
        std = vwap_bands.std_dev

        # Distance from VWAP
        features['vwap_distance'] = (current_price - vwap) / vwap

        # Band position (0 = lower band, 0.5 = VWAP, 1 = upper band)
        band_range = (vwap_bands.upper_2std - vwap_bands.lower_2std)
        if band_range > 0:
            features['vwap_band_position'] = (current_price - vwap_bands.lower_2std) / band_range
        else:
            features['vwap_band_position'] = 0.5

        # Band width (volatility)
        features['vwap_band_width'] = band_range / vwap

        # Individual band distances
        features['distance_to_upper_2std'] = (vwap_bands.upper_2std - current_price) / current_price
        features['distance_to_lower_2std'] = (current_price - vwap_bands.lower_2std) / current_price
        features['distance_to_upper_3std'] = (vwap_bands.upper_3std - current_price) / current_price
        features['distance_to_lower_3std'] = (current_price - vwap_bands.lower_3std) / current_price

        # VWAP slope (trend)
        if len(df) >= 20:
            vwap_20_ago = df.iloc[-20]['close']  # Approximate
            features['vwap_slope'] = (vwap - vwap_20_ago) / vwap_20_ago
        else:
            features['vwap_slope'] = 0.0

        # Price momentum relative to VWAP
        if len(df) >= 5:
            price_5_ago = df.iloc[-5]['close']
            features['price_momentum_5'] = (current_price - price_5_ago) / price_5_ago
        else:
            features['price_momentum_5'] = 0.0

        # Volatility metrics
        if len(df) >= 20:
            volatility_20 = df['close'].pct_change().iloc[-20:].std()
            features['volatility_20'] = volatility_20
        else:
            features['volatility_20'] = 0.01

        # VWAP touches
        if len(df) >= 50:
            recent_df = df.iloc[-50:]
            touches_upper = ((recent_df['high'] >= vwap_bands.upper_2std) &
                           (recent_df['close'] < vwap_bands.upper_2std)).sum()
            touches_lower = ((recent_df['low'] <= vwap_bands.lower_2std) &
                           (recent_df['close'] > vwap_bands.lower_2std)).sum()
            features['vwap_upper_touches'] = touches_upper
            features['vwap_lower_touches'] = touches_lower
        else:
            features['vwap_upper_touches'] = 0
            features['vwap_lower_touches'] = 0

        # VWAP mean reversion strength
        features['vwap_reversion_score'] = abs(features['vwap_distance']) * (1 - abs(features['vwap_slope']))

        # Current candle position
        current_candle = df.iloc[-1]
        features['candle_body_size'] = abs(current_candle['close'] - current_candle['open']) / current_candle['open']
        features['candle_wick_ratio'] = (
            (current_candle['high'] - current_candle['low'] - abs(current_candle['close'] - current_candle['open']))
            / (current_candle['high'] - current_candle['low'] + 1e-10)
        )

        # ============================================================
        # S/R ZONE FEATURES (20 features)
        # ============================================================
        features['zone_strength'] = zone.strength
        features['zone_touches'] = zone.touches
        features['zone_bounces'] = zone.bounces
        features['zone_breakout_count'] = zone.breakout_count
        features['zone_liquidity_grabs'] = zone.liquidity_grabs
        features['zone_false_breakout_count'] = zone.false_breakout_count

        # Zone age (in number of candles)
        zone_age = (current_time - zone.created_at).total_seconds() / 60  # Minutes
        features['zone_age_minutes'] = zone_age

        # Zone quality metrics
        if zone.touches > 0:
            features['zone_bounce_rate'] = zone.bounces / zone.touches
            features['zone_false_breakout_rate'] = zone.false_breakout_count / zone.touches
        else:
            features['zone_bounce_rate'] = 0.0
            features['zone_false_breakout_rate'] = 0.0

        # Zone width
        features['zone_width'] = (zone.upper - zone.lower) / zone.lower

        # Distance from current price to zone
        if signal_type == 'LONG':
            features['distance_to_zone'] = (current_price - zone.upper) / current_price
            features['zone_edge_distance'] = (current_price - zone.lower) / current_price
        else:
            features['distance_to_zone'] = (zone.lower - current_price) / current_price
            features['zone_edge_distance'] = (zone.upper - current_price) / current_price

        # Zone type
        features['is_support_zone'] = 1 if zone.zone_type == 'support' else 0
        features['is_resistance_zone'] = 1 if zone.zone_type == 'resistance' else 0

        # Recent zone activity
        recent_interactions = zone.touches + zone.bounces + zone.liquidity_grabs
        features['zone_recent_activity'] = recent_interactions

        # Zone invalidation status
        features['zone_is_invalidated'] = 1 if zone.invalidated else 0
        features['zone_invalidation_count'] = zone.invalidation_count

        # Zone confidence (higher = more reliable)
        zone_confidence = (
            (zone.bounces * 2.0) +  # Bounces are strong signals
            (zone.liquidity_grabs * 1.5) +  # Liquidity grabs show traps
            (zone.touches * 0.5) -  # More touches = tested more
            (zone.breakout_count * 1.0) -  # Breakouts reduce confidence
            (zone.false_breakout_count * 0.5)  # False breakouts increase confidence
        )
        features['zone_confidence'] = max(0, zone_confidence)

        # Zone alignment with VWAP
        zone_mid = (zone.upper + zone.lower) / 2
        features['zone_vwap_alignment'] = (zone_mid - vwap) / vwap

        # ============================================================
        # VWAP DYNAMIC S/R FEATURES (7 features)
        # ============================================================
        # These represent VWAP bands as dynamic support/resistance

        # Which VWAP band is closest?
        bands = {
            'lower_3std': vwap_bands.lower_3std,
            'lower_2std': vwap_bands.lower_2std,
            'vwap': vwap,
            'upper_2std': vwap_bands.upper_2std,
            'upper_3std': vwap_bands.upper_3std
        }

        closest_band = min(bands.items(), key=lambda x: abs(x[1] - current_price))
        features['closest_vwap_band'] = list(bands.keys()).index(closest_band[0]) / 4.0  # Normalize 0-1

        # Distance to closest band
        features['distance_to_closest_band'] = abs(closest_band[1] - current_price) / current_price

        # Is price between VWAP and zone?
        if signal_type == 'LONG':
            between = (current_price >= vwap) and (current_price <= zone.lower)
        else:
            between = (current_price <= vwap) and (current_price >= zone.upper)
        features['price_between_vwap_zone'] = 1 if between else 0

        # VWAP zone alignment score
        # Positive = zone and VWAP agree on direction
        if signal_type == 'LONG':
            vwap_signal = -1 if current_price < vwap else 1
            zone_signal = 1  # Support zone
            features['vwap_zone_alignment'] = 1 if vwap_signal == zone_signal else -1
        else:
            vwap_signal = 1 if current_price > vwap else -1
            zone_signal = -1  # Resistance zone
            features['vwap_zone_alignment'] = 1 if vwap_signal == zone_signal else -1

        # Price deviation from VWAP in standard deviations
        features['vwap_std_distance'] = abs(current_price - vwap) / (std + 1e-10)

        # Confluence score (VWAP band + zone alignment)
        confluence = 0.0
        if signal_type == 'LONG':
            if current_price < vwap:  # Price below VWAP (oversold)
                confluence += 1.0
            if zone.zone_type == 'support':  # Support zone below
                confluence += 1.0
            if current_price < vwap_bands.lower_2std:  # Price at lower band
                confluence += 0.5
        else:
            if current_price > vwap:  # Price above VWAP (overbought)
                confluence += 1.0
            if zone.zone_type == 'resistance':  # Resistance zone above
                confluence += 1.0
            if current_price > vwap_bands.upper_2std:  # Price at upper band
                confluence += 0.5
        features['confluence_score'] = confluence

        # ============================================================
        # TEMPORAL FEATURES (8 features)
        # ============================================================
        features['hour'] = current_time.hour
        features['day_of_week'] = current_time.dayofweek

        # Trading sessions
        features['is_asian_session'] = 1 if (0 <= current_time.hour < 8) else 0
        features['is_london_session'] = 1 if (8 <= current_time.hour < 16) else 0
        features['is_ny_session'] = 1 if (13 <= current_time.hour < 21) else 0
        features['is_overlap'] = 1 if (13 <= current_time.hour < 16) else 0
        features['is_weekend'] = 1 if current_time.dayofweek >= 5 else 0

        # Weekend flag
        features['is_monday'] = 1 if current_time.dayofweek == 0 else 0

        # ============================================================
        # MARKET REGIME FEATURES (5 features)
        # ============================================================
        # These require more complex calculations - simplified here
        # In production, these should match your actual regime detection logic

        if len(df) >= 100:
            sma_100 = df['close'].iloc[-100:].mean()
            features['price_vs_sma100'] = (current_price - sma_100) / sma_100

            # Trend strength (simplified)
            returns = df['close'].pct_change().iloc[-20:]
            trend = returns.mean()
            features['trend_strength'] = trend

            # Volatility regime
            volatility = returns.std()
            volatility_percentile = (volatility - returns.std().min()) / (returns.std().max() - returns.std().min() + 1e-10)
            features['volatility_percentile'] = volatility_percentile

            # Market state
            if abs(trend) < 0.0005:
                features['market_state'] = 0.0  # Ranging
            elif trend > 0:
                features['market_state'] = 1.0  # Uptrend
            else:
                features['market_state'] = -1.0  # Downtrend

            # ADX-like (simplified)
            price_range = df['high'].iloc[-20:] - df['low'].iloc[-20:]
            features['price_range_avg'] = price_range.mean() / current_price

        else:
            features['price_vs_sma100'] = 0.0
            features['trend_strength'] = 0.0
            features['volatility_percentile'] = 0.5
            features['market_state'] = 0.0
            features['price_range_avg'] = 0.01

        # ============================================================
        # SIGNAL TYPE
        # ============================================================
        features['is_long'] = 1 if signal_type == 'LONG' else 0

        return pd.Series(features)

    def get_model_info(self) -> Dict:
        """Get information about loaded model"""
        if not self.is_loaded:
            return {
                'loaded': False,
                'enabled': self.enabled
            }

        return {
            'loaded': True,
            'enabled': self.enabled,
            'model_path': self.model_path,
            'n_features': len(self.feature_names),
            'min_confidence': self.min_confidence,
            'model_type': type(self.model).__name__
        }
