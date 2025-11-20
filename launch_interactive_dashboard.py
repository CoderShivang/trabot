"""
Launch Interactive VWAP Backtest Dashboard

Usage:
    python launch_interactive_dashboard.py

Features:
- Filter trades by outcome (WIN/LOSS), direction (LONG/SHORT), signal type
- Click any trade to view its specific chart
- See only the decision-making context (VWAP bands, S/R zones) for that trade
- No clutter from other trades
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.visualization.interactive_dashboard import InteractiveDashboard
import pandas as pd

# Find most recent backtest results (check both directories)
vwap_dir = Path('data/vwap_backtest')
ml_dir = Path('data/vwap_ml_backtest')

# Collect results from both directories
results_files = []
if vwap_dir.exists():
    results_files.extend(list(vwap_dir.glob('backtest_*.json')))
    results_files.extend(list(vwap_dir.glob('vwap_backtest_*.json')))
if ml_dir.exists():
    results_files.extend(list(ml_dir.glob('vwap_ml_*.json')))

if not results_files:
    print("[ERROR] No backtest results found in data/vwap_backtest/ or data/vwap_ml_backtest/")
    print("Run a backtest first:")
    print("  python run_vwap_backtest.py  (or)")
    print("  python run_vwap_ml_backtest.py")
    sys.exit(1)

# Get most recent file
latest_results = max(results_files, key=lambda p: p.stat().st_mtime)
results_dir = latest_results.parent
print(f"[INFO] Loading backtest: {latest_results.name}")
print(f"[INFO] From directory: {results_dir}")

# Load OHLCV data from the same directory
ohlcv_path = results_dir / 'ohlcv_data.parquet'
if not ohlcv_path.exists():
    print(f"[ERROR] OHLCV data not found at: {ohlcv_path}")
    print("Re-run the backtest to generate OHLCV data.")
    sys.exit(1)

df = pd.read_parquet(ohlcv_path)

# Launch dashboard
dashboard = InteractiveDashboard(str(latest_results), df)
dashboard.run(port=8050, debug=False, open_browser=True)
