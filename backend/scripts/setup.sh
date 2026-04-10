#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# setup.sh — one-time Phase 1 bootstrap
#
# What this does:
#   1. Generates an RSA-2048 key pair → secrets/
#   2. Computes the KID (first 8 hex chars of SHA-256 of the public key content)
#      — must match the _compute_kid() function in identity/services/jwt_service.py
#   3. Rewrites kong/kong.yml with a Kong consumer that holds the RSA public key
#      so the jwt plugin can verify tokens
#   4. Copies .env.example → .env (if .env doesn't exist yet)
#
# Run from the backend/ directory:
#   bash scripts/setup.sh
#
# Safe to re-run — regenerates keys and rewrites kong.yml each time.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETS_DIR="$BACKEND_DIR/secrets"
KONG_YML="$BACKEND_DIR/kong/kong.yml"

# ── 1. Generate RSA key pair ─────────────────────────────────────────────────
mkdir -p "$SECRETS_DIR"
echo "[setup] Generating RSA-2048 key pair..."
openssl genrsa -out "$SECRETS_DIR/jwt_private_key.pem" 2048 2>/dev/null
openssl rsa \
    -in  "$SECRETS_DIR/jwt_private_key.pem" \
    -pubout \
    -out "$SECRETS_DIR/jwt_public_key.pem" 2>/dev/null

chmod 600 "$SECRETS_DIR/jwt_private_key.pem"
chmod 644 "$SECRETS_DIR/jwt_public_key.pem"
echo "[setup] Keys written to $SECRETS_DIR"

# ── 2. Generate kong/kong.yml via embedded Python ────────────────────────────
# Python matches the kid computation in identity/src/identity/services/jwt_service.py
echo "[setup] Generating kong/kong.yml with consumer credential..."

python3 - "$SECRETS_DIR/jwt_public_key.pem" "$KONG_YML" <<'PYEOF'
import sys
import hashlib
import textwrap

pub_key_path, output_path = sys.argv[1], sys.argv[2]

with open(pub_key_path) as f:
    pub_key_content = f.read()

# Matches _compute_kid() in identity/src/identity/services/jwt_service.py
kid = hashlib.sha256(pub_key_content.encode()).hexdigest()[:8]

# Indent PEM lines to sit inside the YAML literal block (10-space indent)
pem_lines = pub_key_content.strip().splitlines()
# Each line of the PEM gets 10 spaces of indentation in the YAML literal block
indented_pem = "\n".join("          " + line for line in pem_lines)

# ── Full kong.yml ─────────────────────────────────────────────────────────
# The post-function plugin (priority -1000) runs AFTER:
#   jwt plugin (1005)              — verifies RS256 signature + exp
#   request-transformer (801)      — strips anyclient-supplied X-Authenticated-Userid
# so that upstream services receive X-Authenticated-Userid = JWT sub (user UUID).
kong_yml = f"""\
_format_version: "3.0"
_transform: true

services:
  - name: identity-service
    url: http://identity:8000
    routes:
      - name: auth-public
        paths: [/auth/register, /auth/login, /auth/.well-known/jwks.json]
        strip_path: false
        methods: [POST, GET]

  - name: transaction-service
    url: http://transaction:8000
    plugins:
      - name: jwt
        config:
          key_claim_name: kid
          claims_to_verify: [exp]
    routes:
      - name: transactions
        paths: [/transactions]
        strip_path: false
        methods: [GET, POST, PATCH, DELETE]

  - name: journal-service
    url: http://journal:8000
    plugins:
      - name: jwt
        config:
          key_claim_name: kid
          claims_to_verify: [exp]
    routes:
      - name: journal
        paths: [/journal]
        strip_path: false
        methods: [GET, POST, PATCH, DELETE]

  - name: insight-service
    url: http://insight:8000
    plugins:
      - name: jwt
        config:
          key_claim_name: kid
          claims_to_verify: [exp]
      - name: rate-limiting
        config:
          minute: 20       # LLM endpoint — tighter limit
          policy: local
    routes:
      - name: insights
        paths: [/insights]
        strip_path: false
        methods: [GET]

  - name: notification-service
    url: http://notification:8000
    plugins:
      - name: jwt
        config:
          key_claim_name: kid
          claims_to_verify: [exp]
    routes:
      - name: notifications
        paths: [/notifications]
        strip_path: false
        methods: [GET, PATCH]

# ── JWT consumer ──────────────────────────────────────────────────────────────
# One shared consumer for all app-issued tokens.
# The jwt plugin matches the token's `kid` header claim against credential.key.
# After a successful match + signature verification, the post-function plugin
# (below) injects the user UUID from the JWT sub claim as X-Authenticated-Userid.
consumers:
  - username: fw-app
    jwt_secrets:
      - key: {kid}
        algorithm: RS256
        rsa_public_key: |
{indented_pem}

plugins:
  # Inject X-Authenticated-Userid from JWT sub claim.
  # Runs last (post-function priority = -1000), guaranteeing:
  #   - jwt plugin already validated signature + exp
  #   - request-transformer already stripped any client-supplied header (anti-spoof)
  - name: post-function
    config:
      access:
        - |
          local auth = kong.request.get_header("authorization")
          if not auth then return end
          local token = auth:match("^[Bb]earer%s+(.+)$")
          if not token then return end
          local parts = {{}}
          for p in token:gmatch("[^.]+") do parts[#parts + 1] = p end
          if #parts ~= 3 then return end
          local b64 = parts[2]:gsub("%-", "+"):gsub("_", "/")
          local pad = #b64 % 4
          if pad > 0 then b64 = b64 .. string.rep("=", 4 - pad) end
          local decoded = ngx.decode_base64(b64)
          if not decoded then return end
          local ok, data = pcall(require("cjson").decode, decoded)
          if ok and data and data.sub then
            kong.service.request.set_header("X-Authenticated-Userid", data.sub)
          end

  - name: request-transformer
    config:
      remove:
        headers: [X-Consumer-ID, X-Consumer-Username, X-Authenticated-Userid]

  - name: rate-limiting
    config:
      minute: 120
      policy: local

  - name: cors
    config:
      origins: ["http://localhost:3000"]
      methods: [GET, POST, PUT, PATCH, DELETE, OPTIONS]
      headers: [Authorization, Content-Type]
      max_age: 3600

  - name: opentelemetry
    config:
      endpoint: http://jaeger:4318/v1/traces
      resource_attributes:
        service.name: kong-gateway
      propagation:
        default_format: w3c
"""

with open(output_path, "w") as f:
    f.write(kong_yml)

print(f"[setup] kong/kong.yml generated  (KID = {kid})")
PYEOF

# ── 3. Create .env from .env.example ─────────────────────────────────────────
ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"
if [ ! -f "$ENV_FILE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "[setup] .env created from .env.example"
else
    echo "[setup] .env already exists — skipping (delete it to reset)"
fi

# ── 4. Guard: add secrets/ to .gitignore ─────────────────────────────────────
ROOT_GITIGNORE="$(cd "$BACKEND_DIR/.." && pwd)/.gitignore"
BACKEND_GITIGNORE="$BACKEND_DIR/.gitignore"
for GI in "$ROOT_GITIGNORE" "$BACKEND_GITIGNORE"; do
    if [ -f "$GI" ] && ! grep -qF "secrets/" "$GI" 2>/dev/null; then
        echo "secrets/" >> "$GI"
        echo "[setup] Added secrets/ to $GI"
    fi
done

echo ""
echo "────────────────────────────────────"
echo "Setup complete. Next steps:"
echo "  docker compose up --build"
echo "────────────────────────────────────"
