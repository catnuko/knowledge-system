#!/usr/bin/env bash
# knowledge-engine 一键启动：后端服务 + 网页前端（浏览器交互）
# 用法：./start.sh [--port 8000]
set -euo pipefail

PORT="${1:-8000}"
if [[ "$1" == "--port" ]]; then PORT="${2:-8000}"; fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# 首次运行：自动安装依赖
if ! python3 -c "import sqlite_vec, fsrs, fastapi, uvicorn" 2>/dev/null; then
  echo "[ke] 首次运行，安装依赖…"
  pip3 install -q -e .
fi

# 环境变量（可用 .env 覆盖）
export KE_EMBEDDING="${KE_EMBEDDING:-light}"
export KE_LLM="${KE_LLM:-rule}"

echo "[ke] 启动知识系统服务 → http://127.0.0.1:${PORT}"
echo "[ke] 浏览器打开上面地址即可使用；Ctrl+C 停止服务"
echo

exec python3 -m uvicorn knowledge_engine.web.app:create_app --factory \
  --host 127.0.0.1 --port "$PORT" --log-level warning
