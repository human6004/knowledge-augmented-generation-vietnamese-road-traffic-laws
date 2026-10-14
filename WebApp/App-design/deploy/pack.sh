#!/usr/bin/env bash
# Đóng gói image + compose + script cài đặt thành MỘT tệp để chia sẻ (không cần mạng ở máy nhận)
set -euo pipefail
cd "$(dirname "$0")"
source .env
OUT=../dist/kag-legal-bundle-$TAG
rm -rf "$OUT" && mkdir -p "$OUT/images"
IMAGES=$(docker compose --env-file .env config --images)
echo "→ docker save: $IMAGES"
docker save $IMAGES | gzip -1 > "$OUT/images/kag-legal-$TAG.tar.gz"
cp docker-compose.yml env.example install.sh install.ps1 "$OUT/"
mkdir -p "$OUT/dumps"
mkdir -p "$OUT/app" && cp app/kag_config.yaml "$OUT/app/" 2>/dev/null || true
cp dumps/*.dump "$OUT/dumps/" 2>/dev/null || echo "(không có dump — bỏ qua)"
# Máy nhận không build lại: bỏ các khối build: khỏi compose
sed -i.bak '/^    build:/d' "$OUT/docker-compose.yml" && rm "$OUT/docker-compose.yml.bak"
(cd "$OUT" && sha256sum images/* dumps/* 2>/dev/null > SHA256SUMS || true)
tar -C ../dist -czf "$OUT.tar.gz" "$(basename "$OUT")"
echo "✓ Gói chia sẻ: $OUT.tar.gz ($(du -h "$OUT.tar.gz" | cut -f1))"
