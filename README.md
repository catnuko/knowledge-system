# Knowledge System · 个人知识系统

多源采集（文本 / 链接 / 音频 / 手写）→ AI 原子化 → 依据知识科学理论构建持续生长的个人知识网络。

## 当前状态：MVP v0.2 — 服务化可用

**日常使用方式 = 启动一个后端服务，用浏览器操作**。CLI 仅为高级调试保留。

四种采集入口（网页界面）：粘贴文本、粘贴链接自动提取、上传音频自动转写、上传手写图片自动识别。
本地优先、单文件 SQLite（含向量检索与全文索引）。**无需任何 API key 即可跑通完整闭环**：采集 → 原子化 → 科学建链 → 间隔重复回取 → 综合 → 冲突检测。

## 快速开始（两步）

```bash
cd knowledge-system
./start.sh                # 第一步：启动服务（首次自动安装依赖）
# 第二步：浏览器打开 http://127.0.0.1:8000
```

Web 面板包含：知识图谱（ECharts 力导向图）、采集（文本/链接/音频/手写）、间隔重复回取评分、建议箱（边确认）、矛盾处理、每周综合、指标条。

> 音频转写（FunASR）与手写识别（PaddleOCR）首次使用时自动下载本地模型（约 1GB / 15MB），之后离线可用。

## 服务架构

```
┌────────────────────────────────────────────┐
│  浏览器（前端：图谱 / 采集 / 回取 / 建议箱）  │
└──────────────▲─────────────────────────────┘
               │ HTTP /api/*
┌──────────────┴─────────────────────────────┐
│  后端服务（FastAPI，./start.sh 启动）        │
│  采集: 文本 / URL提取 / 音频ASR / 手写OCR    │
│  加工: 原子化 → 去重 → 质量门               │
│  建链: 召回 → 命题判定 → 门控 → 前提DAG      │
│  生长: FSRS回取 / 每周综合 / 冲突检测        │
└──────────────┬─────────────────────────────┘
               │ SQLite (vec0 + FTS5 + 递归CTE)
        ~/.knowledge_engine/ke.db
```

## CLI（高级调试，日常不需要）

```bash
pip install -e .
ke ingest-text "文本"        # 采集文本
ke ingest-url <链接>          # 采集链接
ke ingest-file notes.md      # 采集文件
ke ingest-audio a.wav        # 采集音频（需 FunASR）
ke ingest-handwritten a.png  # 采集手写（需 PaddleOCR）
ke link --all                # 建链
ke recall / ke review 1 good # 回取
ke synthesize / ke conflicts / ke stats
```

## 核心思想

- **采集不是壁垒**：6 类源（浏览器、剪贴板、飞书、链接提取、音频转写、手写识别）通过适配器模式增量扩展，多模态输入统一为"文本中间态"
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

## 数据模型

- `sources` — 原始材料（kind: url/clipboard/message/file/audio/handwritten/synthesis + 指纹去重）
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
./start.sh
```

> 注意：切换 embedding 后端后向量语义不同，建议清空重建知识库（`rm ~/.knowledge_engine/ke.db*`）。

### 启用 OpenAI 兼容 LLM（提升原子化/建链/综合质量）

```bash
export KE_LLM=openai KE_LLM_KEY=sk-xxx KE_LLM_BASE=https://api.deepseek.com/v1 KE_LLM_MODEL=deepseek-chat
./start.sh
```

## 测试

```bash
python -m pytest tests/ -q        # 存储/流水线/建链/回取
```

## 文档

- `docs/knowledge-system-mvp-plan.html` — MVP 架构与落地方案 v1.1（技术选型、建链引擎、生长机制、10 周路线图、30 天验收指标、风险对策）

## 路线图（10 周）

| 阶段 | 内容 |
|---|---|
| Phase 0（W1） | 数据模型 schema + vec0 + FSRS + 采集队列抽象 |
| Phase 1a（W2-3） | 文本与链接源：浏览器扩展 / 剪贴板 / 飞书 / URL 提取 |
| Phase 1b（W4） | 音频源：FunASR 本地转写 → 总结入图（✅ 已落地） |
| Phase 1c（W5） | 手写源：PaddleOCR 识别 → 校对 → 总结入图（✅ 已落地） |
| Phase 2（W6-7） | 建链引擎 + 建议箱 + 图谱视图 |
| Phase 3（W8-9） | 回取队列 + 每周综合 + 冲突检测 + 指标面板 |
| Phase 4（W10） | 30 天复盘 + 扩展源 #7+ |

## License

Private / 内部使用
