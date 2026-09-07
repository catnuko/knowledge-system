#!/usr/bin/env bash
# knowledge-engine 一键启动：后端服务 + 网页前端（浏览器交互）
set -euo pipefail
PORT="${1:-8000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
exec python3 -m uvicorn knowledge_engine.web.app:create_app --factory --host 127.0.0.1 --port "$PORT" --log-level warning
