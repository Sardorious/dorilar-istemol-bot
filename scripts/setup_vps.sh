#!/bin/bash
# VPS setup script — Ubuntu 22.04/24.04 da bir marta ishga tushiring
# Usage: bash scripts/setup_vps.sh

set -e

echo "=== Docker o'rnatilmoqda ==="
apt-get update
apt-get install -y ca-certificates curl gnupg git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "=== Loyiha papkasi tayyorlanmoqda ==="
mkdir -p ~/dorilar-bot
cd ~/dorilar-bot

echo "=== Repo clone qilinmoqda ==="
git clone https://github.com/Sardorious/dorilar-istemol-bot.git .

echo "=== .env yaratilmoqda ==="
cp .env.example .env
echo ""
echo "MUHIM: ~/dorilar-bot/.env faylini to'ldiring:"
echo "  BOT_TOKEN=your_bot_token"
echo "  ADMIN_IDS=your_telegram_id"
echo ""
echo "=== Tayyor! .env to'ldirilgandan keyin ==="
echo "  cd ~/dorilar-bot && docker compose up -d"
