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

# Seed documents carry relative-time placeholders rather than literal timestamps.
# Providers bound how old a document may be before it stops being served (sports
# filters on the event date against `event_ttl_weeks`), so hard-coded fixture dates
# silently stop matching some weeks after they are authored. Rendering them at seed
# time keeps the fixtures inside those windows however long after authoring they load.
now=$(date -u +%s)
iso_at() {
  date -u -d "@$((now + $1))" +%Y-%m-%dT%H:%M:%S+00:00
}

render_seed() {
  sed \
    -e "s/__T_NOW__/$(iso_at 0)/g" \
    -e "s/__T_MINUS_1H__/$(iso_at -3600)/g" \
    -e "s/__T_MINUS_1D__/$(iso_at -86400)/g" \
    -e "s/__T_MINUS_2D__/$(iso_at -172800)/g" \
    -e "s/__T_PLUS_1D__/$(iso_at 86400)/g" \
    -e "s/__T_PLUS_1Y__/$(iso_at 31536000)/g" \
    "$1"
}

for file in /es-seed/*.ndjson; do
  echo ""
  echo "--- Seeding: $file ---"
  render_seed "$file" > /tmp/seed.ndjson
  curl -v -X POST "$ES_URL/_bulk" \
    -H "Content-Type: application/x-ndjson" \
    --data-binary "@/tmp/seed.ndjson" 2>&1
  echo ""
done

echo "--- Seeding complete ---"

# Due to negative refresh interval in index
echo "--- Refreshing indices ---"
curl -s -X POST "$ES_URL/_refresh" | cat
echo ""
echo "--- Done ---"
