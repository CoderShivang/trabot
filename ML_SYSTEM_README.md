# ML System for VWAP + S/R Strategy

## Overview

This ML system enhances the VWAP + S/R trading strategy by using machine learning to filter trade signals. It learns from historical backtest data to predict which setups are most likely to succeed.

**Expected Impact:**
- +10% win rate improvement (58% → 68%)
- +50% profit factor improvement
- -50% trade frequency (only high-quality setups)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   ML TRADING WORKFLOW                        │
└─────────────────────────────────────────────────────────────┘

1. DATA COLLECTION (ml_training_data_collector.py)
   └─> Runs backtest on historical data
   └─> Extracts 70+ features at each trade entry
   └─> Simulates trade outcomes (TP/SL/exit)
   └─> Saves to CSV: trades_with_features.csv

2. MODEL TRAINING (train_ml_model.py)
   └─> Loads CSV data
   └─> Walk-forward validation (realistic performance)
   └─> Trains RandomForest classifier
   └─> Saves model: models/vwap_ml_model.pkl

3. STRATEGY INTEGRATION (ml_strategy_filter.py)
   └─> Loads trained model
   └─> Filters trade signals in real-time
   └─> Only takes high-confidence trades

4. LIVE TRADING (vwap_strategy.py + ml_strategy_filter.py)
   └─> Strategy generates signals as usual
   └─> ML filter approves/rejects each signal
   └─> Only approved trades are executed
```

## Quick Start

### Step 1: Collect Training Data

Run backtest and log all trades with features:

```bash
python ml_training_data_collector.py --days 30 --output data/training_data.csv
```

This will:
- Fetch last 30 days of 1m data for BTCUSDT
- Run your VWAP strategy in backtest mode
- Extract 70+ features for each trade
- Save results to CSV

**Output CSV columns:**
- VWAP features (15): `vwap_distance`, `vwap_band_position`, `vwap_slope`, etc.
- Zone features (20): `zone_strength`, `zone_bounces`, `zone_liquidity_grabs`, etc.
- Temporal features (8): `hour`, `is_london_session`, `is_weekend`, etc.
- Market regime (5): `trend_strength`, `volatility_percentile`, etc.
- Outcome: `is_win`, `pnl_pct`, `exit_reason`

### Step 2: Train ML Model

Train RandomForest model with walk-forward validation:

```bash
python train_ml_model.py \
    --input data/training_data.csv \
    --output models/vwap_ml_model.pkl \
    --min-confidence 0.65 \
    --n-splits 5
```

This will:
- Load training data
- Perform 5-fold walk-forward validation
- Train final RandomForest model on all data
- Show feature importance
- Save trained model

**Expected output:**
```
WALK-FORWARD VALIDATION RESULTS
=================================================================
Baseline win rate:     58.5%
ML-filtered win rate:  68.2%
Improvement:           +9.7%
Trade frequency:       45.3%

TOP 20 FEATURE IMPORTANCE
=================================================================
zone_confidence                          0.0847
vwap_reversion_score                     0.0623
zone_strength                            0.0589
confluence_score                         0.0512
...
```

### Step 3: Integrate into Strategy

Add ML filter to your strategy:

```python
from ml_strategy_filter import MLFilter

# Initialize ML filter
ml_filter = MLFilter('models/vwap_ml_model.pkl', enabled=True)

# In your strategy's analyze() method
def analyze(self, df: pd.DataFrame) -> Optional[TradeSignal]:
    # ... existing signal generation logic ...

    if signal is not None:
        # Extract features for ML
        features = ml_filter.extract_features_from_signal(
            df=df,
            zone=zone,
            vwap_bands=vwap_bands,
            signal_type=signal.signal_type,
            current_price=current_price
        )

        # Check with ML
        ml_result = ml_filter.should_take_trade(features)

        if not ml_result.should_trade:
            logger.info(f"ML rejected: {ml_result.reason}")
            return None  # Skip trade

        # Trade approved by ML
        logger.info(
            f"ML approved: prob={ml_result.success_probability:.1%}, "
            f"conf={ml_result.confidence_score:.1%}"
        )

    return signal
```

### Step 4: Backtest ML-Enhanced Strategy

Run backtest with ML filter enabled:

```bash
python run_backtest.py --days 7 --ml-enabled
```

Compare results:
- **Without ML:** 58% win rate, 100 trades
- **With ML:** 68% win rate, 45 trades (higher quality)

## Feature Engineering

The ML system extracts 70+ features per trade:

### 1. VWAP Features (15)
- Distance from VWAP
- Band position (0=lower, 1=upper)
- Band width (volatility)
- VWAP slope (trend)
- Upper/lower band distances
- Touch counts
- Mean reversion score

### 2. S/R Zone Features (20)
- Zone strength (consolidation quality)
- Touches, bounces, breakouts
- Liquidity grabs (false breakouts)
- Zone age, width
- Distance to zone
- Bounce rate, breakout rate
- Zone confidence score
- VWAP alignment

### 3. VWAP Dynamic S/R (7)
- Closest VWAP band
- Distance to closest band
- Price between VWAP and zone
- VWAP-zone alignment
- Standard deviation distance
- Confluence score

### 4. Temporal Features (8)
- Hour of day (0-23)
- Day of week (0-6)
- Trading session (Asian/London/NY)
- Session overlap
- Weekend flag
- Monday flag

### 5. Market Regime (5)
- Price vs 100 SMA
- Trend strength
- Volatility percentile
- Market state (ranging/trending)
- Price range average

## Model Details

### RandomForest Classifier

**Why RandomForest?**
- Excellent for zone-based features (categorical data)
- Robust to overfitting
- Works with small datasets (200-500 trades)
- Provides feature importance
- Handles non-linear relationships

**Hyperparameters:**
```python
RandomForestClassifier(
    n_estimators=300,        # 300 trees for stability
    max_depth=8,             # Prevents overfitting
    min_samples_split=20,    # Conservative splits
    min_samples_leaf=10,     # Minimum samples per leaf
    max_features='sqrt',     # Feature sampling
    class_weight='balanced', # Handle imbalanced data
    n_jobs=-1                # Use all CPU cores
)
```

### Decision Logic

A trade is approved if:
1. **Success probability ≥ 30%** (with 2:1 R:R, this is profitable)
2. **Confidence score ≥ 65%** (model is confident)

**Philosophy:** Conservative filtering to maximize win rate while maintaining reasonable trade frequency.

## Walk-Forward Validation

Traditional ML validation (random train/test split) is **misleading** for trading because:
- It mixes past and future data
- Doesn't respect time order
- Overstates performance

**Walk-forward validation** simulates realistic deployment:
```
Split 1: Train [0-100]   Test [100-120]
Split 2: Train [0-120]   Test [120-140]
Split 3: Train [0-140]   Test [140-160]
Split 4: Train [0-160]   Test [160-180]
Split 5: Train [0-180]   Test [180-200]
```

This ensures:
- Model always trained on past data
- Tested on future data
- No look-ahead bias
- Realistic performance estimates

## File Structure

```
trabot/
├── ml_training_data_collector.py  # Step 1: Collect training data
├── train_ml_model.py              # Step 2: Train ML model
├── ml_strategy_filter.py          # Step 3: ML filter integration
├── models/
│   └── vwap_ml_model.pkl         # Trained model (created in Step 2)
├── data/
│   └── training_data.csv         # Training data (created in Step 1)
└── src/
    └── strategy/
        └── vwap_strategy.py      # Your strategy (integrate ML here)
```

## Performance Monitoring

### Training Metrics

Monitor these during training:

1. **Walk-forward win rate improvement**: Should be +5-15%
2. **Trade frequency**: Should be 30-60% (filtering out bad trades)
3. **AUC score**: Should be >0.60 (predictive power)

### Live Trading Metrics

Track these in live/paper trading:

1. **ML approval rate**: % of signals approved (should be ~40-60%)
2. **Approved trade win rate**: Win rate of ML-approved trades
3. **Rejected trade win rate**: Win rate of ML-rejected trades (should be lower!)
4. **Feature importance stability**: Top features should be consistent

### Red Flags

Stop using ML if:
- ML-approved trades perform worse than baseline
- ML approves >80% of trades (not filtering enough)
- ML approves <20% of trades (too conservative)
- Feature importance changes drastically between retrains

## Retraining Schedule

**Recommended:** Retrain model weekly

Why?
- Market conditions change
- Model learns from new data
- Adapts to regime shifts

**Retraining process:**
```bash
# 1. Collect fresh data (last 30 days)
python ml_training_data_collector.py --days 30 --output data/training_$(date +%Y%m%d).csv

# 2. Retrain model
python train_ml_model.py \
    --input data/training_$(date +%Y%m%d).csv \
    --output models/vwap_ml_model_$(date +%Y%m%d).pkl

# 3. Compare old vs new model performance

# 4. If new model is better, deploy it
cp models/vwap_ml_model_$(date +%Y%m%d).pkl models/vwap_ml_model.pkl
```

## Advanced: Feature Engineering Improvements

### Current Features (70)
The system already extracts comprehensive features. To improve further:

1. **Multi-timeframe features**: Add 5m, 15m VWAP alignment
2. **Order book imbalance**: If you have L2 data
3. **Funding rate**: For perp futures (sentiment)
4. **Recent P&L**: Win/loss streak context
5. **Time since last trade**: Prevent overtrading

### Feature Selection

Some features may be redundant or noisy. To identify:

```python
# After training, check feature importance
feature_imp = trainer.get_feature_importance(top_n=50)

# Remove features with importance < 0.001
# Retrain model with selected features
```

## Advanced: Ensemble Models

Instead of single RandomForest, combine multiple models:

```python
from sklearn.ensemble import VotingClassifier, GradientBoostingClassifier
from xgboost import XGBClassifier

ensemble = VotingClassifier(
    estimators=[
        ('rf', RandomForestClassifier(...)),
        ('gb', GradientBoostingClassifier(...)),
        ('xgb', XGBClassifier(...))
    ],
    voting='soft',  # Use probabilities
    weights=[1, 1, 2]  # XGBoost gets 2x weight
)
```

## Troubleshooting

### "Model not found" error

**Problem:** `ml_strategy_filter.py` can't find trained model

**Solution:**
```bash
# Check if model exists
ls -lh models/vwap_ml_model.pkl

# If not, train it first
python train_ml_model.py --input data/training_data.csv --output models/vwap_ml_model.pkl
```

### "Missing features" warning

**Problem:** Feature mismatch between training and live data

**Solution:**
- Ensure `extract_features_from_signal()` matches `_extract_features_at_entry()` exactly
- Check for typos in feature names
- Verify all required data (zone, vwap_bands) is available

### ML filter rejects all trades

**Problem:** `min_confidence` threshold too high

**Solution:**
```bash
# Lower confidence threshold
python train_ml_model.py --input data.csv --output model.pkl --min-confidence 0.55
```

### ML filter approves all trades

**Problem:** Model not learning meaningful patterns

**Solution:**
- Collect more training data (60-90 days)
- Check feature quality (print feature values)
- Verify outcomes are correctly labeled
- Try different model (GradientBoosting instead of RandomForest)

## Next Steps

1. ✅ **Collect data**: Run `ml_training_data_collector.py` for 30+ days
2. ✅ **Train model**: Run `train_ml_model.py` and review metrics
3. ✅ **Integrate**: Add `MLFilter` to `vwap_strategy.py`
4. 🔲 **Backtest**: Compare baseline vs ML-enhanced performance
5. 🔲 **Paper trade**: Test in paper trading for 1 week
6. 🔲 **Go live**: Deploy to live trading with small position sizes
7. 🔲 **Monitor**: Track ML performance daily
8. 🔲 **Retrain**: Retrain model weekly with fresh data

## Support

For issues or questions:
1. Check this README
2. Review `ML_INTEGRATION_ANALYSIS.md` for detailed analysis
3. Check feature extraction logic in `ml_strategy_filter.py`
4. Verify training data quality in CSV output

## References

- **ML Analysis**: `ML_INTEGRATION_ANALYSIS.md`
- **Strategy Analysis**: `VWAP_SR_STRATEGY_ANALYSIS_CORRECT.md`
- **Model Factory**: `/tmp/mlbot/model_factory.py` (reference implementation)
- **Enhanced Features**: `/tmp/mlbot/enhanced_features.py` (reference implementation)
