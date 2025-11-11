# 🚀 VPS Deployment & Update Guide

Complete guide for deploying and maintaining your trading bot on a VPS with safe update workflows.

---

## 📋 Table of Contents

1. [Initial VPS Setup](#initial-vps-setup)
2. [Deployment Scripts](#deployment-scripts)
3. [Making Updates While Live](#making-updates-while-live)
4. [Emergency Rollback](#emergency-rollback)
5. [Monitoring & Maintenance](#monitoring--maintenance)
6. [Best Practices](#best-practices)

---

## 🖥️ Initial VPS Setup

### Step 1: Prepare Your VPS

```bash
# SSH into your VPS
ssh root@your-vps-ip

# Update system
apt update && apt upgrade -y

# Install Python 3.10+
apt install -y python3 python3-pip python3-venv git

# Create a dedicated user (recommended)
useradd -m -s /bin/bash tradingbot
usermod -aG sudo tradingbot
su - tradingbot
```

### Step 2: Clone and Setup

```bash
# Navigate to installation directory
cd ~
mkdir -p trading
cd trading

# Clone your repository
git clone https://github.com/your-username/trabot.git
cd trabot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
nano .env  # Add your Binance API keys and settings
```

### Step 3: Configure for Production

```bash
# Edit configuration
nano config/bot_config.yaml

# Important settings to review:
# - trading.leverage (start conservative: 30-50×)
# - risk.per_trade_max_loss_usdt ($10-15)
# - risk.daily_max_loss_usdt ($30)
# - strategy.entry_threshold (75.0 recommended)
```

### Step 4: Make Scripts Executable

```bash
chmod +x bot_control.sh
chmod +x deploy_update.sh
chmod +x rollback.sh
```

### Step 5: Test Installation

```bash
# Test configuration loading
python -c "
import sys
sys.path.insert(0, 'src')
from config import load_config
config = load_config()
print('✓ Configuration loaded')
print(f'Symbols: {config.trading.symbols}')
"

# Run a quick 1-day backtest (requires API keys)
python run_backtest.py --symbol BTCUSDT --days 1

# If backtest succeeds, you're ready!
```

---

## 🛠️ Deployment Scripts

You have three helper scripts for managing the bot:

### 1. `bot_control.sh` - Daily Bot Management

```bash
# Start the bot
./bot_control.sh start

# Check status
./bot_control.sh status

# View recent logs
./bot_control.sh logs

# Restart the bot
./bot_control.sh restart

# Stop the bot
./bot_control.sh stop
```

**Status Output Example:**
```
● Bot is RUNNING
PID: 12345
Uptime: 02:15:30
Memory: 245.3 MB
CPU: 3.2%
Log file: logs/bot_20250111.log
Total trades: 47
```

### 2. `deploy_update.sh` - Safe Code Updates

```bash
# Full update with automatic restart
./deploy_update.sh

# Update code only (no restart)
./deploy_update.sh --no-restart
```

**What it does:**
1. ✅ Checks bot status
2. ✅ Creates automatic backup
3. ✅ Stops bot gracefully
4. ✅ Pulls latest code from git
5. ✅ Updates dependencies
6. ✅ Runs validation tests
7. ✅ Restarts bot
8. ✅ Verifies successful start

### 3. `rollback.sh` - Emergency Recovery

```bash
# List available backups
./rollback.sh

# Rollback to specific backup
./rollback.sh backup_20250111_143000
```

---

## 🔄 Making Updates While Live

### Workflow A: Direct Git Updates (Small Changes)

Use this for config tweaks, parameter adjustments, or bug fixes.

```bash
# 1. SSH into VPS
ssh tradingbot@your-vps-ip
cd ~/trading/trabot

# 2. Make changes on your local machine and push to git
# (From your local machine)
git add .
git commit -m "Adjust entry threshold to 70"
git push origin main

# 3. Pull and apply updates on VPS
./deploy_update.sh
```

**Timeline:**
- Backup: ~5 seconds
- Stop bot: ~5 seconds (closes positions first)
- Update code: ~10 seconds
- Restart: ~5 seconds
- **Total downtime: ~25 seconds**

### Workflow B: Development → Staging → Production (Major Changes)

Use this for new features or risky changes.

```bash
# On your local machine

# 1. Create feature branch
git checkout -b feature/improve-sr-detection

# 2. Make changes and test locally
# ... make changes ...
python run_backtest.py --symbol BTCUSDT --days 7

# 3. Commit and push feature branch
git add .
git commit -m "feat: Improve S/R detection accuracy"
git push origin feature/improve-sr-detection

# 4. Merge to staging branch (optional)
git checkout staging
git merge feature/improve-sr-detection
git push origin staging

# 5. Test on staging VPS
ssh staging-vps
cd trabot
git pull origin staging
./deploy_update.sh

# Monitor for 24 hours...

# 6. If successful, merge to production
git checkout main
git merge staging
git push origin main

# 7. Deploy to production VPS
ssh production-vps
cd trabot
./deploy_update.sh
```

### Workflow C: Hot-Fix for Critical Bugs

```bash
# 1. Create emergency fix locally
git checkout -b hotfix/critical-stop-loss-bug
# ... fix the bug ...
git commit -m "hotfix: Fix stop loss calculation error"
git push origin hotfix/critical-stop-loss-bug

# 2. Merge directly to main (skip staging in emergency)
git checkout main
git merge hotfix/critical-stop-loss-bug
git push origin main

# 3. Deploy immediately to production
ssh production-vps
cd trabot
./deploy_update.sh

# 4. Monitor logs intensely
./bot_control.sh logs
tail -f logs/bot_$(date +%Y%m%d).log
```

---

## 🚨 Emergency Rollback

### When to Rollback

- Bot crashes repeatedly after update
- Unexpected trading behavior (entering bad trades)
- Configuration errors causing losses
- Dependency conflicts

### How to Rollback

```bash
# 1. SSH into VPS
ssh tradingbot@your-vps-ip
cd ~/trading/trabot

# 2. List available backups
./rollback.sh

# Output:
# backup_20250111_143500 (commit: 3e37f65)
# backup_20250111_120000 (commit: 356967c)
# backup_20250110_180000 (commit: 758ca92)

# 3. Choose a backup (typically the most recent before the bad update)
./rollback.sh backup_20250111_120000

# 4. Restart bot
./bot_control.sh start

# 5. Verify it's working
./bot_control.sh status
./bot_control.sh logs
```

**Rollback restores:**
- ✅ Git commit (exact code state)
- ✅ Data files (trades, feedback, ML models)
- ✅ Configuration (bot_config.yaml)
- ✅ Environment variables (.env)
- ✅ Dependencies (requirements.txt versions)

---

## 📊 Monitoring & Maintenance

### Daily Checks

```bash
# Quick health check (run daily)
./bot_control.sh status

# Check if any errors in last hour
./bot_control.sh logs | grep -i "error"

# Check recent trades
cat data/trades.json | jq '.[-5:]'  # Last 5 trades

# Check current balance
cat data/balance.json | jq '.'
```

### Set Up Cron Jobs

```bash
# Edit crontab
crontab -e

# Add monitoring jobs:

# Health check every hour
0 * * * * cd ~/trading/trabot && ./bot_control.sh status >> logs/health_$(date +\%Y\%m\%d).log 2>&1

# Daily backup at 2 AM
0 2 * * * cd ~/trading/trabot && tar -czf ~/backups/trabot_$(date +\%Y\%m\%d).tar.gz data/ .env config/ >> logs/backup.log 2>&1

# Restart daily at 3 AM (optional - clears memory leaks)
0 3 * * * cd ~/trading/trabot && ./bot_control.sh restart >> logs/restart.log 2>&1

# Clean old logs weekly (keep 30 days)
0 4 * * 0 find ~/trading/trabot/logs/ -name "*.log" -mtime +30 -delete
```

### Set Up systemd Service (Recommended)

Create a service that auto-starts on boot:

```bash
# Create service file
sudo nano /etc/systemd/system/tradingbot.service
```

Add:
```ini
[Unit]
Description=Trading Bot
After=network.target

[Service]
Type=simple
User=tradingbot
WorkingDirectory=/home/tradingbot/trading/trabot
ExecStart=/home/tradingbot/trading/trabot/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:/home/tradingbot/trading/trabot/logs/bot.log
StandardError=append:/home/tradingbot/trading/trabot/logs/bot_error.log

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable tradingbot
sudo systemctl start tradingbot

# Check status
sudo systemctl status tradingbot

# View logs
journalctl -u tradingbot -f
```

---

## 🎯 Best Practices

### 1. Testing Strategy

```bash
# ALWAYS test locally first
python run_backtest.py --symbol BTCUSDT --days 7

# Then test on testnet VPS (if available)
BINANCE_TESTNET=true python main.py

# Only then deploy to production
```

### 2. Gradual Rollouts

```bash
# Step 1: Deploy with reduced position size
# Edit config/bot_config.yaml
# position_size_usdt: 5.0  (instead of 15.0)
./deploy_update.sh

# Step 2: Monitor for 24 hours

# Step 3: If successful, increase position size
# position_size_usdt: 15.0
./deploy_update.sh
```

### 3. Monitoring Alerts

Set up alerts for critical events:

```bash
# Create alert script
nano ~/trading/trabot/alert.sh
```

```bash
#!/bin/bash
# Send alert if bot dies
if ! ./bot_control.sh status | grep -q "RUNNING"; then
    # Send email/telegram/discord notification
    echo "Bot is DOWN!" | mail -s "URGENT: Trading Bot Down" your@email.com
fi
```

Run via cron every 15 minutes:
```bash
*/15 * * * * cd ~/trading/trabot && ./alert.sh
```

### 4. Version Tagging

```bash
# Before major updates, tag the current version
git tag -a v1.0.0 -m "Stable version before ML upgrade"
git push origin v1.0.0

# If needed to rollback to tagged version
git checkout v1.0.0
./deploy_update.sh --no-restart
./bot_control.sh restart
```

### 5. Change Log

Keep a changelog for tracking updates:

```bash
# Update CHANGELOG.md before each deployment
echo "## v1.1.0 - $(date +%Y-%m-%d)" >> CHANGELOG.md
echo "- Improved S/R detection accuracy" >> CHANGELOG.md
echo "- Added ML confidence threshold" >> CHANGELOG.md
echo "- Fixed stop loss bug" >> CHANGELOG.md
```

### 6. Pre-Deployment Checklist

Before running `./deploy_update.sh`:

- [ ] Code tested locally with backtests
- [ ] Configuration reviewed (no accidental leverage changes)
- [ ] Current balance noted (to verify no trades lost)
- [ ] Backup verified (check `./rollback.sh`)
- [ ] Low volatility period (avoid deploying during high vol events)
- [ ] No open positions (or acceptable to close them)
- [ ] Alternative capital available if bot fails

---

## 🔧 Advanced: Zero-Downtime Updates

For critical production environments where you can't afford even 25 seconds of downtime:

### Option 1: Blue-Green Deployment

```bash
# Run two instances simultaneously
# Instance A (blue) - currently running
# Instance B (green) - updated version

# 1. Start green instance on different port
cd ~/trading/trabot-green
git pull origin main
./bot_control.sh start

# 2. Wait 5 minutes, verify green is working

# 3. Gracefully stop blue
cd ~/trading/trabot-blue
./bot_control.sh stop

# 4. Green is now primary
```

### Option 2: Hot-Reload Configuration

For config-only changes (no code changes):

```python
# Add to main.py
import signal
import importlib

def reload_config(signum, frame):
    global config
    config = load_config()
    logger.info("Configuration reloaded")

signal.signal(signal.SIGHUP, reload_config)
```

Then on VPS:
```bash
# Edit config
nano config/bot_config.yaml

# Send reload signal (no restart needed)
kill -HUP $(cat bot.pid)
```

---

## 📞 Troubleshooting

### Bot Won't Start After Update

```bash
# Check logs
./bot_control.sh logs

# Check Python errors
source venv/bin/activate
python main.py  # Run in foreground to see errors

# Verify dependencies
pip install -r requirements.txt --upgrade

# Rollback if persistent
./rollback.sh backup_20250111_120000
```

### Update Script Fails

```bash
# Check git status
git status

# If merge conflicts
git stash
git pull origin main
git stash pop

# If dependency errors
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Backup Not Created

```bash
# Check disk space
df -h

# Check permissions
ls -la backups/

# Manually create backup
mkdir -p backups/manual_$(date +%Y%m%d_%H%M%S)
cp -r data/ backups/manual_$(date +%Y%m%d_%H%M%S)/
```

---

## 📝 Summary

**Typical Update Workflow:**

1. **Develop locally** → Test with backtests
2. **Push to git** → `git push origin main`
3. **SSH to VPS** → `ssh tradingbot@vps-ip`
4. **Run update** → `./deploy_update.sh`
5. **Monitor** → `./bot_control.sh logs`
6. **If issues** → `./rollback.sh backup_XXXXXX`

**Key Files:**
- `bot_control.sh` - Start/stop/status
- `deploy_update.sh` - Safe updates
- `rollback.sh` - Emergency recovery
- `logs/` - All logs
- `backups/` - Automatic backups
- `data/` - Critical data (trades, ML models)

**Remember:**
- ✅ Test locally first
- ✅ Update during low-volatility periods
- ✅ Monitor after every update
- ✅ Keep backups for 30+ days
- ✅ Document all changes

---

**Questions or issues?** Check logs first: `./bot_control.sh logs`
