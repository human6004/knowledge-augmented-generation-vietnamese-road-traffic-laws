#!/usr/bin/env bash
# Chạy trên máy bạn bè: giải nén gói rồi ./install.sh
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo "Cần cài Docker trước"; exit 1; }
[ -f SHA256SUMS ] && sha256sum -c SHA256SUMS
echo "→ Nạp image (không cần tải từ internet)"
for f in images/*.tar.gz; do gunzip -c "$f" | docker load; done
[ -f .env ] || { cp env.example .env; echo "⚠ Đã tạo .env — hãy đổi mật khẩu/API key rồi chạy lại nếu cần"; }
docker compose --env-file .env up -d
echo "→ Chờ các dịch vụ healthy..."
for i in $(seq 1 60); do
  BAD=$(docker compose ps --format '{{.Health}}' | grep -vc healthy || true)
  [ "$BAD" = "0" ] && break; sleep 5
done
docker compose ps
echo "✓ OpenSPG: http://localhost:8887  ·  Web: http://localhost:8080"
