#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PATTERN='AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|ghp_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z\-_]{35}|-----BEGIN (RSA|OPENSSH|EC|DSA|PRIVATE KEY)-----|api[_-]?key[[:space:]]*[:=][[:space:]]*["'\'' ]?[A-Za-z0-9_\-]{16,}|secret[[:space:]]*[:=][[:space:]]*["'\'' ]?[A-Za-z0-9_\-]{16,}|token[[:space:]]*[:=][[:space:]]*["'\'' ]?[A-Za-z0-9_\-]{16,}'

printf '== Working tree scan ==\n'
rg -n --hidden -S -g '!.git' -g '!.venv/**' -g '!outputs/**' -e "$PATTERN" . || true

printf '\n== Git history scan (sample up to 200 hits) ==\n'
count=0
while IFS= read -r commit; do
  while IFS= read -r line; do
    printf '%s\n' "$line"
    count=$((count + 1))
    if [[ "$count" -ge 200 ]]; then
      printf '\n[Truncated after 200 hits]\n'
      exit 0
    fi
  done < <(git grep -nI -E "$PATTERN" "$commit" -- . ':(exclude).venv' ':(exclude)outputs' ':(exclude)docs/images' || true)
done < <(git rev-list --all)
