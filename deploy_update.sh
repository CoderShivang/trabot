#!/bin/bash
#
# Safe deployment script for VPS updates
# Usage: ./deploy_update.sh [--no-restart]
#

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Trading Bot Update Script ===${NC}\n"

# Configuration
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$BOT_DIR/venv"
PID_FILE="$BOT_DIR/bot.pid"
BACKUP_DIR="$BOT_DIR/backups"
NO_RESTART=false

# Parse arguments
if [ "$1" == "--no-restart" ]; then
    NO_RESTART=true
fi

# Step 1: Check if bot is running
echo -e "${YELLOW}[1/8] Checking bot status...${NC}"
BOT_RUNNING=false
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        BOT_RUNNING=true
        echo -e "${GREEN}✓ Bot is running (PID: $PID)${NC}"
    else
        echo -e "${YELLOW}⚠ PID file exists but bot not running${NC}"
        rm -f "$PID_FILE"
    fi
else
    echo -e "${YELLOW}⚠ Bot is not running${NC}"
fi

# Step 2: Create backup
echo -e "\n${YELLOW}[2/8] Creating backup...${NC}"
mkdir -p "$BACKUP_DIR"
BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

# Backup critical files
mkdir -p "$BACKUP_PATH"
cp -r "$BOT_DIR/data" "$BACKUP_PATH/" 2>/dev/null || echo "No data directory to backup"
cp "$BOT_DIR/.env" "$BACKUP_PATH/" 2>/dev/null || echo "No .env to backup"
cp "$BOT_DIR/config/bot_config.yaml" "$BACKUP_PATH/" 2>/dev/null || echo "No config to backup"

# Save current git commit
git rev-parse HEAD > "$BACKUP_PATH/commit_hash.txt" 2>/dev/null || echo "unknown" > "$BACKUP_PATH/commit_hash.txt"

echo -e "${GREEN}✓ Backup created at: $BACKUP_PATH${NC}"

# Step 3: Stop the bot gracefully
if [ "$BOT_RUNNING" = true ]; then
    echo -e "\n${YELLOW}[3/8] Stopping bot gracefully...${NC}"

    # Send SIGTERM for graceful shutdown
    kill -TERM "$PID" 2>/dev/null || true

    # Wait up to 30 seconds for graceful shutdown
    for i in {1..30}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Bot stopped gracefully${NC}"
            rm -f "$PID_FILE"
            break
        fi
        sleep 1
        echo -n "."
    done

    # Force kill if still running
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "\n${RED}⚠ Forcing shutdown...${NC}"
        kill -9 "$PID" 2>/dev/null || true
        rm -f "$PID_FILE"
    fi
else
    echo -e "\n${YELLOW}[3/8] Skipping stop (bot not running)${NC}"
fi

# Step 4: Stash any local changes
echo -e "\n${YELLOW}[4/8] Stashing local changes...${NC}"
git stash push -m "Auto-stash before update $(date +%Y%m%d_%H%M%S)" || echo "Nothing to stash"

# Step 5: Pull latest changes
echo -e "\n${YELLOW}[5/8] Pulling latest changes...${NC}"
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Current branch: $CURRENT_BRANCH"

if git pull origin "$CURRENT_BRANCH"; then
    echo -e "${GREEN}✓ Code updated successfully${NC}"
else
    echo -e "${RED}✗ Failed to pull changes${NC}"
    echo -e "${YELLOW}Rolling back...${NC}"
    git reset --hard HEAD
    exit 1
fi

# Step 6: Update dependencies
echo -e "\n${YELLOW}[6/8] Updating dependencies...${NC}"
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
    pip install -q -r requirements.txt --upgrade
    echo -e "${GREEN}✓ Dependencies updated${NC}"
else
    echo -e "${RED}✗ Virtual environment not found${NC}"
    exit 1
fi

# Step 7: Run validation tests
echo -e "\n${YELLOW}[7/8] Running validation tests...${NC}"

# Test Python syntax
python -m py_compile src/**/*.py 2>/dev/null && echo -e "${GREEN}✓ Syntax check passed${NC}" || {
    echo -e "${RED}✗ Syntax errors found${NC}"
    exit 1
}

# Test imports
python -c "
import sys
sys.path.insert(0, 'src')
from config import load_config
from strategy.location_detector import LocationDetector
from learning.ml_optimizer import MLParameterOptimizer
print('✓ Critical imports successful')
" || {
    echo -e "${RED}✗ Import errors found${NC}"
    exit 1
}

# Test config loading
python -c "
import sys
sys.path.insert(0, 'src')
from config import load_config
config = load_config()
print('✓ Configuration loaded successfully')
" || {
    echo -e "${RED}✗ Configuration error${NC}"
    exit 1
}

echo -e "${GREEN}✓ All validation tests passed${NC}"

# Step 8: Restart the bot (unless --no-restart)
if [ "$NO_RESTART" = false ]; then
    echo -e "\n${YELLOW}[8/8] Restarting bot...${NC}"

    # Start bot in background with nohup
    nohup python main.py > logs/bot_$(date +%Y%m%d).log 2>&1 &
    NEW_PID=$!
    echo $NEW_PID > "$PID_FILE"

    # Wait 5 seconds and check if it's still running
    sleep 5
    if ps -p "$NEW_PID" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Bot restarted successfully (PID: $NEW_PID)${NC}"
    else
        echo -e "${RED}✗ Bot failed to start${NC}"
        echo -e "${YELLOW}Check logs/bot_$(date +%Y%m%d).log for errors${NC}"
        exit 1
    fi
else
    echo -e "\n${YELLOW}[8/8] Skipping restart (--no-restart flag)${NC}"
fi

echo -e "\n${GREEN}=== Update Complete ===${NC}"
echo -e "Backup location: $BACKUP_PATH"
echo -e "Log file: logs/bot_$(date +%Y%m%d).log"

# Keep only last 10 backups
echo -e "\n${YELLOW}Cleaning old backups (keeping last 10)...${NC}"
cd "$BACKUP_DIR"
ls -t | tail -n +11 | xargs rm -rf 2>/dev/null || true
