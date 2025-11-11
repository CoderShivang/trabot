#!/bin/bash
#
# Bot control script - start, stop, restart, status
# Usage: ./bot_control.sh [start|stop|restart|status|logs]
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$BOT_DIR/bot.pid"
LOG_FILE="$BOT_DIR/logs/bot_$(date +%Y%m%d).log"
VENV_DIR="$BOT_DIR/venv"

# Ensure logs directory exists
mkdir -p "$BOT_DIR/logs"

# Function to get bot PID
get_bot_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    else
        echo ""
    fi
}

# Function to check if bot is running
is_bot_running() {
    PID=$(get_bot_pid)
    if [ -n "$PID" ] && ps -p "$PID" > /dev/null 2>&1; then
        return 0  # Running
    else
        return 1  # Not running
    fi
}

# Function to start bot
start_bot() {
    echo -e "${YELLOW}Starting trading bot...${NC}"

    if is_bot_running; then
        echo -e "${RED}✗ Bot is already running (PID: $(get_bot_pid))${NC}"
        exit 1
    fi

    # Activate virtual environment
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
    else
        echo -e "${RED}✗ Virtual environment not found${NC}"
        exit 1
    fi

    # Start bot in background
    cd "$BOT_DIR"
    nohup python main.py > "$LOG_FILE" 2>&1 &
    NEW_PID=$!
    echo $NEW_PID > "$PID_FILE"

    # Wait and verify
    sleep 3
    if is_bot_running; then
        echo -e "${GREEN}✓ Bot started successfully (PID: $NEW_PID)${NC}"
        echo -e "Log file: $LOG_FILE"
    else
        echo -e "${RED}✗ Bot failed to start${NC}"
        echo -e "Check log file: $LOG_FILE"
        exit 1
    fi
}

# Function to stop bot
stop_bot() {
    echo -e "${YELLOW}Stopping trading bot...${NC}"

    if ! is_bot_running; then
        echo -e "${YELLOW}⚠ Bot is not running${NC}"
        rm -f "$PID_FILE"
        exit 0
    fi

    PID=$(get_bot_pid)
    echo "Sending graceful shutdown signal to PID $PID..."

    # Send SIGTERM
    kill -TERM "$PID" 2>/dev/null || true

    # Wait up to 30 seconds
    for i in {1..30}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Bot stopped gracefully${NC}"
            rm -f "$PID_FILE"
            exit 0
        fi
        sleep 1
        echo -n "."
    done

    # Force kill
    echo -e "\n${YELLOW}Forcing shutdown...${NC}"
    kill -9 "$PID" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo -e "${GREEN}✓ Bot stopped (forced)${NC}"
}

# Function to restart bot
restart_bot() {
    stop_bot
    sleep 2
    start_bot
}

# Function to show status
show_status() {
    if is_bot_running; then
        PID=$(get_bot_pid)
        echo -e "${GREEN}● Bot is RUNNING${NC}"
        echo -e "PID: $PID"
        echo -e "Uptime: $(ps -p $PID -o etime= 2>/dev/null | xargs)"
        echo -e "Memory: $(ps -p $PID -o rss= 2>/dev/null | awk '{printf "%.1f MB", $1/1024}')"
        echo -e "CPU: $(ps -p $PID -o %cpu= 2>/dev/null | xargs)%"
        echo -e "Log file: $LOG_FILE"

        # Show recent trades count
        if [ -f "$BOT_DIR/data/trades.json" ]; then
            TRADE_COUNT=$(cat "$BOT_DIR/data/trades.json" | grep -o "trade_id" | wc -l)
            echo -e "Total trades: $TRADE_COUNT"
        fi
    else
        echo -e "${RED}● Bot is STOPPED${NC}"
        if [ -f "$PID_FILE" ]; then
            echo -e "${YELLOW}⚠ Stale PID file found${NC}"
        fi
    fi
}

# Function to show logs
show_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}=== Recent Logs (last 50 lines) ===${NC}\n"
        tail -n 50 "$LOG_FILE"
        echo -e "\n${YELLOW}=== End of Logs ===${NC}"
        echo -e "Full log: $LOG_FILE"
    else
        echo -e "${YELLOW}No log file found for today${NC}"
        echo -e "Expected location: $LOG_FILE"
    fi
}

# Main
case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the trading bot"
        echo "  stop    - Stop the trading bot gracefully"
        echo "  restart - Restart the trading bot"
        echo "  status  - Show bot status and stats"
        echo "  logs    - Show recent logs"
        exit 1
        ;;
esac
