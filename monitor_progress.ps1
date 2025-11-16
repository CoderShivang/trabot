# Simple progress monitor for Windows PowerShell
# Run with: .\monitor_progress.ps1

$logFile = "C:\Users\shivang\trabot\train_ml_90d_test.log"

Write-Host "================================================================================================" -ForegroundColor Cyan
Write-Host "ML BACKTEST PROGRESS MONITOR" -ForegroundColor Cyan
Write-Host "================================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Monitoring: $logFile" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop monitoring" -ForegroundColor Yellow
Write-Host ""

while ($true) {
    Clear-Host

    Write-Host "================================================================================================" -ForegroundColor Cyan
    Write-Host "ML BACKTEST PROGRESS - Last Update: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
    Write-Host "================================================================================================" -ForegroundColor Cyan
    Write-Host ""

    # Get last 30 lines
    $lastLines = Get-Content -Tail 30 $logFile -ErrorAction SilentlyContinue

    if ($lastLines) {
        # Extract current step
        $stepLine = $lastLines | Where-Object { $_ -match "STEP \d" } | Select-Object -Last 1
        if ($stepLine) {
            Write-Host "Current Step:" -ForegroundColor Green
            Write-Host "  $stepLine" -ForegroundColor White
            Write-Host ""
        }

        # Extract progress
        $progressLine = $lastLines | Where-Object { $_ -match "Backtesting:|Fetched.*candles" } | Select-Object -Last 1
        if ($progressLine) {
            Write-Host "Latest Progress:" -ForegroundColor Green
            Write-Host "  $progressLine" -ForegroundColor White
            Write-Host ""
        }

        # Show last 10 lines
        Write-Host "Recent Activity:" -ForegroundColor Green
        Write-Host "================================================================================================" -ForegroundColor Gray
        $lastLines | Select-Object -Last 10 | ForEach-Object {
            if ($_ -match "ERROR|Error|Traceback") {
                Write-Host $_ -ForegroundColor Red
            } elseif ($_ -match "STEP|COMPARISON") {
                Write-Host $_ -ForegroundColor Cyan
            } elseif ($_ -match "Backtesting:") {
                Write-Host $_ -ForegroundColor Yellow
            } else {
                Write-Host $_
            }
        }
        Write-Host "================================================================================================" -ForegroundColor Gray
    } else {
        Write-Host "Waiting for log file..." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Next refresh in 30 seconds... (Press Ctrl+C to stop)" -ForegroundColor DarkGray

    Start-Sleep -Seconds 30
}
