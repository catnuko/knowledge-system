#!/usr/bin/env bash
# 打包 web 端：把静态面板组装到 web/dist/，可部署到任意静态服务器 / 对象存储。
# 注意：面板 API 使用相对路径 /api/*，静态部署时需把 /api 反向代理到后端（见 deploy.example.conf）。
#
# 用法（仓库根目录执行）：bash web/build.sh
# 产物：web/dist/（index.html + lib/）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/knowledge_engine/web/static"
DIST="$ROOT/web/dist"

if [ ! -f "$SRC/index.html" ]; then
  echo "未找到静态面板：$SRC" >&2
  exit 1
fi

rm -rf "$DIST"
mkdir -p "$DIST/lib"
cp "$SRC/index.html" "$DIST/"
cp "$SRC/lib/echarts.min.js" "$DIST/lib/"
echo "web 端已打包：$DIST"
echo "零配置 web 模式（无需此产物）：ke serve --port 8000"
