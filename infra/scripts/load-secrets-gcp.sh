#!/usr/bin/env bash
# GCP Secret Manager から secret.env 形式のペイロードを取得し、compose / make 用に書き出す。
# シークレット値は標準出力に出さない。
set -euo pipefail

BOOTSTRAP="${XDG_CONFIG_HOME:-$HOME/.config}/cursor/gcp-bootstrap.env"
if [[ -f "$BOOTSTRAP" ]]; then
  # shellcheck disable=SC1090
  source "$BOOTSTRAP"
fi

GCP_PROJECT="${GCP_PROJECT:-}"
GSM_SECRET_NAME="${GSM_SECRET_NAME:-cursor-secret}"
SECRETS_OUT="${SECRETS_OUT:-$HOME/.cursor/secrets/secret.env}"

if [[ -z "$GCP_PROJECT" ]]; then
  GCP_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "$GCP_PROJECT" || "$GCP_PROJECT" == "(unset)" ]]; then
  echo "load-secrets-gcp: GCP_PROJECT が未設定です (~/.config/cursor/gcp-bootstrap.env または gcloud config)" >&2
  exit 1
fi

mkdir -p "$(dirname "$SECRETS_OUT")"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

if ! gcloud secrets versions access latest \
  --secret="$GSM_SECRET_NAME" \
  --project="$GCP_PROJECT" >"$tmp" 2>/dev/null; then
  echo "load-secrets-gcp: Secret Manager から取得できませんでした (secret=$GSM_SECRET_NAME project=$GCP_PROJECT)" >&2
  exit 1
fi

mv "$tmp" "$SECRETS_OUT"
chmod 600 "$SECRETS_OUT"
trap - EXIT
echo "load-secrets-gcp: wrote $SECRETS_OUT (contents not shown)"
