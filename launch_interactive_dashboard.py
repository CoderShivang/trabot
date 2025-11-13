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

# Find most recent backtest results
results_dir = Path('data/vwap_backtest')

if not results_dir.exists():
    print("[ERROR] No backtest results found. Run a backtest first:")
    print("  python run_vwap_backtest.py")
    sys.exit(1)

# Find most recent results file
results_files = list(results_dir.glob('backtest_*.json'))
if not results_files:
    print("[ERROR] No backtest results found in data/vwap_backtest/")
    print("Run a backtest first: python run_vwap_backtest.py")
    sys.exit(1)

# Get most recent file
latest_results = max(results_files, key=lambda p: p.stat().st_mtime)
print(f"[INFO] Loading backtest: {latest_results.name}")

# Load OHLCV data
ohlcv_path = results_dir / 'ohlcv_data.parquet'
if not ohlcv_path.exists():
    print("[ERROR] OHLCV data not found. Re-run the backtest to generate it.")
    sys.exit(1)

df = pd.read_parquet(ohlcv_path)

# Launch dashboard
dashboard = InteractiveDashboard(str(latest_results), df)
dashboard.run(port=8050, debug=False, open_browser=True)
