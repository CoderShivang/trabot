#!/bin/bash
# VPS Setup Script for TraBot
# Run this on your Ubuntu VPS after cloning the repository

set -e  # Exit on error

echo "================================================"
echo "TraBot VPS Setup Script"
echo "================================================"
echo ""

# Update system
echo "[1/7] Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install Python 3.11
echo "[2/7] Installing Python 3.11..."
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Install system dependencies
echo "[3/7] Installing system dependencies..."
sudo apt install -y build-essential libssl-dev libffi-dev git curl

# Create virtual environment
echo "[4/7] Creating Python virtual environment..."
cd ~/trabot
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "[5/7] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "[6/7] Creating .env file..."
    cat > .env << EOF
# Binance API Credentials
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# Environment Settings
ENVIRONMENT=production
TESTNET=true  # Set to false ONLY when ready for live trading

# Trading Parameters
SYMBOL=BTCUSDT
LEVERAGE=20
MAX_POSITION_USDT=100.0

# Logging
LOG_LEVEL=INFO
EOF
    echo "⚠️  IMPORTANT: Edit .env and add your Binance API credentials!"
    echo "    Run: nano .env"
else
    echo "[6/7] .env file already exists, skipping..."
fi

# Create systemd service
echo "[7/7] Creating systemd service..."
sudo bash -c 'cat > /etc/systemd/system/trabot.service << EOF
[Unit]
Description=TraBot - VWAP Trading Bot
After=network.target

[Service]
Type=simple
User='$USER'
WorkingDirectory='$HOME'/trabot
Environment="PATH='$HOME'/trabot/venv/bin"
ExecStart='$HOME'/trabot/venv/bin/python src/trading/live_trader.py
Restart=always
RestartSec=10

# Logging
StandardOutput=append:/var/log/trabot.log
StandardError=append:/var/log/trabot.error.log

[Install]
WantedBy=multi-user.target
EOF'

# Create log files
sudo touch /var/log/trabot.log /var/log/trabot.error.log
sudo chown $USER:$USER /var/log/trabot.log /var/log/trabot.error.log

# Reload systemd
sudo systemctl daemon-reload

echo ""
echo "================================================"
echo "✅ VPS Setup Complete!"
echo "================================================"
echo ""
echo "Next Steps:"
echo "1. Edit your .env file with API credentials:"
echo "   nano ~/trabot/.env"
echo ""
echo "2. Test the bot manually first:"
echo "   cd ~/trabot"
echo "   source venv/bin/activate"
echo "   python src/trading/live_trader.py"
echo ""
echo "3. Once tested, enable the service:"
echo "   sudo systemctl enable trabot"
echo "   sudo systemctl start trabot"
echo ""
echo "4. Check bot status:"
echo "   sudo systemctl status trabot"
echo ""
echo "5. View logs:"
echo "   tail -f /var/log/trabot.log"
echo ""
echo "⚠️  CRITICAL: Start with TESTNET=true in .env!"
echo "================================================"
