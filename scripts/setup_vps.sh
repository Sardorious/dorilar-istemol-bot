#!/bin/bash
# VPS setup script — run once on fresh Ubuntu 22.04/24.04 server
# Usage: bash scripts/setup_vps.sh

set -e

echo "=== Installing Docker ==="
apt-get update
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "=== Setting up project directory ==="
mkdir -p /opt/dorilar-bot
cd /opt/dorilar-bot

echo "=== Cloning repo ==="
git clone https://github.com/Sardorious/dorilar-istemol-bot.git .

echo "=== Creating .env (fill in values!) ==="
cp .env.example .env
echo ""
echo "IMPORTANT: Edit /opt/dorilar-bot/.env with your values:"
echo "  BOT_TOKEN=your_bot_token"
echo "  ADMIN_IDS=your_telegram_id"
echo ""

echo "=== Done! After editing .env, run: ==="
echo "  cd /opt/dorilar-bot && docker compose up -d"
