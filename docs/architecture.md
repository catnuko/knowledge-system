# SecondMe · 架构与机制文档

本文档记录 SecondMe（第二个我）的数据模型、9 类命题边、建链门控、FSRS 间隔重复、GraphRAG 问答、Feynman 主动验证与 API 速查。供二次开发与审计使用。

## 目录

- [五层架构](#五层架构)
- [数据模型](#数据模型)
- [9 类命题边定义](#9-类命题边定义)
- [建链引擎与门控](#建链引擎与门控)
- [FSRS 间隔重复](#fsrs-间隔重复)
- [GraphRAG 对话问答](#graphrag-对话问答)
- [主动验证：Feynman / 生成提问 / 盲测](#主动验证feynman--生成提问--盲测)
- [掌握度指标](#掌握度指标)
- [部署与降级](#部署与降级)
- [API 速查](#api-速查)

---

## 五层架构

```
采集层  →  加工层  →  存储层  →  建链层  →  生长层
文本/文件/URL/音频/图片  |  原子化/去重/质量门  |  SQLite+vec0+FTS5  |  召回/判定/门控/DAG  |  FSRS/综合/冲突/问答/验证
```

- **采集层**：浏览器扩展（右键选中文本）、Tauri 全局快捷键（剪贴板）、URL 提取（trafilatura）、音频转写（FunASR）、图片 OCR（rapidocr）。统一为"文本中间态"。
- **加工层**：原子化（rule 段落切分 / LLM 主张拆解）→ SHA256 指纹去重 → 质量门（MIN_BODY=20 字）。
- **存储层**：单文件 SQLite + vec0 向量 KNN + FTS5 trigram 全文。递归 CTE 做图查询，不引入图数据库。
- **建链层**：向量 Top-K ∪ FTS Top-K 召回 → 命题判定（9 类）→ 置信度门控 → 前提 DAG 环检测 → 双向去重。
- **生长层**：FSRS 每日回取 + 每周社区综合 + 冲突检测 + Feynman 主动验证 + 掌握度指标。

---

## 数据模型

### `sources` — 原始材料

| 字段 | 说明 |
|---|---|
| `id` | PK |
| `kind` | url/clipboard/message/file/audio/synthesis |
| `raw_path` | 原始文件路径 |
| `text_extracted` | 提取后的纯文本 |
| `fingerprint` | SHA256 指纹（去重） |
| `captured_at` | 采集时间 |

### `nodes` — 原子笔记

| 字段 | 说明 |
|---|---|
| `id` | PK |
| `type` | concept / claim / question |
| `title` | 简短标题 |
| `body` | 主张内容（≤600 字） |
| `source_ref` | FK → sources |
| `status` | draft / active / pending_link / archived |
| `recall_state` | JSON：FSRS 卡片状态（stability/difficulty/due/reps/lapses） |

### `edges` — 9 类命题边

| 字段 | 说明 |
|---|---|
| `id` | PK |
| `src_id`, `dst_id` | FK → nodes |
| `rel_type` | 9 类之一（见下表） |
| `rationale` | 一句话理由（可审计） |
| `confidence` | 0.0–1.0 |
| `confirm_status` | auto / pending / approved / rejected |
| UNIQUE | (src_id, dst_id, rel_type) 防同向重复 |

### `verifications` — 主动验证留痕

| 字段 | 说明 |
|---|---|
| `id` | PK |
| `nid` | FK → nodes |
| `mode` | feynman / recall / generative |
| `paraphrase` | 用户复述原文 |
| `gaps` | JSON 数组：缺失/出错的关键点 |
| `score` | 0.0–1.0 |
| `feedback` | 总评 |

### 向量与全文索引

- `node_vec` — vec0 虚拟表（embedding float[512]），KNN 检索
- `node_fts` — FTS5（title, body, tokenize='trigram'），BM25 排序

---

## 9 类命题边定义

每条边都是"带类型的有向命题"，拒绝"相似就拉线"。

| rel_type | 含义 | 典型场景 |
|---|---|---|
| `implies` | 蕴含 / 因果 | A 成立 ⇒ B 成立 |
| `supports` | 支持 / 证据 | B 为 A 提供证据 |
| `contradicts` | 反对 / 矛盾 | A 与 B 互斥（触发冲突检测） |
| `exemplifies` | 实例 | B 是 A 的具体例子 |
| `refines` | 细化 / 精化 | B 是 A 的更精确版本 |
| `prerequisite_of` | 前提 / 先决 | 学 A 之前必须先掌握 B（构建 DAG） |
| `contrasts` | 对比 / 区分 | A 与 B 的差异点 |
| `merges` | 同义合并 | A 与 B 是同一概念（待人工归档） |
| `relates` | 弱关联 | 有关系但类型不明（建议箱） |

**特殊处理**：
- `prerequisite_of`：插入前调用 `dag.creates_cycle` 检测，成环则降级为 `relates`（置信度 ≤0.6）
- `merges`：始终进 `pending` 待人工确认归档
- `contradicts`：进入 `growth/conflict.py` 矛盾队列，可 resolve(keep/archive_a/archive_b)

---

## 建链引擎与门控

`graph/linker.py` 流程：

1. **召回**：`embed(title+body)` → vec0 Top-20 ∪ FTS Top-10。向量扩展不可用时退化为 FTS Top-50 ∪ 全量余弦 Top-20。
2. **过滤**：排除自身、archived 节点、同源材料内部段落（Zettelkasten：链接发生在不同来源之间）。
3. **判定**：`provider.judge_relation(a, b)` → `{rel_type, confidence, rationale}` 或 None。
4. **去重**：任意方向已存在同类型边则跳过（避免双向重复）。
5. **门控**：

| 置信度 | 动作 | confirm_status |
|---|---|---|
| ≥ 0.85 (`auto_threshold`) | 自动入图 | `auto` |
| 0.5–0.85 (`pending_threshold`) | 建议箱 | `pending` |
| < 0.5 | 丢弃 | — |

6. **DAG 校验**：`prerequisite_of` 调 `creates_cycle`，成环降级为 `relates`。
7. **孤儿标记**：入库超 48h 仍无边的节点 → `pending_link`。

---

## FSRS 间隔重复

`growth/recall.py` 使用 `fsrs >= 6.x` 的 `Scheduler` + `Card` API。

- **到期队列** `due_cards`：`recall_state='{}'`（新卡）或 `date(due) <= date('now')`。
- **评分** `review(nid, rating)`：again(1)/hard(2)/good(3)/easy(4) → `sched.review_card` → 更新 stability/difficulty/due/reps/lapses。
- **状态持久化**：FSRS Card 字段（card_id/state/step/stability/difficulty/due/last_review）+ 业务字段（reps/lapses）存入 `nodes.recall_state` JSON。

> 历史坑：`due` 是 datetime 字符串，与 `date('now')` 直接比较会漏当天到期卡片。修正为 `date(json_extract(recall_state,'$.due')) <= date('now')`。

---

## GraphRAG 对话问答

`growth/qa.py` 的 `ask(con, question)` 流程：

1. **召回**：`embed(question)` → vec0 Top-K ∪ FTS（jieba 分词）Top-K。无向量索引时全量余弦兜底。
2. **图扩展**：对召回节点沿 1 跳边补相邻节点进 context（`db.neighbors`，限制 context 长度）。
3. **冲突感知**：查询召回节点对里的 `contradicts` 边（`confirm_status!='rejected'`）。
4. **生成**：`provider.answer(question, cited_nodes, contradictions)`。
   - OpenAI 模式：系统提示强制每个事实后用 `[#节点id]` 标注来源，矛盾时明确"A 说 X，但 B 说 Y"并标两侧 id，禁止编造。
   - rule 模式降级：返回节点列表（不生成答案，供前端展示）。
5. **返回**：`{question, answer, cited_nodes, contradictions}`。

---

## 主动验证：Feynman / 生成提问 / 盲测

`growth/verify.py` 三种模式：

### Feynman 模式（LLM 找 gap）

`feynman(con, nid, paraphrase)`：
1. 加载节点原文。
2. `provider.feynman(node, paraphrase)` → `{score, gaps, feedback}`。
   - OpenAI：LLM 比较复述 vs 原文，输出准确度分 + 缺失/出错关键点 + 总评。
   - rule 降级：向量相似度 ×0.5 + 关键术语召回率 ×0.5。
3. 落库 `verifications`（mode='feynman'），返回最近 5 条历史。

### 生成提问（generative）

`generate_questions(con, nid, n)`：
- `provider.generate_questions(node, n)` → N 个开放式检验提问。
- OpenAI：教学提问设计专家，要求不问是非、引发复述/类比/反例。
- rule 降级：按节点类型（claim/question/concept）模板生成。
- 留痕 mode='generative'。

### 盲测（纯前端）

前端实现，不落库后端：
1. 节点选择器只显示标题，隐藏 body。
2. 用户凭记忆复述（textarea）。
3. 点击"揭示原文"显示 body。
4. 自评 again/hard/good/easy → 调 `/api/recall/{nid}/review` 同步 FSRS。

---

## 掌握度指标

`db.node_mastery(con, nid)`：

```
fsrs_score = min(1, reps/5 * 0.6 + min(1, stability/30) * 0.4)
feynman_score = avg(最近 10 次 Feynman score)
score = 有 Feynman 时 0.4*fsrs + 0.6*feynman，无则纯 fsrs
```

`db.all_mastery(con)`：全库平均分 + 分级分布（low<0.4 / mid<0.75 / high）+ 已验证节点数。

`/api/stats` 新增字段：`mastery_avg`、`mastery_verified`、`feynman_count`。

---

## 部署与降级

- **本地优先**：单文件 SQLite，无外部服务依赖。
- **sqlite_vec 加载**：优先 `con.load_extension(sqlite_vec.loadable_path())`（最稳），失败回退 `enable_load_extension + sqlite_vec.load`。扩展不可用时向量检索优雅降级为 FTS+全量余弦。
- **LLM 降级**：无 `KE_LLM_KEY` 时自动用 `RuleProvider`（确定性规则实现，闭环可跑）。
- **embedding 降级**：`KE_EMBEDDING=light`（内置 512 维确定性向量，零依赖）；`bge`（BGE-small-zh 本地语义模型，需 torch/transformers）。
- **CI**：GitHub Actions 跑 pytest + `scripts/smoke.sh` 端到端冒烟。

---

## API 速查

所有路由见 `knowledge_engine/web/app.py`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/stats` | 指标面板（含 mastery_avg/feynman_count） |
| GET | `/api/graph?root=&depth=` | 子图（节点+边） |
| GET | `/api/diagnostics` | 孤儿 + pending 边 + 矛盾边 |
| GET/POST | `/api/nodes` / `/api/edges` | 列表（status 过滤） |
| POST | `/api/edges/{eid}/confirm` | approve/reject/delete |
| POST | `/api/ingest` | 文本入库 |
| POST | `/api/ingest/url` | 链接提取入库 |
| POST | `/api/ingest/audio` | 音频转写入库 |
| POST | `/api/ingest/image` | 图片 OCR 入库 |
| GET | `/api/timeline?date=` | 按日分组的时间线 |
| GET | `/api/recall` | 今日到期卡片 |
| POST | `/api/recall/{nid}/review` | FSRS 评分 |
| GET | `/api/conflicts` | 矛盾队列 |
| POST | `/api/conflicts/{eid}/resolve` | keep/archive_a/archive_b |
| POST | `/api/synthesize` | 每周综合 |
| POST | `/api/ask` | GraphRAG 问答 |
| POST | `/api/verify/feynman` | Feynman 复述评分 |
| POST | `/api/verify/questions` | 生成检验提问 |
| GET | `/api/verify/history/{nid}` | 验证历史 |
| GET | `/api/mastery` | 全库掌握度 |
| GET | `/api/mastery/{nid}` | 单节点掌握度 |
| POST | `/api/link` | 建链 + 孤儿标记 |

---

## 测试覆盖

`tests/` 共 44+ 用例，按域分布：

| 文件 | 用例 | 覆盖 |
|---|---|---|
| `test_db.py` | 4 | CRUD / 向量+FTS / 子图 / 统计 |
| `test_linker.py` | 3 | 建链+双向去重 / 孤儿标记 / 前提环 |
| `test_pipeline.py` | 2 | 去重 / 质量门 |
| `test_recall.py` | 3 | FSRS 到期/评分/状态 |
| `test_qa.py` | 3 | 召回+答案 / 空库 / 冲突感知 |
| `test_verify.py` | 6 | Feynman 评分+留痕 / 空复述 / 生成提问 / 掌握度 |
| `test_maturity.py` | 24 | 9 类边 × 非法拦截 / 双向去重 / 门控 auto+pending+丢弃 / DAG 多跳+环 / 综合 / 矛盾 resolve / 指标 / 孤儿 48h |
