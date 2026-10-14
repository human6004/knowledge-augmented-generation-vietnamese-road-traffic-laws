#!/usr/bin/env bash
# Build toàn bộ image của hệ thống từ deploy/
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || cp env.example .env
docker compose --env-file .env build --pull
docker compose --env-file .env images
echo "✓ Đã build: mysql, neo4j, minio, server, app, web"
