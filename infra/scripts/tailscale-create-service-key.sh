#!/usr/bin/env bash
# tag:bananacraft 付き再利用可能 TS_AUTHKEY を API 発行し secret.env に追記
set -euo pipefail

SECRETS="${SECRETS_ENV:-$HOME/.cursor/secrets/secret.env}"
TAG="${TAILSCALE_TAG:-tag:bananacraft}"

if [[ ! -f "$SECRETS" ]]; then
  echo "Missing $SECRETS — run infra/push-secret-env.ps1 from Windows first." >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "$SECRETS"
set +a

TAILNET="${TAILNET:-}"
if [[ -z "$TAILNET" ]]; then
  echo "TAILNET not set in $SECRETS (e.g. qilin-scala.ts.net)" >&2
  exit 1
fi

if [[ -n "${TS_AUTHKEY:-}" && ${#TS_AUTHKEY} -gt 20 ]]; then
  echo "TS_AUTHKEY already set in $SECRETS — skip API (clear value to re-issue)"
  exit 0
fi

tailscale_api_token() {
  local api_token="${TS_API_ACCESS_TOKEN:-}"
  local oauth_id="${TS_OAUTH_CLIENT_ID:-}"
  local oauth_secret="${TS_OAUTH_CLIENT_SECRET:-}"

  if [[ -n "$api_token" && "$api_token" == tskey-api-* ]]; then
    echo "$api_token"
    return 0
  fi

  if [[ -z "$oauth_secret" && -n "$api_token" && "$api_token" == tskey-client-* ]]; then
    oauth_secret="$api_token"
  fi

  if [[ -z "$oauth_secret" ]]; then
    echo "Set TS_API_ACCESS_TOKEN (tskey-api-...) or TS_OAUTH_CLIENT_ID + TS_OAUTH_CLIENT_SECRET" >&2
    return 1
  fi

  if [[ -z "$oauth_id" && "$oauth_secret" == tskey-client-* ]]; then
    oauth_id="${oauth_secret#tskey-client-}"
    oauth_id="${oauth_id%%-*}"
  fi

  if [[ -z "$oauth_id" ]]; then
    echo "TS_OAUTH_CLIENT_ID required when using OAuth client secret" >&2
    return 1
  fi

  curl -sf -d "client_id=${oauth_id}" \
    -d "client_secret=${oauth_secret}" \
    -d "grant_type=client_credentials" \
    "https://api.tailscale.com/api/v2/oauth/token" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

API_TOKEN=$(tailscale_api_token) || exit 1

BODY=$(cat <<EOF
{
  "capabilities": {
    "devices": {
      "create": {
        "reusable": true,
        "ephemeral": false,
        "preauthorized": true,
        "tags": ["${TAG}"]
      }
    }
  },
  "expirySeconds": 7776000
}
EOF
)

KEYS_RESP=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$BODY" \
  "https://api.tailscale.com/api/v2/tailnet/${TAILNET}/keys")
HTTP_CODE=$(echo "$KEYS_RESP" | tail -1)
RESP=$(echo "$KEYS_RESP" | sed '$d')

if [[ "$HTTP_CODE" != "200" ]]; then
  MSG=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message',''))" 2>/dev/null || true)
  if [[ "$MSG" == *"invalid or not permitted"* ]] || [[ "$MSG" == *"tags"* ]]; then
    echo "ACL に tag:bananacraft の tagOwners が無いため API 発行をスキップします。" >&2
    echo "Admin → Access controls に追加後、make tailscale-keys を再実行してください。" >&2
    oauth_secret="${TS_OAUTH_CLIENT_SECRET:-${TS_API_ACCESS_TOKEN:-}}"
    if [[ "$oauth_secret" == tskey-client-* ]]; then
      KEY="$oauth_secret"
      echo "暫定: OAuth client secret を TS_AUTHKEY として使用します。"
    else
      echo "API error ($HTTP_CODE): $MSG" >&2
      exit 1
    fi
  else
    echo "API error ($HTTP_CODE): $MSG" >&2
    exit 1
  fi
else
  KEY=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
fi

if grep -q '^TS_AUTHKEY=' "$SECRETS" 2>/dev/null; then
  sed -i "s|^TS_AUTHKEY=.*|TS_AUTHKEY=${KEY}|" "$SECRETS"
else
  printf '\nTS_AUTHKEY=%s\n' "$KEY" >> "$SECRETS"
fi

chmod 600 "$SECRETS"
echo "Wrote TS_AUTHKEY to $SECRETS (tag ${TAG}). Re-run push-secret-env.ps1 to sync OneDrive if needed."
