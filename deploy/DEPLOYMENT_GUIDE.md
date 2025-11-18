# 🚀 Complete VPS Deployment Guide

This guide will walk you through deploying TraBot to a VPS for 24/7 live trading.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [VPS Provider Setup](#vps-provider-setup)
3. [Binance API Setup](#binance-api-setup)
4. [VPS Configuration](#vps-configuration)
5. [Bot Deployment](#bot-deployment)
6. [Testing & Verification](#testing--verification)
7. [Going Live](#going-live)
8. [Monitoring & Maintenance](#monitoring--maintenance)

---

## 1️⃣ Prerequisites

### **What You Need:**
- [ ] Binance Futures account with $100+ balance
- [ ] Credit card for VPS ($5-6/month)
- [ ] Basic Linux/SSH knowledge
- [ ] 2-3 hours for initial setup

### **Recommended VPS Specs:**
- **CPU:** 1 vCPU
- **RAM:** 1-2 GB
- **Storage:** 25 GB SSD
- **OS:** Ubuntu 22.04 LTS
- **Location:** Singapore or Tokyo (low latency to Binance)

---

## 2️⃣ VPS Provider Setup

### **Option A: DigitalOcean (Easiest, Recommended)**

1. **Create Account:**
   - Go to https://www.digitalocean.com
   - Sign up and verify email
   - Add payment method

2. **Create Droplet:**
   - Click "Create" → "Droplets"
   - Choose:
     - **Image:** Ubuntu 22.04 LTS
     - **Plan:** Basic ($6/month)
     - **CPU:** Regular (1 vCPU, 1GB RAM)
     - **Datacenter:** Singapore or San Francisco
     - **Authentication:** SSH key (create if needed)
     - **Hostname:** trabot-production
   - Click "Create Droplet"

3. **Note Your IP:**
   - Copy the droplet IP address (e.g., `123.45.67.89`)
   - Save this for SSH access

### **Option B: Vultr ($5/month)**

1. Go to https://www.vultr.com
2. Create account and add payment
3. Deploy new server:
   - **Server Type:** Cloud Compute
   - **Location:** Singapore or Tokyo
   - **OS:** Ubuntu 22.04
   - **Plan:** $5/month (1 vCPU, 1GB RAM)

### **Option C: AWS EC2 (Free Tier)**

1. Go to https://aws.amazon.com/free
2. Create AWS account
3. Launch EC2 instance:
   - **AMI:** Ubuntu 22.04 LTS
   - **Instance Type:** t2.micro (free tier)
   - **Region:** ap-southeast-1 (Singapore)

---

## 3️⃣ Binance API Setup

### **⚠️ CRITICAL SECURITY STEPS:**

1. **Log into Binance:**
   - Go to https://www.binance.com
   - Navigate to: Profile → API Management

2. **Create New API Key:**
   - Click "Create API"
   - Label: "TraBot Production"
   - Security verification (2FA)

3. **Configure Permissions (CRITICAL!):**
   - ✅ **Enable Futures**
   - ❌ **DISABLE "Enable Withdrawals"** (critical!)
   - ❌ **DISABLE "Enable Spot & Margin Trading"**
   - ✅ **Enable "Restrict access to trusted IPs only"**
     - Add your VPS IP: `123.45.67.89`

4. **Save Credentials:**
   - Copy API Key
   - Copy API Secret
   - **NEVER share these or commit to git!**

### **Testnet API (For Testing First):**

1. Go to https://testnet.binancefuture.com
2. Click "Generate HMAC_SHA256 Key"
3. Save testnet API key and secret
4. Use these for initial testing!

---

## 4️⃣ VPS Configuration

### **Step 1: SSH into VPS**

```bash
# From your local machine
ssh root@123.45.67.89

# If using SSH key
ssh -i ~/.ssh/id_rsa root@123.45.67.89
```

### **Step 2: Create Non-Root User**

```bash
# Create user
adduser trader
# Set password when prompted

# Add to sudo group
usermod -aG sudo trader

# Switch to new user
su - trader
```

### **Step 3: Clone Repository**

```bash
cd ~
git clone https://github.com/CoderShivang/trabot.git
cd trabot
```

### **Step 4: Run Setup Script**

```bash
# Make script executable
chmod +x deploy/vps_setup.sh

# Run setup
./deploy/vps_setup.sh
```

This will install Python, dependencies, and create systemd service.

### **Step 5: Configure Environment**

```bash
# Edit .env file
nano .env
```

**Add your credentials:**
```env
# Binance API Credentials (TESTNET FIRST!)
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here

# Start with TESTNET
TESTNET=true

# Trading Parameters
SYMBOL=BTCUSDT
LEVERAGE=5  # Start conservative!
MAX_POSITION_USDT=20.0  # Small size for testing

# Risk Management
RISK_PER_TRADE=0.5  # Risk $0.50 per trade
```

Save: `Ctrl+X` → `Y` → `Enter`

---

## 5️⃣ Bot Deployment

### **Step 1: Test Manually First**

```bash
cd ~/trabot
source venv/bin/activate
python src/trading/live_trader.py
```

**What to Look For:**
- ✅ "Connected successfully"
- ✅ "Wallet Balance: $XXX"
- ✅ "Mode: TESTNET"
- ✅ "Leverage set to 5x"

**Test Order Placement:**
- Watch logs for "[ORDER] Placing POST-only"
- Verify "timeInForce: GTX"
- Check Binance Testnet UI for orders

### **Step 2: Enable Systemd Service**

```bash
# Enable auto-start on boot
sudo systemctl enable trabot

# Start the service
sudo systemctl start trabot

# Check status
sudo systemctl status trabot
```

Should show: `Active: active (running)`

### **Step 3: Monitor Logs**

```bash
# View live logs
tail -f /var/log/trabot.log

# View errors
tail -f /var/log/trabot.error.log

# View last 100 lines
tail -100 /var/log/trabot.log
```

---

## 6️⃣ Testing & Verification

### **Testnet Testing Checklist (1-2 Weeks):**

- [ ] **Day 1-3:** Verify bot connects and places orders
- [ ] **Day 4-7:** Verify orders use POST-only (GTX)
- [ ] **Day 8-10:** Verify stop losses trigger correctly
- [ ] **Day 11-14:** Verify take profits execute
- [ ] **Throughout:** Monitor for any errors or crashes

### **Verification Commands:**

```bash
# Check bot is running
sudo systemctl status trabot

# View recent trades
tail -100 /var/log/trabot.log | grep "EXIT"

# Check for errors
grep "ERROR" /var/log/trabot.log

# Check POST-only orders
grep "POST-only" /var/log/trabot.log
```

### **Binance Testnet Verification:**

1. Log into https://testnet.binancefuture.com
2. Check "Order History":
   - All filled orders should show **0.02% fee**
   - If you see 0.04%, POST-only isn't working!
3. Check "Position History":
   - Verify SL and TP triggered correctly

---

## 7️⃣ Going Live

### **⚠️ ONLY After Testnet Success!**

### **Step 1: Create Live API Key**

Follow [Section 3](#binance-api-setup) but for **live Binance** (not testnet)

**Critical Settings:**
- ❌ **DISABLE "Enable Withdrawals"**
- ✅ **IP Whitelist: Only your VPS IP**

### **Step 2: Update .env**

```bash
nano ~/trabot/.env
```

Change:
```env
# ⚠️ GOING LIVE - REAL MONEY!
BINANCE_API_KEY=your_LIVE_api_key
BINANCE_API_SECRET=your_LIVE_api_secret
TESTNET=false  # ← Changed from true!

# Start small!
LEVERAGE=5
MAX_POSITION_USDT=20.0
RISK_PER_TRADE=0.5
```

### **Step 3: Restart Bot**

```bash
sudo systemctl restart trabot
sudo systemctl status trabot
```

### **Step 4: Monitor Closely**

```bash
# Watch live logs for first 30 minutes
tail -f /var/log/trabot.log
```

**What to Watch:**
- First line should say: "Mode: LIVE MAINNET"
- Check wallet balance is correct
- Verify first order uses POST-only (GTX)

---

## 8️⃣ Monitoring & Maintenance

### **Daily Checks (First Month):**

```bash
# Morning check
ssh trader@your_vps_ip
sudo systemctl status trabot
tail -50 /var/log/trabot.log
```

### **Weekly Tasks:**

1. **Review Performance:**
   ```bash
   # Count winning vs losing trades
   grep "TP HIT" /var/log/trabot.log | wc -l  # Wins
   grep "SL HIT" /var/log/trabot.log | wc -l  # Losses
   ```

2. **Check Disk Space:**
   ```bash
   df -h
   # If >80% full, clean old logs
   sudo journalctl --vacuum-time=7d
   ```

3. **Update Code:**
   ```bash
   cd ~/trabot
   git pull origin main
   sudo systemctl restart trabot
   ```

### **Set Up Alerts (Optional):**

Install `monit` for automatic monitoring:

```bash
sudo apt install monit

# Configure alerts
sudo nano /etc/monit/monitrc
```

Add:
```
check process trabot with pidfile /var/run/trabot.pid
    start program = "/bin/systemctl start trabot"
    stop program = "/bin/systemctl stop trabot"
    if failed host 127.0.0.1 port 8080 then restart
    if 5 restarts within 5 cycles then alert
```

---

## 🚨 Emergency Procedures

### **If Something Goes Wrong:**

**Method 1: Emergency Shutdown Script**
```bash
cd ~/trabot
source venv/bin/activate
python deploy/emergency_shutdown.py
```

**Method 2: Stop Bot**
```bash
sudo systemctl stop trabot
```

**Method 3: Manual Binance Close**
1. Log into Binance Futures
2. Go to "Positions"
3. Click "Close All"
4. Go to "Open Orders" → "Cancel All"

---

## 📊 Performance Tracking

### **Create a Spreadsheet:**

Track daily:
| Date | Trades | Wins | Losses | Win Rate | P&L | Balance |
|------|--------|------|--------|----------|-----|---------|
| Day 1 | 3 | 2 | 1 | 66% | +$1.50 | $101.50 |
| Day 2 | 2 | 1 | 1 | 50% | -$0.25 | $101.25 |

### **Binance API for Balance:**

```bash
# Check current balance
python -c "from binance.client import Client; c = Client('key', 'secret'); print(c.futures_account_balance())"
```

---

## 🔧 Troubleshooting

### **Bot Won't Start:**
```bash
# Check logs for errors
sudo journalctl -u trabot -n 50

# Test manually
cd ~/trabot
source venv/bin/activate
python src/trading/live_trader.py
```

### **Orders Not Filling:**
- Check price is below market for LONG (above for SHORT)
- Verify POST-only orders sit on book
- Check Binance UI for open orders

### **"API key invalid" Error:**
- Verify API key in .env is correct
- Check IP whitelist includes your VPS IP
- Ensure Futures permission is enabled

### **High CPU Usage:**
```bash
# Check resource usage
top
htop

# Reduce monitoring frequency in code
```

---

## 📚 Additional Resources

- **Binance API Docs:** https://binance-docs.github.io/apidocs/futures/en/
- **Python-Binance Docs:** https://python-binance.readthedocs.io/
- **VPS Security Guide:** https://www.digitalocean.com/community/tutorials/initial-server-setup-with-ubuntu-22-04

---

## ✅ Final Pre-Launch Checklist

- [ ] Tested on testnet for 1-2 weeks
- [ ] All orders verified as POST-only (0.02% fees)
- [ ] Stop loss tested and working
- [ ] Take profit tested and working
- [ ] Emergency shutdown tested
- [ ] Live API key created with proper permissions
- [ ] IP whitelist configured
- [ ] Starting with small position sizes ($20-50)
- [ ] Starting with low leverage (5-10x)
- [ ] Have SSH access from phone (for emergencies)
- [ ] Read SAFETY_CHECKLIST.md completely
- [ ] Capital is money you can afford to lose

---

**Remember: Start small, test thoroughly, scale gradually!**

Good luck! 🚀
