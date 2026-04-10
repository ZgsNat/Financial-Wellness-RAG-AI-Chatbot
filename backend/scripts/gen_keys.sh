#!/usr/bin/env bash
# Run from backend/ directory: bash scripts/gen-keys.sh
set -euo pipefail

SECRETS_DIR="$(dirname "$0")/../secrets"
mkdir -p "$SECRETS_DIR"

echo "Generating RSA-2048 key pair..."
openssl genrsa -out "$SECRETS_DIR/jwt_private_key.pem" 2048
openssl rsa -in "$SECRETS_DIR/jwt_private_key.pem" \
            -pubout \
            -out "$SECRETS_DIR/jwt_public_key.pem"

chmod 600 "$SECRETS_DIR/jwt_private_key.pem"
chmod 644 "$SECRETS_DIR/jwt_public_key.pem"

echo "Done. Keys written to $SECRETS_DIR"
echo ""
echo "IMPORTANT: ensure secrets/ is in .gitignore"

# Append to .gitignore if not already there
GITIGNORE="$(dirname "$0")/../../.gitignore"
if ! grep -q "secrets/" "$GITIGNORE" 2>/dev/null; then
    echo "secrets/" >> "$GITIGNORE"
    echo "Added secrets/ to .gitignore"
fi