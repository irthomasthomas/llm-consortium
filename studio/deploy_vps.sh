#!/usr/bin/env bash
set -euo pipefail

# Deploy Consortium Dashboard to OVH VPS
VPS_HOST="${1:-ovh-vps}"
VPS_USER="${2:-ubuntu}"
VPS_PATH="${3:-~/consortium-dashboard}"
LOCAL_DB="$HOME/.config/io.datasette.llm/consortium_logs.db"
PORT="${4:-8888}"

echo "🚀 Deploying Consortium Dashboard to $VPS_HOST..."

# 1. Create directory on VPS
ssh "$VPS_HOST" "mkdir -p $VPS_PATH"

# 2. Copy server
scp studio/server.py "$VPS_HOST:$VPS_PATH/"

# 3. Sync database (initial copy)
echo "📊 Syncing consortium_logs.db..."
rsync -azP "$LOCAL_DB" "$VPS_HOST:$VPS_PATH/consortium_logs.db"

# 4. Create systemd service
ssh "$VPS_HOST" "cat > /tmp/consortium-dashboard.service << 'SVC'
[Unit]
Description=LLM Consortium Dashboard
After=network.target

[Service]
Type=simple
User=$VPS_USER
WorkingDirectory=$VPS_PATH
Environment=HOME=/home/$VPS_USER
ExecStart=/usr/bin/python3 $VPS_PATH/server.py $PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC
sudo mv /tmp/consortium-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable consortium-dashboard
sudo systemctl restart consortium-dashboard
"

# 5. Create DB sync cron job
ssh "$VPS_HOST" "cat > /tmp/sync_db.sh << 'SYNC'
#!/bin/bash
rsync -azP $LOCAL_DB $VPS_PATH/consortium_logs.db 2>/dev/null
SYNC
chmod +x /tmp/sync_db.sh
(crontab -l 2>/dev/null; echo '*/5 * * * * /tmp/sync_db.sh') | sort -u | crontab -
"

# 6. Check status
echo "📋 Service status:"
ssh "$VPS_HOST" "sudo systemctl status consortium-dashboard --no-pager" 2>&1 | head -10

echo ""
echo "✅ Dashboard deployed to $VPS_HOST:$PORT"
echo "📊 DB sync: every 5 minutes via cron"
