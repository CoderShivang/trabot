# 🛡️ LIVE TRADING SAFETY CHECKLIST

**⚠️ CRITICAL: Complete ALL items before live trading!**

---

## ✅ Pre-Deployment Checklist

### **1. API Security**
- [ ] Created Binance Futures API key with **ONLY** "Enable Futures" permission
- [ ] **DISABLED** "Enable Withdrawals" permission (critical!)
- [ ] Set IP whitelist to your VPS IP only
- [ ] Stored API credentials in `.env` file (never in code)
- [ ] `.env` file has proper permissions: `chmod 600 .env`

### **2. Testnet Testing**
- [ ] Tested bot on **Binance Futures Testnet** for at least 7 days
- [ ] Verified all orders use POST-only (GTX) timeInForce
- [ ] Confirmed NO taker fees are being charged
- [ ] Tested stop loss triggers correctly
- [ ] Tested take profit executes correctly
- [ ] Verified position sizing is correct
- [ ] Tested emergency shutdown works

### **3. Position Limits**
- [ ] Set `MAX_POSITION_USDT` to safe amount (start with $20-50)
- [ ] Verified leverage is appropriate (start with 5-10x, not 20x)
- [ ] Confirmed risk per trade is small (<2% of capital)
- [ ] Tested position capping logic works

### **4. VPS Setup**
- [ ] VPS has stable internet connection
- [ ] VPS is in same region as Binance servers (Singapore/Tokyo for low latency)
- [ ] Firewall configured to allow only SSH and outbound HTTPS
- [ ] SSH key authentication enabled (password auth disabled)
- [ ] Auto-restart systemd service configured
- [ ] Logging is working and disk space monitored

### **5. Monitoring**
- [ ] Set up log monitoring (check every hour initially)
- [ ] Created alerts for errors/exceptions
- [ ] Set up balance monitoring
- [ ] Created emergency contact plan
- [ ] Have mobile access to VPS to kill bot if needed

### **6. Risk Management**
- [ ] Understand maximum loss per trade
- [ ] Calculated maximum daily drawdown
- [ ] Have plan to shut down bot if losses exceed threshold
- [ ] Capital you're trading is money you can afford to lose
- [ ] Tested emergency shutdown procedure

---

## 🔍 POST-Only Order Verification

### **How to Verify POST-Only Orders:**

1. **Check Binance Futures UI:**
   - Look at "Order History" → "Filled Orders"
   - Fee column should show **EXACTLY 0.02%** (maker fee)
   - If you see 0.04%, you have taker orders (BAD!)

2. **Check API Response:**
```python
order = client.futures_create_order(...)
# Should have:
# - 'status': 'NEW' (sitting on book)
# - 'timeInForce': 'GTX'
```

3. **Monitor Rejection Logs:**
```
[ORDER] ❌ POST-only order rejected (would execute as taker)
```
This is GOOD - means your protection is working!

---

## 🚨 Emergency Shutdown Procedures

### **Method 1: Systemd (Recommended)**
```bash
# Stop the bot immediately
sudo systemctl stop trabot

# Cancel all open orders
python -c "from src.trading.live_trader import LiveTrader; LiveTrader.emergency_close_all()"
```

### **Method 2: Manual Binance UI**
1. Log into Binance Futures
2. Go to "Positions"
3. Click "Close All Positions"
4. Go to "Open Orders" → "Cancel All"

### **Method 3: API Script**
```bash
cd ~/trabot
source venv/bin/activate
python deploy/emergency_shutdown.py
```

---

## 📊 Recommended Starting Configuration

### **Conservative Start:**
```env
# .env file
TESTNET=true  # Keep true for 1-2 weeks
LEVERAGE=5    # Start low!
MAX_POSITION_USDT=20.0  # Small size
RISK_PER_TRADE=0.5  # Risk $0.50 per trade
```

### **After 2 Weeks Testnet Success:**
```env
TESTNET=false  # ⚠️ LIVE TRADING
LEVERAGE=10
MAX_POSITION_USDT=50.0
RISK_PER_TRADE=1.0
```

### **After 1 Month Live Success:**
```env
# Gradually increase if profitable
LEVERAGE=15
MAX_POSITION_USDT=100.0
RISK_PER_TRADE=2.0
```

---

## ⚠️ Common Mistakes to Avoid

1. **❌ DON'T** enable "Enable Withdrawals" on API key
2. **❌ DON'T** skip testnet testing
3. **❌ DON'T** start with high leverage (>10x)
4. **❌ DON'T** risk more than 1-2% per trade
5. **❌ DON'T** ignore rejected orders (they're protecting you!)
6. **❌ DON'T** run bot from laptop (use VPS)
7. **❌ DON'T** share API keys or commit them to git
8. **❌ DON'T** forget to set stop losses

---

## 📈 Success Metrics

Track these daily:

| Metric | Target | Action if Failed |
|--------|--------|------------------|
| Win Rate | >50% | Review strategy |
| Maker Fee % | 100% (0.02%) | Check POST-only |
| Max Drawdown | <10% | Reduce position size |
| Daily Trades | 2-5 | Review signal generation |
| API Errors | 0 | Check connection |

---

## 🔐 API Key Permissions (CRITICAL!)

### **✅ REQUIRED Permissions:**
- ✅ Enable Futures

### **❌ FORBIDDEN Permissions:**
- ❌ Enable Withdrawals
- ❌ Enable Spot & Margin Trading (unless needed)
- ❌ Enable Universal Transfer

### **🔒 IP Whitelist:**
- Add ONLY your VPS IP
- Do NOT use "Unrestricted" option

---

## 📞 Emergency Contacts

Keep these handy:

- **VPS Provider Support:** _______________
- **Your Phone (for mobile SSH):** _______________
- **Backup Contact:** _______________
- **Binance Support:** https://www.binance.com/en/support

---

## 📝 Daily Checklist (First Month)

- [ ] Check bot is running: `sudo systemctl status trabot`
- [ ] Review logs for errors: `tail -100 /var/log/trabot.log`
- [ ] Check Binance balance hasn't dropped unexpectedly
- [ ] Verify all filled orders show 0.02% maker fee
- [ ] Review open positions and pending orders
- [ ] Check VPS disk space: `df -h`
- [ ] Verify VPS is running: `uptime`

---

## ⚡ Quick Command Reference

```bash
# Check bot status
sudo systemctl status trabot

# View live logs
tail -f /var/log/trabot.log

# Restart bot
sudo systemctl restart trabot

# Stop bot
sudo systemctl stop trabot

# SSH to VPS
ssh trader@your_vps_ip

# Check Python environment
source ~/trabot/venv/bin/activate
python --version
```

---

**Remember: It's better to make $0 safely than lose $100 quickly!**

Start small, test thoroughly, and scale gradually. 🚀
