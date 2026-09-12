# SecondMe · 第二个我

**中文** | [English](README.md)

> ## ⚠️ 项目正在开发中（Work in Progress）
>
> 本项目处于**活跃开发早期阶段**，接口、数据模型与功能随时可能变更。
> **不保证可用性**：你可能会遇到 bug、功能缺失或文档与实际行为不一致。
> 欢迎试用和反馈，但请勿在生产环境或重要数据上依赖本项目。
> 当前发布版本见 [Releases](https://github.com/catnuko/knowledge-system/releases)。

多源采集（文本 / 链接 / 文件）→ AI 原子化 → 依据知识科学理论构建持续生长的个人知识网络。

## 当前状态：v0.3.0

本地优先、单文件 SQLite（含向量检索与全文索引）的知识网络引擎，无需任何 API key 即可跑通完整闭环：
采集 → 原子化 → 科学建链 → 间隔重复回取 → 综合 → 冲突检测 → 对话问答 → 主动验证（Feynman）。

- **Web 面板**（v0.3 重构）：桌面端优先的现代化界面，侧边栏多视图（总览 / 图谱 / 采集 / 复习 / 验证 / 问答），闪卡式复习支持键盘操作
- **桌面端**：Tauri v2 壳，macOS 与 Windows 安装包由 CI 自动构建发布（Windows 安装包未签名，安装时 SmartScreen 会告警）
- **发版自动化**：Conventional Commits + release-please，合并发版 PR 即自动升版本、生成 CHANGELOG、打包双平台产物

### 已知限制

- 默认 `rule` 模式下问答 / Feynman 评分 / 综合为规则降级实现，效果有限；接入 OpenAI 兼容 API 后才获得完整 LLM 能力
- 打包后的桌面端**不含音频转写**（FunASR + 模型体积原因）；CLI 源码运行可用
- Windows 安装包未做代码签名
- 数据模型与 API 在后续版本可能不兼容（无迁移保证）

## 快速开始（源码运行）

```bash
# 用 uv（推荐）：自动创建虚拟环境 + 锁定依赖
uv sync                    # 安装依赖（sqlite-vec / fsrs / trafilatura / jieba / fastapi）
uv run ke serve --port 8000   # 打开 http://127.0.0.1:8000 即面板
```

CLI 方式：

```bash
uv run ke ingest-text "间隔重复算法通过遗忘曲线安排复习，能提升长期记忆保持率" --title "间隔重复"
uv run ke ingest-file notes.md             # 本地文件
uv run ke ingest-url https://example.com   # 网页提取（trafilatura）
uv run ke link --all                       # 建链：自动边 + 建议箱 + 孤儿标记
uv run ke recall                           # 今日到期卡片
uv run ke review 1 good                    # 评分：again / hard / good / easy
uv run ke synthesize                       # 每周综合（连通分量 → 综述回图）
uv run ke conflicts                        # 矛盾检测报告
uv run ke stats                            # 指标面板（掌握度 / Feynman 次数）
```

## 桌面端安装包

在 [Releases](https://github.com/catnuko/knowledge-system/releases) 下载（由 GitHub Actions 自动构建）：

| 平台 | 产物 |
|---|---|
| macOS (Apple Silicon) | `knowledge-engine_vX.Y.Z_aarch64.dmg` / `_macos_app.zip` |
| Windows x64 | NSIS 安装包 `.exe` / `.msi` |

应用启动时自动拉起内置后端并打开面板，数据存于 `~/.knowledge_engine/`。

## 核心思想

- **采集不是壁垒**：多类源（浏览器扩展、剪贴板、链接提取、文件、音频转写）通过适配器模式增量扩展，统一为"文本中间态"
- **科学建链**：网络 = 原子节点 + 9 类命题化有向边 + 前提 DAG，每条边可解释、可审计，拒绝"相似就拉线"
- **生长是主引擎**：FSRS 每日回取 + 每周社区综合 + 冲突检测 + Feynman 主动验证，北极星指标是掌握度而非存储量

## 科学依据

| 理论 | 对应设计规则 |
|---|---|
| Ausubel 同化理论 | 新节点必须链接到已有结构，否则进待连接池 |
| Novak 概念图 | 边必须是带类型的命题（9 类有向边） |
| 知识空间理论 KST | 前提 DAG 决定学习与回取顺序，环检测拦截 |
| 检索练习 + FSRS | 按遗忘曲线调度回取，提示先行 |
| GraphRAG | 每周基于图社区做综合产出 |

## 架构（五层 + 生长回环）

```
采集层  →  加工层  →  存储层  →  建链层  →  生长层
文本/文件/URL/音频  |  原子化/去重/质量门  |  SQLite+vec0+FTS5  |  召回/判定/门控/DAG  |  FSRS/综合/冲突/指标
```

## 数据模型

- `sources` — 原始材料（kind: url/clipboard/message/file/audio/synthesis + 指纹去重）
- `nodes` — 原子笔记（concept/claim/question + FSRS 记忆状态）
- `edges` — 9 类命题有向边（implies/supports/contradicts/exemplifies/refines/prerequisite_of/contrasts/merges/relates）
- `verifications` — 主动验证记录（mode: feynman/recall/generative + 复述/gap/评分/反馈）
- `node_vec`（vec0 向量 KNN）+ `node_fts`（trigram 全文）— 双通道召回
- 图查询用递归 CTE，不引入图数据库（迁移触发条件：节点 >10⁵ 或需要实时图算法）

## 建链门控（可审计）

| 置信度 | 动作 |
|---|---|
| ≥ 0.85 | 自动合并（可回滚） |
| 0.5 – 0.85 | 建议箱，人工确认 |
| < 0.5 | 丢弃 |

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `KE_DB` | `~/.knowledge_engine/ke.db` | 数据库路径 |
| `KE_LLM` | `rule` | `rule`=规则模式（零依赖）；`openai`=OpenAI 兼容 API |

## 开发

```bash
uv run pytest -q           # 测试套件
bash web/build.sh          # Web 静态打包 → web/dist/
bash desktop/scripts/build-backend.sh   # PyInstaller 后端单文件（发布用）
# 桌面端本地开发：cd desktop && npm install && npm run tauri:dev
```

CI（GitHub Actions）：
- `CI` — push/PR 时跑测试
- `Release Please` — 发版 PR（自动版本号 + CHANGELOG），合并后自动构建 macOS / Windows 产物并发布 Release
- `Build & Release` — 手动打包（可指定 tag）

## 文档

- `docs/architecture.md` — 架构与数据模型、9 类边定义、建链门控、FSRS/GraphRAG/Feynman 机制、API 速查
- `docs/knowledge-system-mvp-plan.html` — MVP 架构与落地方案 v1.1

## License

MIT — 见 [LICENSE](LICENSE)。
