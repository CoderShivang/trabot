#!/bin/bash
# Continuously update log file for Windows PowerShell access
while true; do
    cp /tmp/train_ml_90d_test_v2.log C:/Users/shivang/trabot/ml_backtest_progress.log 2>/dev/null
    sleep 10
done
