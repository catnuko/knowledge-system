#!/usr/bin/env bash
# 端到端冒烟：覆盖 Web API 全闭环（设置→采集→建链→回取→评分→综合→冲突→指标）
# 在 GitHub Actions 与本地均可运行。失败即非零退出。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 强制使用临时库，避免本地 ~/.knowledge_engine/ 数据残留干扰
export KE_DB="${KE_DB:-/tmp/ke_smoke.db}"
export KE_LLM="${KE_LLM:-rule}"
export KE_EMBEDDING="${KE_EMBEDDING:-light}"
PORT="${KE_SMOKE_PORT:-8177}"
BASE="http://127.0.0.1:${PORT}"
rm -f "$KE_DB" "$KE_DB-shm" "$KE_DB-wal" 2>/dev/null || true

# 优先走 uv 管理的虚拟环境（uv run bash 调用时已在 venv 内，裸 python3 可能是系统解释器）
run_py() {
  if command -v uv >/dev/null 2>&1; then uv run python "$@"; else python3 "$@"; fi
}

# 启动后端（后台），退出时清理
run_py -m knowledge_engine.web --port "$PORT" >/tmp/ke_smoke_server.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for i in $(seq 1 30); do
  curl -sf "$BASE/api/stats" >/dev/null 2>&1 && break
  [ "$i" = 30 ] && { echo "[smoke] FAIL: 后端未就绪"; cat /tmp/ke_smoke_server.log; exit 1; }
  sleep 1
done

# JSON 字段读取（无 jq 依赖）
jqget() { run_py -c "import json,sys; d=json.load(sys.stdin); print(eval('d'+sys.argv[1]))" "$1"; }

echo "[smoke] 1/8 settings（读写 config.json）"
curl -sf "$BASE/api/settings" >/dev/null
curl -sf -X PUT "$BASE/api/settings" -H 'Content-Type: application/json' \
  -d '{"settings":{"llm_provider":"rule"}}' | grep -q '"provider"'

echo "[smoke] 2/8 ingest"
curl -sf -X POST "$BASE/api/ingest" -H 'Content-Type: application/json' \
  -d '{"text":"间隔重复算法通过遗忘曲线安排复习，能提升长期记忆保持率。检索练习通过主动提取巩固记忆。","title":"记忆理论"}' >/dev/null
curl -sf -X POST "$BASE/api/ingest" -H 'Content-Type: application/json' \
  -d '{"text":"主动回忆比重读更有效，是检索练习的核心机制。","title":"回忆"}' >/dev/null

echo "[smoke] 3/8 link（必须产出候选边）"
LINK=$(curl -sf -X POST "$BASE/api/link")
echo "$LINK"
echo "$LINK" | run_py -c "
import json,sys
d = json.load(sys.stdin)
assert d.get('linked',0) + d.get('pending',0) > 0, '建链未产出任何候选边'
" || { echo "[smoke] FAIL: 建链未产出候选边"; exit 1; }

echo "[smoke] 4/8 recall"
RECALL=$(curl -sf "$BASE/api/recall")
echo "$RECALL" | head -c 200; echo
NID=$(echo "$RECALL" | jqget "['cards'][0]['id']")
[ -n "$NID" ] || { echo "[smoke] FAIL: 到期队列为空"; exit 1; }

echo "[smoke] 5/8 review"
curl -sf -X POST "$BASE/api/recall/$NID/review" -H 'Content-Type: application/json' \
  -d '{"rating":"good"}' | jqget "['reps']" | grep -qx 1 \
  || { echo "[smoke] FAIL: review 未更新 reps"; exit 1; }

echo "[smoke] 6/8 synthesize"
curl -sf -X POST "$BASE/api/synthesize" >/dev/null

echo "[smoke] 7/8 conflicts"
curl -sf "$BASE/api/conflicts" >/dev/null

echo "[smoke] 8/8 stats"
STATS=$(curl -sf "$BASE/api/stats")
echo "$STATS"
# ingest 2 个 + synthesize 1 个综合节点 = 3
echo "$STATS" | run_py -c "
import json,sys
d = json.load(sys.stdin)
assert d['nodes'] == 3, f'节点数应为 3（2 ingest + 1 综合），实际 {d[\"nodes\"]}'
" || { echo "[smoke] FAIL: stats 校验未通过"; exit 1; }

echo "[smoke] ALL OK"
