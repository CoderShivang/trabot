"""
Run VWAP Strategy Backtest

Usage:
    python run_vwap_backtest.py --symbol BTCUSDT --days 7
    python run_vwap_backtest.py --symbol ETHUSDT --start 2025-01-01 --end 2025-01-07

Features:
- Uses VWAP + S/R strategy
- All orders are limit orders (lower fees)
- Fetches data from live Binance mainnet
- Detailed trade logging
- Supports 1-minute timeframe
"""

import asyncio
import argparse
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.backtesting.vwap_backtest_engine import VWAPBacktestEngine
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Run VWAP Strategy Backtest')

    parser.add_argument('--symbol', type=str, default='BTCUSDT',
                        help='Trading pair (default: BTCUSDT)')

    parser.add_argument('--timeframe', type=str, default='1m',
                        help='Timeframe (default: 1m)')

    parser.add_argument('--days', type=int, default=7,
                        help='Number of days to backtest (default: 7)')

    parser.add_argument('--start', type=str, default=None,
                        help='Start date (YYYY-MM-DD)')

    parser.add_argument('--end', type=str, default=None,
                        help='End date (YYYY-MM-DD)')

    parser.add_argument('--capital', type=float, default=100,
                        help='Initial margin in USDT (default: 100)')

    parser.add_argument('--leverage', type=int, default=20,
                        help='Leverage multiplier (default: 20)')

    parser.add_argument('--risk', type=float, default=0.02,
                        help='Risk per trade as decimal (default: 0.02 = 2%%)')

    # Strategy parameters
    parser.add_argument('--target', type=int, default=200,
                        help='Take profit in dollars (default: 200)')

    parser.add_argument('--stop', type=int, default=150,
                        help='Stop loss in dollars (default: 150)')

    parser.add_argument('--band-proximity', type=int, default=300,
                        help='How close to VWAP band for entry (default: 300)')

    parser.add_argument('--zone-proximity', type=int, default=500,
                        help='How close to S/R zone for entry (default: 500)')

    parser.add_argument('--min-zone-strength', type=int, default=20,
                        help='Minimum S/R zone quality (0-100, default: 20)')

    # ML Filtering
    parser.add_argument('--ml-filter', action='store_true',
                        help='Enable ML filtering with walk-forward analysis (default: False)')

    parser.add_argument('--min-win-prob', type=float, default=0.60,
                        help='Minimum win probability for ML filter (default: 0.60)')

    return parser.parse_args()


async def main():
    """Main entry point"""
    args = parse_args()

    # If ML filtering is enabled, use the ML backtest engine
    if args.ml_filter:
        logger.info("[ML-FILTER] Running backtest with ML filtering...")
        logger.info("[ML-FILTER] Using simple train/test split (first 50% for training, second 50% for testing)")

        from src.learning.vwap_ml_optimizer import VWAPMLOptimizer
        from src.backtesting.vwap_ml_backtest_engine import VWAPMLBacktestEngine

        # Determine date range
        if args.start and args.end:
            start_date = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            end_date = datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        else:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=args.days)

        # Split into training and testing periods
        total_duration = end_date - start_date
        train_end_date = start_date + (total_duration / 2)
        test_start_date = train_end_date

        logger.info(f"[ML-TRAIN] Training period: {start_date.strftime('%Y-%m-%d')} to {train_end_date.strftime('%Y-%m-%d')}")
        logger.info(f"[ML-TEST] Testing period: {test_start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        # Build config
        config = {
            'symbol': args.symbol,
            'timeframe': args.timeframe,
            'initial_capital': args.capital,
            'leverage': args.leverage,
            'risk_per_trade': args.risk,
            'strategy_params': {
                'target_points': args.target,
                'stop_points': args.stop,
                'band_proximity': args.band_proximity,
                'zone_proximity': args.zone_proximity,
                'min_zone_strength': args.min_zone_strength
            }
        }

        # Phase 1: Training (no ML filtering, collect training data)
        logger.info("\n[PHASE 1] Running training period to collect signals...")
        train_engine = VWAPBacktestEngine(config)
        train_results = await train_engine.run(start_date, train_end_date)

        # Collect training data from executed trades
        training_signals = []
        training_outcomes = []

        for trade in train_engine.executed_trades:
            if hasattr(trade, 'entry_signal') and trade.entry_signal:
                # Create signal dict
                signal_data = {
                    'signal': trade.entry_signal,
                    'market_data': {
                        'current_price': trade.entry_price,
                        'timestamp': trade.entry_time,
                        'volume': getattr(trade, 'volume', 0),
                        'volatility': abs(trade.entry_price * 0.01),  # Approximate
                        'spread_bps': 10  # Approximate
                    }
                }
                training_signals.append(signal_data)

                # Outcome: 1 if profitable, 0 if loss
                pnl = trade.pnl if hasattr(trade, 'pnl') else 0
                training_outcomes.append(1 if pnl > 0 else 0)

        logger.info(f"[ML-TRAIN] Collected {len(training_signals)} training samples")

        # Train ML models
        ml_optimizer = VWAPMLOptimizer(min_win_probability=args.min_win_prob)

        if len(training_signals) >= 30:
            logger.info(f"[ML-TRAIN] Training ML models on {len(training_signals)} signals...")
            metrics = ml_optimizer.train_models(training_signals, training_outcomes)
            logger.info(f"[ML-TRAIN] Training complete. Model metrics:")
            for model_name, model_metrics in metrics.items():
                logger.info(f"  {model_name}: Accuracy={model_metrics.get('accuracy', 0):.2%}")
        else:
            logger.warning(f"[ML-TRAIN] Insufficient training data ({len(training_signals)}/30 signals). Skipping ML filtering.")
            logger.info("\n[FALLBACK] Running standard backtest without ML filtering...")
            ml_optimizer = None

        # Phase 2: Testing with ML filtering
        logger.info("\n[PHASE 2] Running test period with ML filtering...")
        ml_test_engine = VWAPMLBacktestEngine(config, ml_optimizer=ml_optimizer)
        test_results = await ml_test_engine.run(test_start_date, end_date)

        logger.info("\n[DONE] ML-filtered backtest complete! Check data/vwap_ml_backtest/ for results.")
        return

    # Regular backtest (no ML filtering)
    logger.info("[NO-ML] Running standard VWAP backtest (no ML filtering)...")

    # Determine date range
    if args.start and args.end:
        start_date = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    else:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=args.days)

    # Build config
    config = {
        'symbol': args.symbol,
        'timeframe': args.timeframe,
        'initial_capital': args.capital,
        'leverage': args.leverage,
        'risk_per_trade': args.risk,
        'strategy_params': {
            'target_points': args.target,
            'stop_points': args.stop,
            'band_proximity': args.band_proximity,
            'zone_proximity': args.zone_proximity,
            'min_zone_strength': args.min_zone_strength
        }
    }

    # Create engine
    engine = VWAPBacktestEngine(config)

    # Run backtest
    await engine.run(start_date, end_date)

    logger.info("\n[DONE] Backtest complete! Check data/vwap_backtest/ for detailed results.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[INTERRUPTED] Backtest stopped by user")
    except Exception as e:
        logger.error(f"\n[ERROR] Backtest failed: {e}")
        import traceback
        traceback.print_exc()
