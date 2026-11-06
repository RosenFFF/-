#!/usr/bin/env bash
# Fail if a production Vite build still contains DEMO audit tamper/restore entry points.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$ROOT/web"
DIST="${1:-$WEB/dist}"

if [[ ! -d "$DIST" ]]; then
  echo "check-prod-no-demo: missing dist at $DIST" >&2
  exit 2
fi

PATTERNS=(
  '/demo/audit/tamper'
  '/demo/audit/restore'
  'demoAuditApi'
  'DemoAuditPanel'
  'audit-demo-h'
  'demo.audit_tamper'
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
  echo "check-prod-no-demo: FAIL ($hits leak(s))" >&2
  exit 1
fi
echo "check-prod-no-demo: OK ($DIST)"
