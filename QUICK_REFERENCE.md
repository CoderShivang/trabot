# ⚡ Quick Reference Card

One-page cheatsheet for common VPS operations.

---

## 🎮 Bot Control

```bash
./bot_control.sh start      # Start bot
./bot_control.sh stop       # Stop bot
./bot_control.sh restart    # Restart bot
./bot_control.sh status     # Show status
./bot_control.sh logs       # View logs
```

---

## 🔄 Making Updates

```bash
# From your local machine:
git add .
git commit -m "Your changes"
git push origin main

# On your VPS:
./deploy_update.sh
```

---

## 🚨 Emergency Rollback

```bash
./rollback.sh                           # List backups
./rollback.sh backup_20250111_143000   # Rollback
./bot_control.sh start                  # Restart
```

---

## 📊 Monitoring Commands

```bash
# Quick health check
./bot_control.sh status

# Watch live logs
tail -f logs/bot_$(date +%Y%m%d).log

# Check recent errors
./bot_control.sh logs | grep -i "error"

# View recent trades
cat data/trades.json | jq '.[-10:]'

# Check balance
cat data/balance.json | jq '.'

# CPU and memory usage
top -p $(cat bot.pid)
```

---

## 🔧 Configuration Changes

```bash
# Edit main config
nano config/bot_config.yaml

# Edit environment
nano .env

# Apply changes (restarts bot)
./deploy_update.sh

# Or reload without restart (config only)
kill -HUP $(cat bot.pid)  # If hot-reload enabled
```

---

## 📈 Running Backtests

```bash
# Activate environment
source venv/bin/activate

# Run backtest
python run_backtest.py --symbol BTCUSDT --days 7

# With custom date range
python run_backtest.py --symbol ETHUSDT --start 2025-01-01 --end 2025-01-07

# Launch dashboard
streamlit run dashboard.py
```

---

## 🐛 Troubleshooting

```bash
# Bot won't start?
./bot_control.sh logs                # Check logs
python main.py                       # Run in foreground
source venv/bin/activate && python main.py

# Dependencies broken?
pip install -r requirements.txt --upgrade

# Git conflicts?
git stash && git pull && git stash pop

# Nuclear option (resets everything)
git reset --hard HEAD
./deploy_update.sh

# Emergency: stop all Python processes
pkill -f "python main.py"
```

---

## 📁 Important Files

```
bot.pid                    # Current bot process ID
logs/bot_YYYYMMDD.log     # Daily logs
data/trades.json          # All trades
data/balance.json         # Current balance
data/feedback.json        # Human ratings
backups/                  # Auto backups
config/bot_config.yaml    # Main config
.env                      # API keys
```

---

## 🎯 Common Tasks

### Change Leverage
```bash
nano config/bot_config.yaml  # Edit: leverage: 50
./deploy_update.sh
```

### Change Position Size
```bash
nano config/bot_config.yaml  # Edit: position_size_usdt: 15.0
./deploy_update.sh
```

### Change Entry Threshold
```bash
nano config/bot_config.yaml  # Edit: entry_threshold: 75.0
./deploy_update.sh
```

### Enable/Disable ML
```bash
nano config/bot_config.yaml  # Edit: ml_override_enabled: true
./deploy_update.sh
```

### View Trading Stats
```bash
# Total trades
cat data/trades.json | jq 'length'

# Win rate
cat data/trades.json | jq '[.[] | select(.pnl > 0)] | length'

# Total P&L
cat data/trades.json | jq '[.[] | .pnl] | add'

# Largest win
cat data/trades.json | jq '[.[] | .pnl] | max'

# Largest loss
cat data/trades.json | jq '[.[] | .pnl] | min'
```

---

## 🔐 Security

```bash
# Restrict file permissions
chmod 600 .env
chmod 600 config/bot_config.yaml
chmod 700 bot.pid

# Check who can access files
ls -la .env

# Review API key permissions on Binance
# Should be: Read + Futures Trading only
# Never: Withdraw permission
```

---

## 💾 Backups

```bash
# List automatic backups
./rollback.sh

# Manual backup
tar -czf ~/backup_$(date +%Y%m%d).tar.gz data/ .env config/

# Download backup to local machine
# (Run from local machine)
scp tradingbot@vps-ip:~/backup_20250111.tar.gz ~/Downloads/

# Restore from backup
tar -xzf backup_20250111.tar.gz
./bot_control.sh restart
```

---

## 📞 Getting Help

```bash
# View full documentation
cat README.md
cat VPS_DEPLOYMENT_GUIDE.md
cat ENTRY_LOGIC_EXPLAINED.md
cat BACKTESTING_GUIDE.md

# Check system resources
df -h              # Disk space
free -h            # RAM
top                # CPU/Memory by process
netstat -tulpn     # Network connections
```

---

## ⚠️ Emergency Contacts

**If bot behaving unexpectedly:**
1. `./bot_control.sh stop` - Stop immediately
2. Check logs: `./bot_control.sh logs`
3. Close open positions on Binance manually if needed
4. Review last changes: `git log -5`
5. Rollback if necessary: `./rollback.sh`

**If you lose access to VPS:**
- Close positions via Binance web/mobile app
- API keys can be disabled in Binance settings
- Contact VPS provider for access recovery

---

**Pro Tip:** Print this page and keep near your desk! 📄
