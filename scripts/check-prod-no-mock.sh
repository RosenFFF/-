#!/usr/bin/env bash
# Fail if a production Vite build still contains triggerable mock fixtures or the mock banner.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$ROOT/web"
DIST="${1:-$WEB/dist}"

if [[ ! -d "$DIST" ]]; then
  echo "check-prod-no-mock: missing dist at $DIST" >&2
  exit 2
fi

# Strings that must never ship in a production bundle (fixtures / banner / mock module).
PATTERNS=(
  'MOCK 数据 · 仅开发'
  'DEVELOPMENT ONLY'
  'MOCK · 开发用合规报告'
  'MOCK 开发规则'
  'mockApi'
  'VITE_USE_MOCK'
  'sr_mock_user'
  'from "../mock/api"'
  'from "../mock/data"'
)

hits=0
while IFS= read -r -d '' file; do
  for pat in "${PATTERNS[@]}"; do
    if grep -F -q -- "$pat" "$file"; then
      echo "LEAK in $file: $pat" >&2
      hits=$((hits + 1))
    fi
  done
done < <(find "$DIST" -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.svg' \) -print0)

if [[ "$hits" -gt 0 ]]; then
  echo "check-prod-no-mock: FAIL ($hits leak(s))" >&2
  exit 1
fi
echo "check-prod-no-mock: OK ($DIST)"
