#!/usr/bin/env bash
# 端到端冒烟：覆盖 CLI 全闭环（采集→建链→回取→评分→综合→冲突→指标）
# 在 GitHub Actions 与本地均可运行。失败即非零退出。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 强制使用临时库，避免本地 ~/.knowledge_engine/ke.db 残留数据干扰
export KE_DB="${KE_DB:-/tmp/ke_smoke.db}"
export KE_LLM="${KE_LLM:-rule}"
export KE_EMBEDDING="${KE_EMBEDDING:-light}"
rm -f "$KE_DB" "$KE_DB-shm" "$KE_DB-wal" 2>/dev/null || true

echo "[smoke] 1/7 ingest-text"
ke ingest-text "间隔重复算法通过遗忘曲线安排复习，能提升长期记忆保持率。检索练习通过主动提取巩固记忆。" --title "记忆理论"
ke ingest-text "主动回忆比重读更有效，是检索练习的核心机制。" --title "回忆"

echo "[smoke] 2/7 link"
OUT=$(ke link --all)
echo "$OUT"
# 必须产出至少一条候选边（auto 或 pending），否则建链闭环有问题
echo "$OUT" | grep -qE "自动建链 [1-9]|待确认 [1-9]" \
  || { echo "[smoke] FAIL: 建链未产出任何候选边"; exit 1; }

echo "[smoke] 3/7 recall"
RECALL=$(ke recall)
echo "$RECALL"
echo "$RECALL" | grep -qE "今日到期 [1-9]" \
  || { echo "[smoke] FAIL: 到期队列为空"; exit 1; }

echo "[smoke] 4/7 review"
# 取第一条到期卡片 id 评分（节点 id 从 recall 输出里抓 [N]）
NID=$(echo "$RECALL" | grep -oE '\[[0-9]+\]' | head -1 | tr -d '[]')
[ -n "$NID" ] || { echo "[smoke] FAIL: 未抓到节点 id"; exit 1; }
ke review "$NID" good | grep -q '"reps": 1' \
  || { echo "[smoke] FAIL: review 未更新 reps"; exit 1; }

echo "[smoke] 5/7 synthesize"
ke synthesize  # 不强校验产出（连通分量 <2 时会提示无足够节点）

echo "[smoke] 6/7 conflicts"
ke conflicts  # 无矛盾时打印"当前无未解决的矛盾"也通过

echo "[smoke] 7/7 stats"
STATS=$(ke stats)
echo "$STATS"
# ingest 2 个 + synthesize 1 个综合节点 = 3
echo "$STATS" | grep -q '"nodes": 3' \
  || { echo "[smoke] FAIL: stats 节点数不符（应为 3 = 2 ingest + 1 综合）"; exit 1; }
echo "$STATS" | grep -q '"reviewed": 1' \
  || { echo "[smoke] FAIL: stats 已复习数不符"; exit 1; }
echo "$STATS" | grep -q '"synthesis_count": 1' \
  || { echo "[smoke] FAIL: stats 综合产出数不符"; exit 1; }

echo "[smoke] ALL OK"
