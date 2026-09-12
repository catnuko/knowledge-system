# Changelog

## [1.0.0](https://github.com/catnuko/knowledge-system/compare/v0.3.0...v1.0.0) (2026-09-12)


### ⚠ BREAKING CHANGES

* ke 命令不再存在。服务启动改为 uv run python -m knowledge_engine.web --port 8000； 自动化/集成请直接调用 /api/* 接口。

### Features

* **desktop:** 支持 Windows 打包 ([d077dde](https://github.com/catnuko/knowledge-system/commit/d077ddec1b4d48ea2b9d8a9699fbfe93a49a9014))
* **settings:** 设置面板 + 在线 ASR/LLM provider 配置 ([23c90c9](https://github.com/catnuko/knowledge-system/commit/23c90c932f68328b5788176107c09eab0ffabd4d))


### Bug Fixes

* **ci:** tauri resources 用通配符兼容 Windows .exe 后端 ([d3bb241](https://github.com/catnuko/knowledge-system/commit/d3bb2410fd9cde9d315496ee9880194f27a4e16a))
* **ci:** Windows runner 下 PyInstaller 路径用 cygpath 转 MSYS 路径 ([369d151](https://github.com/catnuko/knowledge-system/commit/369d15198dce5994016cfe894bc85eabfd177fa9))
* **ci:** Windows venv 无 python3，build-backend.sh 改为解析 venv 解释器 ([7f590aa](https://github.com/catnuko/knowledge-system/commit/7f590aa10e04033991b97b567603ce5b47942183))


### Documentation

* 记录 Rust 重写决策（推迟至 1.0 后） ([94c5fe7](https://github.com/catnuko/knowledge-system/commit/94c5fe7c6cb3f5c024c6a657d3a17cbf82886628))
* 重写 README（中英），标注项目处于开发中、不保证可用 ([b7153ad](https://github.com/catnuko/knowledge-system/commit/b7153ad652157285973b506380b02d1aeb0d0152))


### Code Refactoring

* 移除 CLI，统一为 Web/桌面端两条入口 ([712303b](https://github.com/catnuko/knowledge-system/commit/712303b99415459eec763da4ff8bcf5266523115))

## [0.3.0](https://github.com/catnuko/knowledge-system/compare/v0.2.0...v0.3.0) (2026-09-12)


### Features

* **web:** 桌面端优先的现代化面板重构 ([75e25f1](https://github.com/catnuko/knowledge-system/commit/75e25f1548ec0083479ce2b41125455d2be8e146))
