#!/usr/bin/env bash
# Clone or pull github.com/flll/skills and link into ~/.cursor/skills
# Requires: gh auth login（GITHUB_TOKEN は secret.env に載せない）
set -euo pipefail

SKILLS_REPO="${SKILLS_REPO:-$HOME/.cursor/skills-repo}"
SKILLS_REMOTE="${SKILLS_REMOTE:-https://github.com/flll/skills.git}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh not found. Install GitHub CLI and run: gh auth login" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Not logged in. Run: gh auth login" >&2
  exit 1
fi

mkdir -p "$(dirname "$SKILLS_REPO")"

if [[ -d "$SKILLS_REPO/.git" ]]; then
  git -C "$SKILLS_REPO" pull --ff-only
else
  git clone "$SKILLS_REMOTE" "$SKILLS_REPO"
fi

exec "$SKILLS_REPO/scripts/link-skills.sh"
