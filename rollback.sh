#!/bin/bash
#
# Emergency rollback script
# Usage: ./rollback.sh [backup_name]
#        ./rollback.sh                    (lists available backups)
#        ./rollback.sh backup_20250111_143000
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$BOT_DIR/backups"
PID_FILE="$BOT_DIR/bot.pid"

# If no argument, list available backups
if [ -z "$1" ]; then
    echo -e "${YELLOW}=== Available Backups ===${NC}\n"

    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A $BACKUP_DIR)" ]; then
        echo -e "${RED}No backups found${NC}"
        exit 1
    fi

    cd "$BACKUP_DIR"
    for backup in $(ls -t); do
        if [ -f "$backup/commit_hash.txt" ]; then
            COMMIT=$(cat "$backup/commit_hash.txt")
            echo -e "${GREEN}$backup${NC} (commit: ${COMMIT:0:7})"
        else
            echo -e "${GREEN}$backup${NC}"
        fi
    done

    echo -e "\nUsage: ./rollback.sh <backup_name>"
    exit 0
fi

BACKUP_NAME="$1"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

# Verify backup exists
if [ ! -d "$BACKUP_PATH" ]; then
    echo -e "${RED}✗ Backup not found: $BACKUP_NAME${NC}"
    exit 1
fi

echo -e "${YELLOW}=== Rolling Back to: $BACKUP_NAME ===${NC}\n"

# Stop bot if running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}Stopping bot...${NC}"
        kill -TERM "$PID" 2>/dev/null || true
        sleep 3
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
        echo -e "${GREEN}✓ Bot stopped${NC}"
    fi
fi

# Rollback git commit
if [ -f "$BACKUP_PATH/commit_hash.txt" ]; then
    COMMIT=$(cat "$BACKUP_PATH/commit_hash.txt")
    if [ "$COMMIT" != "unknown" ]; then
        echo -e "\n${YELLOW}Rolling back git to commit: ${COMMIT:0:7}${NC}"
        git reset --hard "$COMMIT"
        echo -e "${GREEN}✓ Code rolled back${NC}"
    fi
fi

# Restore data files
if [ -d "$BACKUP_PATH/data" ]; then
    echo -e "\n${YELLOW}Restoring data files...${NC}"
    rm -rf "$BOT_DIR/data"
    cp -r "$BACKUP_PATH/data" "$BOT_DIR/"
    echo -e "${GREEN}✓ Data restored${NC}"
fi

# Restore .env
if [ -f "$BACKUP_PATH/.env" ]; then
    echo -e "\n${YELLOW}Restoring .env...${NC}"
    cp "$BACKUP_PATH/.env" "$BOT_DIR/"
    echo -e "${GREEN}✓ Environment restored${NC}"
fi

# Restore config
if [ -f "$BACKUP_PATH/bot_config.yaml" ]; then
    echo -e "\n${YELLOW}Restoring configuration...${NC}"
    cp "$BACKUP_PATH/bot_config.yaml" "$BOT_DIR/config/"
    echo -e "${GREEN}✓ Configuration restored${NC}"
fi

# Reinstall dependencies
echo -e "\n${YELLOW}Reinstalling dependencies...${NC}"
source "$BOT_DIR/venv/bin/activate"
pip install -q -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"

echo -e "\n${GREEN}=== Rollback Complete ===${NC}"
echo -e "Run ${YELLOW}./bot_control.sh start${NC} to restart the bot"
