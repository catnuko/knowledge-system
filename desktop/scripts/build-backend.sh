#!/usr/bin/env bash
# 把 Python 后端打成单文件二进制（PyInstaller），供 Tauri 桌面端随包分发。
# 仅发布时需要；开发/调试直接 `npm run tauri:dev`（壳内自动调用 ke serve）。
#
# 用法（在仓库根目录执行）：
#   bash desktop/scripts/build-backend.sh
#
# 产物：desktop/backend-dist/knowledge-engine-backend
# 之后打包桌面端时，需把该文件作为资源打进 Tauri 包：
#   tauri.conf.json 的 bundle.resources 增加 "../backend-dist/knowledge-engine-backend"
#   （rust 侧会自动在 resource_dir 下查找该文件）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Windows Git Bash 下 pwd 是 MSYS 风格（/d/...），原生 Python 不识别，转成 Windows 路径
command -v cygpath >/dev/null 2>&1 && ROOT="$(cygpath -m "$ROOT")"
cd "$ROOT"

command -v python3 >/dev/null || { echo "缺少 python3"; exit 1; }
python3 -c "import PyInstaller" 2>/dev/null || { echo "缺少 PyInstaller：pip install pyinstaller"; exit 1; }

rm -rf desktop/backend-dist
# Windows（Git Bash/MSYS）下 --add-data 的分隔符是 ';' 而非 ':'；--noconsole 避免打包出的
# 后端在 Windows 上运行时弹出控制台黑窗（macOS 不能加，否则会产出 .app 而非单文件）
SEP="$(python3 -c "import os; print(';' if os.name=='nt' else ':')")"
EXTRA_ARGS=()
case "$(python3 -c "import os; print(os.name)")" in
  nt) EXTRA_ARGS+=(--noconsole) ;;
esac
WORKDIR="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && WORKDIR="$(cygpath -m "$WORKDIR")"
python3 -m PyInstaller --noconfirm --clean --onefile \
  --name knowledge-engine-backend \
  --add-data "${ROOT}/knowledge_engine/web/static${SEP}knowledge_engine/web/static" \
  --collect-all knowledge_engine \
  --collect-all jieba \
  ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  --distpath desktop/backend-dist \
  --workpath "$WORKDIR" \
  --specpath "$WORKDIR" \
  desktop/scripts/backend_main.py

echo "后端二进制已生成：desktop/backend-dist/knowledge-engine-backend"
echo "提示：若运行时报缺少模块，按错误补充 --hidden-import / --collect-all 后重试。"
