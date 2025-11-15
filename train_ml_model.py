"""
ML Model Training Script
========================

Trains a RandomForest classifier on backtest data collected by ml_training_data_collector.py

Usage:
    python train_ml_model.py --input trades_with_features.csv --output models/vwap_ml_model.pkl

Features:
- Walk-forward validation (realistic performance estimation)
- RandomForest with optimized hyperparameters
- Feature importance analysis
- Performance metrics (precision, recall, win rate improvement)
- Model persistence for live trading
"""

import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from typing import Dict, Tuple
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
import argparse


class VWAPMLTrainer:
    """Train and evaluate ML model for VWAP + S/R strategy"""

    def __init__(self, min_confidence: float = 0.65):
        """
        Initialize trainer

        Args:
            min_confidence: Minimum confidence threshold for trade approval (0-1)
        """
        self.min_confidence = min_confidence
        self.model = None
        self.scaler = None
        self.feature_names = []

    def load_data(self, filepath: str) -> pd.DataFrame:
        """Load training data from CSV"""
        print(f"\n📂 Loading data from {filepath}...")
        df = pd.read_csv(filepath)
        print(f"   Loaded {len(df)} trades")

        # Show win rate breakdown
        win_rate = df['is_win'].mean()
        print(f"   Overall win rate: {win_rate:.1%}")
        print(f"   - Wins: {df['is_win'].sum()}")
        print(f"   - Losses: {(~df['is_win']).sum()}")

        return df

    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Extract features and target from dataframe

        Returns:
            (X, y): Feature DataFrame and target Series
        """
        print("\n🔧 Preparing features...")

        # Define feature columns (all numeric columns except metadata and target)
        exclude_cols = [
            # Timestamps and IDs
            'timestamp', 'entry_time', 'exit_time', 'datetime',
            'symbol', 'position_id',
            # Prices (outcomes, not features)
            'entry_price', 'exit_price',
            # Outcomes (target variables and results)
            'pnl', 'pnl_pct', 'is_win', 'exit_reason',
            # Trade metadata (not predictive features)
            'duration_minutes', 'quantity',
            'stop_loss', 'take_profit',
            'entry_fee', 'exit_fee', 'total_fees',
            # String columns (encoded separately)
            'signal_type', 'direction', 'signal', 'zone_type',
            'market_regime', 'short_term_regime', 'price_structure', 'momentum_direction'
        ]

        feature_cols = [col for col in df.columns if col not in exclude_cols]

        # Encode signal_type or direction as binary feature
        if 'signal_type' in df.columns:
            df['is_long'] = (df['signal_type'] == 'LONG').astype(int)
        elif 'direction' in df.columns:
            df['is_long'] = (df['direction'] == 'LONG').astype(int)
        else:
            df['is_long'] = 1  # Default to long if neither exists

        feature_cols.append('is_long')

        X = df[feature_cols].copy()
        y = df['is_win'].astype(int)

        # Handle missing values
        X = X.fillna(0)

        # Remove infinite values
        X = X.replace([np.inf, -np.inf], 0)

        self.feature_names = list(X.columns)
        print(f"   Selected {len(self.feature_names)} features")

        return X, y

    def walk_forward_validation(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        n_splits: int = 5
    ) -> Dict:
        """
        Perform walk-forward validation

        This simulates realistic deployment:
        - Train on past data
        - Test on future data
        - Roll forward through time

        Args:
            X: Features
            y: Target
            n_splits: Number of time-based splits

        Returns:
            Validation metrics
        """
        print(f"\n🔄 Running walk-forward validation ({n_splits} splits)...")

        # Split data into chunks
        split_size = len(X) // (n_splits + 1)

        results = []

        for i in range(n_splits):
            # Training window: all data up to current split
            train_end = split_size * (i + 1)
            train_idx = slice(0, train_end)

            # Test window: next chunk
            test_start = train_end
            test_end = test_start + split_size
            test_idx = slice(test_start, test_end)

            X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
            X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]

            print(f"\n   Split {i+1}/{n_splits}:")
            print(f"   - Train: {len(X_train)} samples (index 0-{train_end})")
            print(f"   - Test: {len(X_test)} samples (index {test_start}-{test_end})")

            # Train model
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            model = RandomForestClassifier(
                n_estimators=300,
                max_depth=8,
                min_samples_split=20,
                min_samples_leaf=10,
                max_features='sqrt',
                class_weight='balanced',
                n_jobs=-1,
                random_state=42
            )

            model.fit(X_train_scaled, y_train)

            # Predict with confidence filtering
            y_pred_proba = model.predict_proba(X_test_scaled)

            # Apply confidence threshold
            confident_mask = np.max(y_pred_proba, axis=1) >= self.min_confidence
            success_prob = y_pred_proba[:, 1]

            # Apply both filters
            trade_mask = (success_prob >= 0.30) & confident_mask

            # Calculate metrics
            if trade_mask.sum() > 0:
                filtered_accuracy = y_test[trade_mask].mean()
                trade_frequency = trade_mask.mean()

                results.append({
                    'split': i + 1,
                    'filtered_win_rate': filtered_accuracy,
                    'trade_frequency': trade_frequency,
                    'n_trades': trade_mask.sum(),
                    'baseline_win_rate': y_test.mean()
                })

                print(f"   - Baseline win rate: {y_test.mean():.1%}")
                print(f"   - ML filtered win rate: {filtered_accuracy:.1%}")
                print(f"   - Trade frequency: {trade_frequency:.1%} ({trade_mask.sum()}/{len(y_test)} trades)")
                print(f"   - Improvement: {(filtered_accuracy - y_test.mean()):.1%}")
            else:
                print(f"   - ⚠️ No trades passed ML filter in this split")

        # Aggregate results
        if results:
            avg_baseline = np.mean([r['baseline_win_rate'] for r in results])
            avg_filtered = np.mean([r['filtered_win_rate'] for r in results])
            avg_frequency = np.mean([r['trade_frequency'] for r in results])

            return {
                'avg_baseline_win_rate': avg_baseline,
                'avg_filtered_win_rate': avg_filtered,
                'avg_improvement': avg_filtered - avg_baseline,
                'avg_trade_frequency': avg_frequency,
                'splits': results
            }
        else:
            return {
                'avg_baseline_win_rate': 0,
                'avg_filtered_win_rate': 0,
                'avg_improvement': 0,
                'avg_trade_frequency': 0,
                'splits': []
            }

    def train_final_model(self, X: pd.DataFrame, y: pd.Series) -> Dict:
        """
        Train final model on all data

        Args:
            X: Features
            y: Target

        Returns:
            Training metrics
        """
        print("\n🎯 Training final model on full dataset...")

        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Train RandomForest
        self.model = RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_split=20,
            min_samples_leaf=10,
            max_features='sqrt',
            class_weight='balanced',
            n_jobs=-1,
            random_state=42
        )

        self.model.fit(X_scaled, y)

        # Calculate training metrics
        y_pred = self.model.predict(X_scaled)
        y_pred_proba = self.model.predict_proba(X_scaled)

        accuracy = (y_pred == y).mean()

        try:
            auc = roc_auc_score(y, y_pred_proba[:, 1])
        except:
            auc = 0.5

        print(f"   ✓ Training complete")
        print(f"   - Accuracy: {accuracy:.1%}")
        print(f"   - AUC: {auc:.3f}")

        return {
            'accuracy': accuracy,
            'auc': auc,
            'n_samples': len(X),
            'n_features': X.shape[1]
        }

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get feature importance from trained model"""
        if self.model is None:
            return pd.DataFrame()

        importance = self.model.feature_importances_

        feature_imp = pd.DataFrame({
            'feature': self.feature_names,
            'importance': importance
        }).sort_values('importance', ascending=False)

        return feature_imp.head(top_n)

    def save_model(self, filepath: str) -> None:
        """Save trained model to file"""
        print(f"\n💾 Saving model to {filepath}...")

        # Create directory if needed
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        # Save model state
        model_state = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'min_confidence': self.min_confidence,
            'model_type': 'RandomForest'
        }

        with open(filepath, 'wb') as f:
            pickle.dump(model_state, f)

        print(f"   ✓ Model saved successfully")

    def predict(self, features: pd.Series) -> Dict:
        """
        Predict trade quality for new trade

        Args:
            features: Feature Series with same columns as training data

        Returns:
            Prediction result with confidence
        """
        if self.model is None or self.scaler is None:
            return {
                'should_trade': False,
                'reason': 'Model not trained',
                'confidence_score': 0.0,
                'success_probability': 0.5
            }

        try:
            # Prepare features
            X = features[self.feature_names].values.reshape(1, -1)
            X = np.nan_to_num(X, nan=0.0)

            # Scale
            X_scaled = self.scaler.transform(X)

            # Predict
            proba = self.model.predict_proba(X_scaled)[0]
            success_prob = proba[1]
            confidence = max(proba)

            # Decision logic
            should_trade = (
                success_prob >= 0.30 and
                confidence >= self.min_confidence
            )

            reason = "Trade approved by ML"
            if not should_trade:
                if success_prob < 0.30:
                    reason = f"Success probability too low: {success_prob:.1%}"
                elif confidence < self.min_confidence:
                    reason = f"Confidence too low: {confidence:.1%}"

            return {
                'should_trade': should_trade,
                'reason': reason,
                'confidence_score': confidence,
                'success_probability': success_prob
            }

        except Exception as e:
            return {
                'should_trade': False,
                'reason': f'Prediction error: {str(e)}',
                'confidence_score': 0.0,
                'success_probability': 0.5
            }


def main():
    parser = argparse.ArgumentParser(description='Train ML model for VWAP strategy')
    parser.add_argument('--input', type=str, required=True, help='Input CSV file with training data')
    parser.add_argument('--output', type=str, default='models/vwap_ml_model.pkl', help='Output model file')
    parser.add_argument('--min-confidence', type=float, default=0.65, help='Minimum confidence threshold')
    parser.add_argument('--n-splits', type=int, default=5, help='Number of walk-forward validation splits')

    args = parser.parse_args()

    print("=" * 70)
    print("ML Model Training for VWAP + S/R Strategy")
    print("=" * 70)

    # Initialize trainer
    trainer = VWAPMLTrainer(min_confidence=args.min_confidence)

    # Load data
    df = trainer.load_data(args.input)

    # Prepare features
    X, y = trainer.prepare_features(df)

    # Walk-forward validation
    val_results = trainer.walk_forward_validation(X, y, n_splits=args.n_splits)

    print("\n" + "=" * 70)
    print("WALK-FORWARD VALIDATION RESULTS")
    print("=" * 70)
    print(f"Baseline win rate:     {val_results['avg_baseline_win_rate']:.1%}")
    print(f"ML-filtered win rate:  {val_results['avg_filtered_win_rate']:.1%}")
    print(f"Improvement:           {val_results['avg_improvement']:+.1%}")
    print(f"Trade frequency:       {val_results['avg_trade_frequency']:.1%}")
    print()

    if val_results['avg_improvement'] > 0:
        print("✅ ML filter improves performance!")
    else:
        print("⚠️ ML filter does not improve performance. Consider:")
        print("   - Collecting more training data")
        print("   - Adjusting confidence thresholds")
        print("   - Re-evaluating feature engineering")

    # Train final model
    train_metrics = trainer.train_final_model(X, y)

    # Feature importance
    print("\n" + "=" * 70)
    print("TOP 20 FEATURE IMPORTANCE")
    print("=" * 70)
    feature_imp = trainer.get_feature_importance(top_n=20)
    for idx, row in feature_imp.iterrows():
        print(f"{row['feature']:40s} {row['importance']:.4f}")

    # Save model
    trainer.save_model(args.output)

    print("\n" + "=" * 70)
    print("✅ TRAINING COMPLETE")
    print("=" * 70)
    print(f"Model saved to: {args.output}")
    print(f"\nNext steps:")
    print(f"1. Review feature importance above")
    print(f"2. Integrate model into strategy using ml_strategy_filter.py")
    print(f"3. Run backtest with ML filter enabled")
    print(f"4. Compare performance: baseline vs ML-enhanced")
    print()


if __name__ == '__main__':
    main()
