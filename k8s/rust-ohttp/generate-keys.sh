#!/bin/bash
set -e

echo "Generating OHTTP keys and certificates..."

# Save current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Script directory: $SCRIPT_DIR"

# Create temporary directory
TMP_DIR=$(mktemp -d)
echo "Working in: $TMP_DIR"
cd "$TMP_DIR"

# Clone and build ohttp
git clone https://github.com/martinthomson/ohttp.git
cd ohttp
# PATCH: Remove any line that overwrites server.crt with parsed output
sed -i.bak '/-text -noout >/d' ohttp-server/ca.sh

cargo build --bin ohttp-server --release

# Generate certificates
cd ohttp-server
./ca.sh localhost

# Start server briefly to extract config - no flags, just address
echo "Starting server to extract config..."
../target/release/ohttp-server 127.0.0.1:9443 > server.log 2>&1 &
SERVER_PID=$!
sleep 3

# Capture the server log before killing
echo "Server log contents:"
cat server.log

# Extract config - looking for the exact output format from the server code
CONFIG=$(grep -E "^Config: " server.log | head -1 | cut -d ' ' -f 2)
if [ -z "$CONFIG" ]; then
    # Fallback to any long hex string if the specific pattern isn't found
    CONFIG=$(grep -o -E '[0-9a-fA-F]{20,}' server.log | head -1)
fi

# Kill server
kill $SERVER_PID 2>/dev/null || true
sleep 1

# Display what was found
echo "Extracted config: $CONFIG"

# Copy only PEM files and ca.sh back to k8s directory
echo "Copying certificates to: $SCRIPT_DIR/certs/"
mkdir -p "$SCRIPT_DIR/certs"
cp server.crt server.key ca.crt ca.sh "$SCRIPT_DIR/certs/"
echo "$CONFIG" > "$SCRIPT_DIR/config.hex"

# Verify PEM format
echo "Verifying PEM format:"
head -2 "$SCRIPT_DIR/certs/server.crt"
head -2 "$SCRIPT_DIR/certs/server.key"

cd "$SCRIPT_DIR"
rm -rf "$TMP_DIR"

echo "Keys generated successfully!"
echo "Config saved to: $SCRIPT_DIR/config.hex"
echo "Certificates saved to: $SCRIPT_DIR/certs/"
