#!/usr/bin/env bash
# 丝路智审 · 自扫描流水线（对标官方代码安全检查工具）
# 用法: scripts/security-scan.sh [目标目录，默认仓库根]
# 产出: reports/security/<YYYY-MM-DD>.md；存在 HIGH/CRITICAL 时退出码 1
# 工具: semgrep, bandit, gitleaks, trivy, pip-audit, npm audit（缺失则在报告中标为 SKIPPED）
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
ROOT="$(cd "${1:-$(dirname "$0")/..}" && pwd)"
DATE="$(TZ=America/Tijuana date +%F)"
OUT_DIR="$ROOT/reports/security"; mkdir -p "$OUT_DIR"
REPORT="$OUT_DIR/$DATE.md"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
declare -A C=([CRITICAL]=0 [HIGH]=0 [MEDIUM]=0 [LOW]=0 [INFO]=0)
STATUS=""
ERRORS=0
add(){ C[$1]=$(( ${C[$1]} + ${2:-0} )); }
have(){ command -v "$1" >/dev/null 2>&1; }
cnt(){ python3 - "$@"; }
# Scanner/runtime failures must never be reported as a clean scan.
check_report(){
  local tool="$1" rc="$2" file="$3"
  if [ "$rc" -gt 1 ] || ! python3 - "$file" <<'PYJSON'
import json,sys
try:
    data=json.load(open(sys.argv[1]))
    if isinstance(data,dict) and data.get("errors"):
        sys.exit(1)
except (OSError,ValueError):
    sys.exit(1)
PYJSON
  then
    ERRORS=$((ERRORS+1))
    STATUS+="| $tool | ERROR（执行失败或结果不完整） | rc:$rc |"$'\n'
  fi
}

# ---- semgrep ----
if have semgrep; then
  semgrep scan --quiet --metrics=off --config p/owasp-top-ten --config p/python \
    --config p/typescript --config p/secrets --json --exclude reports "$ROOT" >"$TMP/semgrep.json" 2>/dev/null
  check_report semgrep "$?" "$TMP/semgrep.json"
  read -r h m l <<<"$(cnt "$TMP/semgrep.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); r=d.get("results",[])
s=lambda k:sum(1 for x in r if x["extra"].get("severity")==k)
print(s("ERROR"),s("WARNING"),s("INFO"))
PY
)"; add HIGH "$h"; add MEDIUM "$m"; add LOW "$l"
  STATUS+="| semgrep (owasp-top-ten, python, typescript, secrets) | OK | H:$h M:$m L:$l |"$'\n'
else STATUS+="| semgrep | SKIPPED（未安装） | - |"$'\n'; fi

# ---- bandit ----
if have bandit; then
  bandit -r "$ROOT" -x "$ROOT/node_modules,$ROOT/.venv,$ROOT/backend/.venv,$ROOT/tests,$ROOT/backend/tests" -f json -q -o "$TMP/bandit.json" 2>/dev/null
  check_report bandit "$?" "$TMP/bandit.json"
  read -r h m l <<<"$(cnt "$TMP/bandit.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])).get("results",[])
s=lambda k:sum(1 for x in r if x["issue_severity"]==k)
print(s("HIGH"),s("MEDIUM"),s("LOW"))
PY
)"; add HIGH "$h"; add MEDIUM "$m"; add LOW "$l"
  STATUS+="| bandit | OK | H:$h M:$m L:$l |"$'\n'
else STATUS+="| bandit | SKIPPED（未安装或无 Python 源码） | - |"$'\n'; fi

# ---- gitleaks (含 git 历史) ----
if have gitleaks; then
  if git -C "$ROOT" rev-parse >/dev/null 2>&1; then
    gitleaks git "$ROOT" --redact --no-banner -r "$TMP/gl-history.json" -f json >/dev/null 2>&1
    check_report gitleaks-history "$?" "$TMP/gl-history.json"
  else echo '[]' >"$TMP/gl-history.json"; fi
  gitleaks dir "$ROOT" --redact --no-banner -r "$TMP/gl-tree.json" -f json >/dev/null 2>&1
  check_report gitleaks-worktree "$?" "$TMP/gl-tree.json"
  python3 - "$TMP" <<'PYGL'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); rows=[]
for name in ("gl-history.json","gl-tree.json"):
    try: rows.extend(json.loads((p/name).read_text()) or [])
    except (OSError,ValueError): pass
(p/"gl.json").write_text(json.dumps(rows))
PYGL
  n=$(python3 -c "import json,sys;print(len(json.load(open(sys.argv[1])) or []))" "$TMP/gl.json" 2>/dev/null || echo 0)
  add CRITICAL "$n"; STATUS+="| gitleaks（工作区 + 全部 git 历史，已脱敏） | OK | C:$n |"$'\n'
else STATUS+="| gitleaks | SKIPPED | - |"$'\n'; fi

# ---- trivy fs ----
if have trivy; then
  trivy fs --quiet --scanners vuln,misconfig,secret --format json -o "$TMP/trivy.json" --skip-dirs reports "$ROOT" >/dev/null 2>&1
  check_report trivy "$?" "$TMP/trivy.json"
  read -r c h m l <<<"$(cnt "$TMP/trivy.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); n={"CRITICAL":0,"HIGH":0,"MEDIUM":0,"LOW":0}
for r in d.get("Results") or []:
  for k in ("Vulnerabilities","Misconfigurations","Secrets"):
    for x in r.get(k) or []:
      s=x.get("Severity","LOW"); n[s]=n.get(s,0)+1
print(n["CRITICAL"],n["HIGH"],n["MEDIUM"],n["LOW"])
PY
)"; add CRITICAL "$c"; add HIGH "$h"; add MEDIUM "$m"; add LOW "$l"
  STATUS+="| trivy fs（依赖漏洞 + IaC/Dockerfile + 密钥） | OK | C:$c H:$h M:$m L:$l |"$'\n'
else STATUS+="| trivy | SKIPPED | - |"$'\n'; fi

# ---- pip-audit ----
mapfile -t REQS < <(find "$ROOT" \( -name 'requirements*.txt' -o -name 'pylock*.toml' \) -not -path '*/node_modules/*' 2>/dev/null)
if have pip-audit && [ ${#REQS[@]} -gt 0 ]; then
  t=0; for f in "${REQS[@]}"; do
    # uv 导出的完整精确版本集合无需再次解析/安装（扫描器 Python 可能为 3.13）。
    pip-audit --no-deps --disable-pip -r "$f" -f json -o "$TMP/pa.json" >/dev/null 2>&1
    check_report pip-audit "$?" "$TMP/pa.json"
    k=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(sum(len(x.get('vulns',[])) for x in d.get('dependencies',[])))" "$TMP/pa.json" 2>/dev/null || echo 0); t=$((t+k)); done
  add HIGH "$t"; STATUS+="| pip-audit（${#REQS[@]} 个依赖文件，漏洞按 HIGH 计） | OK | H:$t |"$'\n'
else STATUS+="| pip-audit | SKIPPED（无 requirements 锁文件） | - |"$'\n'; fi

# ---- npm audit ----
mapfile -t LOCKS < <(find "$ROOT" -name package-lock.json -not -path '*/node_modules/*' 2>/dev/null)
if have npm && [ ${#LOCKS[@]} -gt 0 ]; then
  for f in "${LOCKS[@]}"; do
    (cd "$(dirname "$f")" && npm audit --json >"$TMP/npm.json" 2>/dev/null)
    check_report npm-audit "$?" "$TMP/npm.json"
    read -r c h m l <<<"$(python3 -c "import json,sys;v=json.load(open(sys.argv[1])).get('metadata',{}).get('vulnerabilities',{});print(v.get('critical',0),v.get('high',0),v.get('moderate',0),v.get('low',0))" "$TMP/npm.json" 2>/dev/null || echo 0 0 0 0)"
    add CRITICAL "$c"; add HIGH "$h"; add MEDIUM "$m"; add LOW "$l"
    STATUS+="| npm audit ($(realpath --relative-to="$ROOT" "$f")) | OK | C:$c H:$h M:$m L:$l |"$'\n'; done
else STATUS+="| npm audit | SKIPPED（无 package-lock.json） | - |"$'\n'; fi

COMMIT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo n/a)"
FAIL=$(( ${C[CRITICAL]} + ${C[HIGH]} ))
{
echo "# 安全自扫描报告 $DATE"; echo
echo "- 扫描对象：仓库提交 \`$COMMIT\`（HEAD + 当前工作区，含 git 历史密钥扫描）"
echo "- 结论：$([ $FAIL -eq 0 ] && [ $ERRORS -eq 0 ] && echo '**通过**（无 HIGH/CRITICAL）' || echo "**未通过**（HIGH+CRITICAL = $FAIL，扫描器错误 = $ERRORS）")"; echo
echo "## 按严重级别汇总"; echo; echo "| CRITICAL | HIGH | MEDIUM | LOW |"; echo "|---|---|---|---|"
echo "| ${C[CRITICAL]} | ${C[HIGH]} | ${C[MEDIUM]} | ${C[LOW]} |"; echo
echo "## 各工具结果"; echo; echo "| 工具 | 状态 | 计数 |"; echo "|---|---|---|"; printf '%s' "$STATUS"; echo
echo "## 明细（前 50 条）"; echo
python3 - "$TMP" "$ROOT" <<'PY'
import json,sys,os
t,root=sys.argv[1],sys.argv[2]; rows=[]
def L(p):
  try: return json.load(open(os.path.join(t,p)))
  except Exception: return None
d=L("semgrep.json")
for error in (d or {}).get("errors",[]): rows.append(("semgrep", "ERROR", error.get("path", ""), error.get("type", "scanner_error")))
for x in (d or {}).get("results",[]): rows.append(("semgrep",x["extra"].get("severity"),os.path.relpath(x["path"],root)+":"+str(x["start"]["line"]),x["check_id"].split(".")[-1]))
d=L("bandit.json")
for error in (d or {}).get("errors",[]): rows.append(("semgrep", "ERROR", error.get("path", ""), error.get("type", "scanner_error")))
for x in (d or {}).get("results",[]): rows.append(("bandit",x["issue_severity"],os.path.relpath(x["filename"],root)+":"+str(x["line_number"]),x["test_id"]+" "+x["test_name"]))
for x in L("gl.json") or []: rows.append(("gitleaks","CRITICAL",x.get("File","")+":"+str(x.get("StartLine","")),x.get("RuleID","")+" @"+x.get("Commit","")[:7]))
d=L("trivy.json")
for r in (d or {}).get("Results") or []:
  for k in ("Vulnerabilities","Misconfigurations","Secrets"):
    for x in r.get(k) or []: rows.append(("trivy",x.get("Severity"),r.get("Target",""),x.get("VulnerabilityID") or x.get("ID") or x.get("RuleID","")))
if not rows: print("无发现。")
else:
  print("| 工具 | 级别 | 位置 | 规则 |\n|---|---|---|---|")
  for r in rows[:50]: print("| "+" | ".join(str(c).replace("|","/") for c in r)+" |")
PY
echo; echo "> 说明：官方工具未公开，本流水线用多款开源扫描器做并集覆盖；密钥类发现一律按 CRITICAL 计，报告只输出脱敏位置，不含密钥值。"
} >"$REPORT"
echo "report: $REPORT  CRITICAL=${C[CRITICAL]} HIGH=${C[HIGH]} MEDIUM=${C[MEDIUM]} LOW=${C[LOW]} ERRORS=$ERRORS"
[ $FAIL -eq 0 ] && [ $ERRORS -eq 0 ]
