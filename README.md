# SecondMe · 第二个我

[中文文档](README_zh.md) | **English**

Multi-source capture (text / links / audio) → AI atomization → a personal knowledge network that grows continuously, grounded in cognitive science theory.

## Status: MVP v0.2

A local-first, single-file SQLite (with vector retrieval and full-text search) knowledge network engine. **No API key required to run the full loop**: capture → atomize → scientific linking → spaced repetition recall → synthesis → conflict detection → conversational Q&A → active verification (Feynman).

## Quick Start

```bash
# Install with uv (recommended): auto-creates venv + locks dependencies
uv sync                    # Install deps (sqlite-vec / fsrs / trafilatura / jieba / fastapi)
uv run ke ingest-text "Spaced repetition schedules reviews along the forgetting curve to improve long-term retention" --title "Spaced Repetition"
ke ingest-file notes.md     # Local files
ke ingest-url https://example.com/article   # Web extraction (trafilatura)
ke link --all               # Link: auto-edges + suggestion box + orphan marking
ke recall                   # Today's due cards
ke review 1 good            # Rate: again / hard / good / easy
ke synthesize               # Weekly synthesis (connected components → summary → new node back into graph)
ke conflicts                # Conflict detection report
ke stats                    # Metrics dashboard (mastery_avg / Feynman count)
ke serve --port 8000        # Web panel (graph / capture / recall / suggestions / conflicts / Q&A / active verification)
# Or: uv run ke serve --port 8000
```

### Web Panel Modules

- **Conversational Q&A**: GraphRAG recall → graph expansion → conflict awareness → forced citation `[#node_id]`, rule mode degrades to node list
- **Active Verification**: Three modes — blind test (frontend hides original + self-rating syncs FSRS) / Feynman (user paraphrase → LLM finds gaps + scores + persists) / generated questions (LLM generates open-ended verification questions per node)
- **Mastery Metrics**: FSRS retention (reps/stability) + Feynman average weighted, outputs per-node and library-wide grade distribution

## Core Philosophy

- **Capture is not a barrier**: 5 source types (browser, clipboard, Feishu, URL extraction, audio transcription + image OCR) extensible via adapter pattern, all unified into a "text intermediate state"
- **Scientific linking**: Network = atomic nodes + 9 typed propositional directed edges + prerequisite DAG, every edge is explainable and auditable — no "similarity means connection"
- **Growth is the main engine**: FSRS daily recall + weekly community synthesis + conflict detection + Feynman active verification — the north star metric is mastery, not storage volume

## Scientific Foundation

| Theory | Design Rule |
|---|---|
| Ausubel Assimilation Theory | New nodes must link to existing structure, otherwise enter pending pool |
| Novak Concept Maps | Edges must be typed propositions (9 directed edge types) |
| Knowledge Space Theory (KST) | Prerequisite DAG determines learning & recall order, cycle detection enforced |
| Retrieval Practice + FSRS | Schedule recall along forgetting curve, prompts first |
| GraphRAG | Weekly synthesis based on graph communities |

## Architecture (5 Layers + Growth Loop)

```
Capture  →  Processing  →  Storage  →  Linking  →  Growth
text/file/URL/audio  |  atomize/dedup/quality gate  |  SQLite+vec0+FTS5  |  recall/judge/gate/DAG  |  FSRS/synthesis/conflict/metrics
```

## Data Model

- `sources` — raw materials (kind: url/clipboard/message/file/audio/synthesis + fingerprint dedup)
- `nodes` — atomic notes (concept/claim/question + FSRS memory state)
- `edges` — 9 typed propositional edges (implies/supports/contradicts/exemplifies/refines/prerequisite_of/contrasts/merges/relates)
- `verifications` — active verification log (mode: feynman/recall/generative + paraphrase/gaps/score/feedback)
- `node_vec` (vec0 vector KNN) + `node_fts` (trigram full-text) — dual-channel recall
- Graph queries: recursive CTE, no graph database (migration trigger: nodes >10⁵ or need real-time graph algorithms)

## Link Gating (Auditable)

| Confidence | Action |
|---|---|
| ≥ 0.85 | Auto-merge (reversible) |
| 0.5 – 0.85 | Suggestion box, manual confirmation |
| < 0.5 | Discard |

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `KE_DB` | `~/.knowledge_engine/ke.db` | Database path |
| `KE_LLM` | `rule` | `rule`=rule mode (zero deps); `openai`=OpenAI-compatible API |
| `KE_LLM_KEY` / `KE_LLM_BASE` / `KE_LLM_MODEL` | — / deepseek / deepseek-chat | e.g. DeepSeek or Qwen |
| `KE_EMBEDDING` | `light` | `light`=built-in lightweight vector; `bge`=BGE-small-zh local semantic model (recommended) |

### Enable BGE Semantic Embedding (Recommended)

```bash
uv pip install torch transformers      # CPU torch: uv pip install torch --index-url https://download.pytorch.org/whl/cpu
# First call auto-downloads BAAI/bge-small-zh-v1.5 (~100MB) from HuggingFace
export KE_EMBEDDING=bge
ke ingest-text "..."
ke link --all
```

> Note: Switching embedding backends changes vector semantics — recommend rebuilding the knowledge base (`rm ~/.knowledge_engine/ke.db*`).

### Enable OpenAI-Compatible LLM (improves atomization/linking/synthesis quality)

```bash
export KE_LLM=openai KE_LLM_KEY=sk-xxx KE_LLM_BASE=https://api.deepseek.com/v1 KE_LLM_MODEL=deepseek-chat
```

### Audio Sources (interface reserved)

```bash
uv pip install funasr modelscope    # Audio transcription (Chinese-optimized, local inference)
```

## Testing

```bash
uv run pytest tests/ -q        # 44+ tests: storage/pipeline/linking/recall/Q&A/active verification/maturity (9 edge types × gating × DAG × synthesis × conflict × metrics × orphan)
uv run bash scripts/smoke.sh    # End-to-end smoke: capture→link→recall→synthesize→conflicts→metrics
```

## Documentation

- `docs/architecture.md` — Architecture & data model, 9 edge type definitions, link gating, FSRS/GraphRAG/Feynman mechanisms, API reference
- `docs/knowledge-system-mvp-plan.html` — MVP architecture & implementation plan v1.1

## Packaging: Desktop / Web

Same frontend (`knowledge_engine/web/static/`), three deployment forms:

| Form | Method | Notes |
|---|---|---|
| Web (zero config) | `ke serve --port 8000` | Backend serves panel directly |
| Web (static deploy) | `bash web/build.sh` | Produces `web/dist/`, Nginx/CDN serves, `/api` reverse proxy (see `web/deploy.example.conf`) |
| Desktop (Tauri v2) | `cd desktop && npm install && npm run tauri:dev` | Shell auto-starts local backend & loads panel; platform configs in `desktop/src-tauri/configs/{windows,linux,macos}/` |

Desktop and Web share the same panel code — see `desktop/README.md` for desktop details.

## Roadmap (10 Weeks)

| Phase | Content |
|---|---|
| Phase 0 (W1) | Data model schema + vec0 + FSRS + capture queue abstraction |
| Phase 1a (W2-3) | Text & link sources: browser extension / clipboard / Feishu / URL extraction |
| Phase 1b (W4) | Audio source: FunASR local transcription → summarize into graph |
| Phase 2 (W6-7) | Linking engine + suggestion box + graph visualization |
| Phase 3 (W8-9) | Recall queue + weekly synthesis + conflict detection + metrics dashboard |
| Phase 4 (W10) | 30-day review + extended sources #7+ |

## License

MIT — see [LICENSE](LICENSE). Open source, free to use, modify, and distribute.
