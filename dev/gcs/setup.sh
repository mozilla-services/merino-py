#!/bin/sh
# Seeds the local fake-GCS emulator with the merino-images-local bucket,
# logo files, and the logo manifest.
set -e

GCS_URL="http://fake-gcs:4443"
BUCKET="merino-images-local"

echo "Waiting for fake-gcs to be ready..."
curl -sf --retry 10 --retry-delay 2 --retry-connrefused \
  "$GCS_URL/storage/v1/b?project=local" > /dev/null
echo "fake-gcs is ready."

echo "Creating bucket '$BUCKET'..."
curl -sf -X POST "$GCS_URL/storage/v1/b?project=local" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$BUCKET\"}"
echo ""

# Upload each logo, inferring the league subdirectory from the filename prefix
# e.g. mlb_bal.png -> logos/mlb/mlb_bal.png
for file in /gcs/logos/*.png; do
  filename=$(basename "$file")
  league=$(echo "$filename" | cut -d'_' -f1)
  object="logos/$league/$filename"
  echo "Uploading $object..."
  curl -sf -X POST \
    "$GCS_URL/upload/storage/v1/b/$BUCKET/o?uploadType=media&name=$object" \
    -H "Content-Type: image/png" \
    --data-binary "@$file"
  echo ""
done

# Upload the manifest to the path the logos provider expects
echo "Uploading logos/logo_manifest_latest.json..."
curl -sf -X POST \
  "$GCS_URL/upload/storage/v1/b/$BUCKET/o?uploadType=media&name=logos/logo_manifest_latest.json" \
  -H "Content-Type: application/json" \
  --data-binary "@/gcs/logos/logo_manifest_latest.json"
echo ""

echo "GCS seed complete."
