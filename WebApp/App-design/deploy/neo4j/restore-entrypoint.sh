#!/bin/bash
# Lần chạy đầu: nếu có dump và database chưa có dữ liệu thì nạp dump, sau đó chạy neo4j bình thường.
set -e
if [ -f "$RESTORE_DUMP" ] && [ ! -f /data/.restored ]; then
  echo "[kag] Nạp đồ thị từ $RESTORE_DUMP ..."
  mkdir -p /tmp/dump && cp "$RESTORE_DUMP" /tmp/dump/neo4j.dump
  neo4j-admin database load neo4j --from-path=/tmp/dump --overwrite-destination=true
  touch /data/.restored
fi
exec /startup/docker-entrypoint.sh "$@"
