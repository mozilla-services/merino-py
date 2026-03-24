#!/bin/bash
set -e
ES_URL="http://es01:9200"

echo " --- Connecting to $ES_URL ---"
curl -v "$ES_URL/_cluster/health" 2>&1 || true

for file in /es-indexes/*.json; do
  index=$(basename "$file" .json)
  echo ""
  echo "--- Creating index: $index ---"
  curl -v -X PUT "$ES_URL/$index" \
    -H "Content-Type: application/json" \
    --data "@$file" 2>&1
  echo ""
done

echo "--- Index creation complete ---"
