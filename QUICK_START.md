# 🚀 TraBot Quick Start Guide

## What Are POST-Only Orders?

**POST-only orders = Maker orders ONLY**

| Feature | Market Order | Regular Limit | POST-Only (GTX) |
|---------|--------------|---------------|-----------------|
| **Execution** | Immediate | Immediate OR book | Book ONLY |
| **Fee Type** | Taker | Taker OR Maker | Maker ONLY |
| **Fee Rate** | 0.04% | 0.02-0.04% | 0.02% |
| **Rejected if crosses** | No | No | ✅ YES |

### Example:
```
BTC Price: $95,000

LONG @ $94,950 (below market):
✅ Order sits on book → Fills as maker → 0.02% fee

LONG @ $95,050 (above market):
❌ Would execute immediately → REJECTED → Prevents 0.04% fee!
```

**This rejection is GOOD** - it saves you 2x fees!

---

## VPS Deployment in 5 Steps

### **1. Get a VPS**
```bash
# Recommended: DigitalOcean Droplet
# - $6/month
# - Ubuntu 22.04
# - Singapore datacenter
# - 1GB RAM, 1 vCPU
```

### **2. SSH into VPS**
```bash
ssh root@your_vps_ip
```

### **3. Run Setup Script**
```bash
# Clone repo
git clone https://github.com/CoderShivang/trabot.git
cd trabot

# Run automated setup
chmod +x deploy/vps_setup.sh
./deploy/vps_setup.sh
```

### **4. Configure API Keys**
```bash
nano .env
```

Add:
```env
BINANCE_API_KEY=your_testnet_key
BINANCE_API_SECRET=your_testnet_secret
TESTNET=true  # Start with testnet!
```

### **5. Start Bot**
```bash
# Test manually first
source venv/bin/activate
python src/trading/live_trader.py

# Then enable service
sudo systemctl enable trabot
sudo systemctl start trabot
```

---

## File Structure

```
trabot/
├── deploy/
│   ├── DEPLOYMENT_GUIDE.md      ← Full deployment guide
│   ├── SAFETY_CHECKLIST.md      ← Safety requirements
│   ├── vps_setup.sh             ← Automated VPS setup
│   └── emergency_shutdown.py    ← Emergency kill switch
├── src/
│   └── trading/
│       └── live_trader.py       ← Live trading module
└── QUICK_START.md               ← This file
```

---

## How POST-Only Works in Code

```python
from src.trading.live_trader import LiveTrader

# Initialize trader (testnet first!)
trader = LiveTrader(
    api_key='your_key',
    api_secret='your_secret',
    testnet=True,  # ← Always start with testnet!
    max_position_usdt=20.0,
    leverage=5
)

# Place POST-only order
trader.place_post_only_order(
    side='BUY',
    price=94950.0,  # Below market
    quantity=0.001,
    reduce_only=False
)
# ✅ Order uses timeInForce='GTX'
# ✅ Gets rejected if would execute as taker
# ✅ Guarantees 0.02% maker fee
```

---

## Critical Commands

### **Monitor Bot**
```bash
# Check status
sudo systemctl status trabot

# View live logs
tail -f /var/log/trabot.log

# Check for errors
grep "ERROR" /var/log/trabot.log
```

### **Emergency Shutdown**
```bash
# Method 1: Stop service
sudo systemctl stop trabot

# Method 2: Emergency script
cd ~/trabot
source venv/bin/activate
python deploy/emergency_shutdown.py
```

### **Verify POST-Only Orders**
```bash
# Check logs for GTX
grep "timeInForce.*GTX" /var/log/trabot.log

# Check for rejections (this is GOOD!)
grep "POST-only order rejected" /var/log/trabot.log
```

---

## Safety Checklist

Before going live:

- [ ] Tested on **testnet** for 1-2 weeks
- [ ] All orders verified as POST-only (0.02% fees)
- [ ] API key has **withdrawals DISABLED**
- [ ] API key has **IP whitelist** enabled
- [ ] Starting with **small positions** ($20-50)
- [ ] Starting with **low leverage** (5-10x)
- [ ] Emergency shutdown tested
- [ ] Have mobile SSH access

---

## Monitoring Dashboard

### **Daily Checks:**
```bash
# 1. Check bot is running
sudo systemctl status trabot

# 2. Check recent trades
tail -50 /var/log/trabot.log | grep "EXIT"

# 3. Verify maker fees
# Log into Binance → Order History
# All orders should show 0.02% fee (not 0.04%!)

# 4. Check balance
python -c "from binance.client import Client; c = Client('key', 'secret'); print(c.futures_account_balance())"
```

---

## Troubleshooting

### **"API key invalid"**
- Check .env file has correct keys
- Verify IP whitelist includes VPS IP
- Ensure "Enable Futures" permission is enabled

### **Orders not filling**
- For LONG: price must be BELOW market
- For SHORT: price must be ABOVE market
- Check Binance UI for open orders

### **"POST-only order rejected"**
- **This is normal and GOOD!**
- It means order would execute as taker
- Bot is protecting you from 2x fees

### **Bot keeps crashing**
```bash
# Check logs
sudo journalctl -u trabot -n 100

# Test manually
cd ~/trabot
source venv/bin/activate
python src/trading/live_trader.py
```

---

## Next Steps

1. **Read Full Documentation:**
   - `deploy/DEPLOYMENT_GUIDE.md` - Complete deployment walkthrough
   - `deploy/SAFETY_CHECKLIST.md` - Critical safety requirements

2. **Set Up Binance Testnet:**
   - Go to https://testnet.binancefuture.com
   - Generate API key
   - Add to .env with TESTNET=true

3. **Test on Testnet for 1-2 Weeks:**
   - Verify all orders are POST-only
   - Check stop losses work
   - Monitor for any errors

4. **Go Live (Only After Success):**
   - Create live API key with security settings
   - Update .env with TESTNET=false
   - Start with small positions

---

## Key Files to Read

| File | Purpose | Priority |
|------|---------|----------|
| `deploy/DEPLOYMENT_GUIDE.md` | Step-by-step VPS setup | ⭐⭐⭐ HIGH |
| `deploy/SAFETY_CHECKLIST.md` | Safety requirements | ⭐⭐⭐ HIGH |
| `src/trading/live_trader.py` | Live trading code | ⭐⭐ MEDIUM |
| `deploy/vps_setup.sh` | Automated VPS setup | ⭐ LOW |

---

## Support

- **Binance API Docs:** https://binance-docs.github.io/apidocs/futures/en/
- **Python-Binance:** https://python-binance.readthedocs.io/
- **Binance Support:** https://www.binance.com/en/support

---

**Remember:**
1. **Always test on testnet first!**
2. **POST-only orders protect you from high fees**
3. **Start small and scale gradually**
4. **Never enable withdrawal permissions on API key**

Good luck! 🚀
