#!/bin/bash
# Start local services for navigational suggestions development

set -e

echo "Starting local services for navigational suggestions testing..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "❌ Docker is not running. Please start Docker and try again."
  exit 1
fi

# Create directories for volume mounts if needed
mkdir -p ./local_data/gcs_emulator

# Start the fake-GCS-server
echo "Starting fake-GCS-server..."
docker-compose -f dev/docker-compose.yaml up -d fake-gcs

# Wait for services to be ready
echo "Waiting for service to be available..."
sleep 3

echo "✅ Service started successfully!"
echo ""
echo "You can now run the navigational suggestions job locally with:"
echo "    uv run merino-jobs navigational-suggestions prepare-domain-metadata --local --sample-size=20"
echo ""
echo "When you're done, stop the service with:"
echo "    docker-compose -f dev/docker-compose.yaml down"
