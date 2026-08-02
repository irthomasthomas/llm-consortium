#!/bin/bash
# Sync consortium_logs.db to VPS without full redeployment
set -euo pipefail

VPS_HOST="ovh-vps"
REMOTE_DIR="/opt/consortium-dashboard"
DB_PATH="$HOME/.config/io.datasette.llm/consortium_logs.db"

if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Database not found at $DB_PATH"
    exit 1
fi

echo "Syncing database to VPS..."
rsync -avz --progress "$DB_PATH" "$VPS_HOST:$REMOTE_DIR/data/"
echo "Database synced successfully"
echo "Size: $(du -h "$DB_PATH" | cut -f1)"
