# knowledge-engine 桌面端（Tauri v2）

Tauri v2 壳工程：启动时自动拉起本地 Python 后端（`python -m knowledge_engine.web`），主窗口加载
`http://127.0.0.1:8000` 的 Web 面板。面板代码零改动，桌面端与 Web 端共用同一份前端。

## 目录结构

```
desktop/
├── package.json                     # npm 脚本（dev / 各平台 build / icon）
├── dist-web/                        # 兜底起始页（窗口打开瞬间的占位页）
├── scripts/
│   ├── build-platform.mjs           # 按当前系统自动选平台配置并 build
│   ├── gen-icons.py                 # 生成全部图标（PNG/ICO/ICNS）
│   ├── backend_main.py              # PyInstaller 后端打包入口（发布用）
│   └── build-backend.sh             # 打后端单文件二进制（发布用）
└── src-tauri/
    ├── Cargo.toml / build.rs / src/ # Rust 壳（main.rs / lib.rs）
    ├── tauri.conf.json              # 基础配置（跨平台共享）
    ├── configs/                     # ★ 平台差异配置，按平台分文件夹
    │   ├── windows/tauri.windows.conf.json
    │   ├── linux/tauri.linux.conf.json
    │   └── macos/tauri.macos.conf.json
    ├── capabilities/default.json    # 主窗口能力声明
    └── icons/                       # 生成的图标
```

平台配置文件通过 `tauri build --config <路径>` 与 `tauri.conf.json` **深合并**
（CLI 的 `--config` 行为），因此各平台文件只放本平台差异项（打包目标、图标、安装参数）。

## 环境要求

| 组件 | 版本 | 用途 |
|---|---|---|
| Python + [uv](https://docs.astral.sh/uv/) | ≥ 3.11，`uv sync` | 后端（`uv run python -m knowledge_engine.web`） |
| Node.js | ≥ 18 | Tauri CLI（`@tauri-apps/cli`） |
| Rust | stable（rustup 安装） | Tauri 壳编译 |

Linux 额外系统依赖（构建 webkit2gtk 所需）：
```bash
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

## 开发调试

```bash
cd desktop
npm install
npm run tauri:dev        # 启动壳 + 自动拉起本地后端，窗口打开面板
```

## 打包（按平台）

```bash
npm run tauri:build            # 自动检测当前系统并套用对应平台配置
npm run tauri:build:windows    # 指定 Windows（NSIS + MSI）
npm run tauri:build:linux      # 指定 Linux（deb + AppImage）
npm run tauri:build:macos      # 指定 macOS（app + dmg，需在 macOS 上执行）
```

产物在 `desktop/src-tauri/target/release/bundle/` 下。

## 运行时行为

1. 探测 `127.0.0.1:KE_PORT`（默认 `8000`）是否已有后端监听；
   - 有：直接复用（如你手动跑了 `python -m knowledge_engine.web`）；
   - 没有：按优先级拉起后端
     1. 环境变量 `KE_BACKEND_CMD`（可执行文件路径）
     2. 随包分发的 `resource_dir/knowledge-engine-backend`（PyInstaller 单文件）
     3. 开发模式 `python -m knowledge_engine.web --port <KE_PORT>`（host 固定 127.0.0.1）
2. 轮询等待后端就绪（最长约 60s），随后主窗口跳转到 `http://127.0.0.1:<KE_PORT>`；
3. 退出应用时自动结束由壳拉起的后端进程。

环境变量（透传给后端，均可不设、在面板「设置」里配置）：`KE_DB` / `KE_LLM` / `KE_LLM_KEY` / `KE_LLM_BASE` / `KE_LLM_MODEL` / `KE_EMBEDDING` / `KE_ASR` / `KE_ASR_KEY` / `KE_ASR_BASE` / `KE_ASR_MODEL`。
后端日志：应用日志目录下 `backend.log`。

## 发布桌面安装包（完整分发）

开发模式依赖本机 Python 环境；发布正式安装包时需把后端也打进包：

```bash
# 1. 打后端单文件二进制（PyInstaller）
bash desktop/scripts/build-backend.sh        # → desktop/backend-dist/knowledge-engine-backend

# 2. 在 src-tauri/tauri.conf.json 的 bundle.resources 增加该文件
#    "resources": ["../backend-dist/knowledge-engine-backend"]

# 3. 打包桌面端
npm run tauri:build
```

> 若 PyInstaller 产物运行时报缺模块，按错误信息在 `build-backend.sh` 中补充
> `--hidden-import` / `--collect-all` 后重试（各环境依赖略有差异，尚未在发布环境验证）。
