# Knowledge System · 个人知识系统

多源采集（文本 / 链接 / 音频）→ AI 原子化 → 依据知识科学理论构建持续生长的个人知识网络。

## 当前状态：MVP v0.1 已可运行

本地优先、单文件 SQLite（含向量检索与全文索引）的知识网络引擎。**无需任何 API key 即可跑通完整闭环**：采集 → 原子化 → 科学建链 → 间隔重复回取 → 综合 → 冲突检测。

## 快速开始

```bash
pip install -e .            # 安装依赖（sqlite-vec / fsrs / trafilatura / jieba / fastapi）

ke ingest-text "间隔重复算法通过遗忘曲线安排复习，能提升长期记忆保持率" --title "间隔重复"
ke ingest-file notes.md     # 本地文件
ke ingest-url https://www.ruanyifeng.com/blog/...   # 网页提取（trafilatura）
ke link --all               # 建链：自动边 + 建议箱 + 孤儿标记
ke recall                   # 今日到期回取卡片
ke review 1 good            # 评分：again / hard / good / easy
ke synthesize               # 每周综合（连通分量 → 综述 → 新节点挂回图）
ke conflicts                # 矛盾检测报告
ke stats                    # 指标面板
ke serve --port 8000        # Web 面板（图谱 / 采集 / 回取 / 建议箱 / 矛盾）
```

## 核心思想

- **采集不是壁垒**：5 类源（浏览器、剪贴板、飞书、链接提取、音频转写）通过适配器模式增量扩展，多模态输入统一为"文本中间态"
- **科学建链**：网络 = 原子节点 + 9 类命题化有向边 + 前提 DAG，每条边可解释、可审计，拒绝"相似就拉线"
- **生长是主引擎**：FSRS 每日回取 + 每周社区综合 + 冲突检测，北极星指标是回取率而非存储量

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
- `edges` — 9 类命题边（implies/supports/contradicts/exemplifies/refines/prerequisite_of/contrasts/merges/relates）
- `node_vec`（vec0 向量 KNN）+ `node_fts`（trigram 全文）— 双路召回
- 图查询：递归 CTE，不引入图数据库（迁移触发器：节点 >10⁵ 或需实时图算法）

## 建链门控（可审计）

| 置信度 | 动作 |
|---|---|
| ≥ 0.85 | 自动入图（可撤回） |
| 0.5 – 0.85 | 建议箱，人工确认 |
| < 0.5 | 丢弃 |

## 关键配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `KE_DB` | `~/.knowledge_engine/ke.db` | 数据库路径 |
| `KE_LLM` | `rule` | `rule`=规则模式（零依赖）；`openai`=OpenAI 兼容 API |
| `KE_LLM_KEY` / `KE_LLM_BASE` / `KE_LLM_MODEL` | — / deepseek / deepseek-chat | 例如 DeepSeek 或 Qwen |
| `KE_EMBEDDING` | `light` | `light`=内置轻量向量；`bge`=BGE-small-zh 本地语义模型（推荐） |

### 启用 BGE 语义嵌入（推荐）

```bash
pip install torch transformers          # CPU 版 torch：pip install torch --index-url https://download.pytorch.org/whl/cpu
# 首次调用自动从 HuggingFace 下载 BAAI/bge-small-zh-v1.5（约 100MB），
# 国内网络可设置 HF_ENDPOINT=https://hf-mirror.com
export KE_EMBEDDING=bge
ke ingest-text "..."
ke link --all
```

> 注意：切换 embedding 后端后向量语义不同，建议清空重建知识库（`rm ~/.knowledge_engine/ke.db*`）。

### 启用 OpenAI 兼容 LLM（提升原子化/建链/综合质量）

```bash
export KE_LLM=openai KE_LLM_KEY=sk-xxx KE_LLM_BASE=https://api.deepseek.com/v1 KE_LLM_MODEL=deepseek-chat
```

### 音频源（接口已预留）

```bash
pip install funasr modelscope    # 音频转写（中文优化，本地推理）
```

## 测试

```bash
python -m pytest tests/ -q        # 11 个用例：存储/流水线/建链/回取
```

## 文档

- `docs/knowledge-system-mvp-plan.html` — MVP 架构与落地方案 v1.1（技术选型、建链引擎、生长机制、10 周路线图、30 天验收指标、风险对策）

## 打包：桌面端 / Web 端

同一份前端（`knowledge_engine/web/static/`），三种形态：

| 形态 | 方式 | 说明 |
|---|---|---|
| Web（零配置） | `ke serve --port 8000` | 后端直接托管面板 |
| Web（静态部署） | `bash web/build.sh` | 产出 `web/dist/`，Nginx/CDN 托管，`/api` 反代后端（见 `web/deploy.example.conf`） |
| 桌面端（Tauri v2） | `cd desktop && npm install && npm run tauri:dev` | 壳自动拉起本地后端并加载面板；平台差异配置按文件夹拆分于 `desktop/src-tauri/configs/{windows,linux,macos}/` |

桌面端与 Web 端共用同一份面板代码，桌面端详情见 `desktop/README.md`。

## 路线图（10 周）

| 阶段 | 内容 |
|---|---|
| Phase 0（W1） | 数据模型 schema + vec0 + FSRS + 采集队列抽象 |
| Phase 1a（W2-3） | 文本与链接源：浏览器扩展 / 剪贴板 / 飞书 / URL 提取 |
| Phase 1b（W4） | 音频源：FunASR 本地转写 → 总结入图 |
| Phase 2（W6-7） | 建链引擎 + 建议箱 + 图谱视图 |
| Phase 3（W8-9） | 回取队列 + 每周综合 + 冲突检测 + 指标面板 |
| Phase 4（W10） | 30 天复盘 + 扩展源 #7+ |

## License

Private / 内部使用
