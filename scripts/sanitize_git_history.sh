#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo is required. Install with: brew install git-filter-repo"
  exit 1
fi

LEAKED_KEY="${1:-}"
if [[ -z "$LEAKED_KEY" ]]; then
  echo "Usage: $0 <leaked_key_literal>"
  echo "Example: pass the leaked token value as argument 1"
  exit 1
fi

REPLACE_FILE="/tmp/ffmas-replacements.txt"
printf '%s==>REDACTED_DEEPSEEK_KEY\n' "$LEAKED_KEY" > "$REPLACE_FILE"

echo "Creating backup refs before rewrite..."
git branch backup/pre-sanitize-$(date +%Y%m%d%H%M%S)

echo "Rewriting history: dropping .env and .venv from all commits..."
git filter-repo --force \
  --path .env \
  --path .venv \
  --invert-paths

echo "Rewriting known leaked literals..."
git filter-repo --force --replace-text "$REPLACE_FILE"

echo
echo "History rewrite complete. Next steps:"
echo "1) Rotate any leaked keys at provider side immediately."
echo "2) Re-run: ./scripts/scan_secrets.sh"
echo "3) Force-push rewritten history:"
echo "   git push --force --all origin"
echo "   git push --force --tags origin"
echo "4) Ask collaborators to re-clone (old clones keep old history)."
