#!/bin/sh
# Tham số lấy từ biến môi trường thay vì viết cứng trong compose.
G="neo4j://neo4j:7687?user=neo4j&password=${NEO4J_PASSWORD}&database=neo4j"
exec java -Dfile.encoding=UTF-8 -Xms${SERVER_XMS:-2048m} -Xmx${SERVER_XMX:-8192m} \
  -jar arks-sofaboot-0.0.1-SNAPSHOT-executable.jar \
  --server.repository.impl.jdbc.host=mysql \
  --server.repository.impl.jdbc.password=${MYSQL_PASSWORD} \
  --builder.model.execute.num=20 \
  --cloudext.graphstore.url="$G" \
  --cloudext.searchengine.url="$G"
