# SecondMe · 第二个我

[中文文档](README_zh.md) | **English**

> ## ⚠️ Work in Progress
>
> This project is in an **early stage of active development**. Interfaces, data models, and
> features may change at any time. **No guarantees of usability**: you may encounter bugs,
> missing features, or documentation that does not match actual behavior.
> Trials and feedback are welcome — but do not rely on this project in production or with
> data you care about. See [Releases](https://github.com/catnuko/knowledge-system/releases)
> for current builds.

Multi-source capture (text / links / files) → AI atomization → a personal knowledge network
that grows continuously, grounded in cognitive science theory.

## Current Status: v0.3.0

A local-first knowledge network engine on a single-file SQLite database (with vector search
and full-text indexing). The full loop runs without any API key:
capture → atomize → scientific linking → spaced-repetition recall → synthesis → conflict
detection → conversational Q&A → active verification (Feynman).

- **Web panel** (redesigned in v0.3): desktop-first modern UI with a sidebar and six views
  (Dashboard / Graph / Capture / Review / Verify / Ask); flashcard-style review with full
  keyboard support
- **Desktop app**: Tauri v2 shell; macOS and Windows installers are built and published
  automatically by CI (Windows builds are unsigned — SmartScreen will warn on install)
- **Release automation**: Conventional Commits + release-please; merging the release PR bumps
  versions, generates the changelog, and publishes installers for both platforms

### Known Limitations

- In the default `rule` mode, Q&A / Feynman scoring / synthesis are rule-based fallbacks with
  limited quality; pick an LLM service in the Settings panel (DeepSeek / SiliconFlow /
  DashScope / Zhipu / custom) and paste an API key for full LLM capability
- Audio transcription uses online APIs (SiliconFlow SenseVoice / Alibaba DashScope Qwen-ASR /
  Zhipu GLM-ASR / any OpenAI-compatible endpoint); paste an API key in the Settings panel.
  Local FunASR inference has been removed
- Windows installers are not code-signed
- Data model and APIs may change incompatibly between versions (no migration guarantees)

## Quick Start (from source)

```bash
# uv (recommended): auto-creates venv + locks dependencies
uv sync                    # installs sqlite-vec / fsrs / trafilatura / jieba / fastapi
uv run python -m knowledge_engine.web --port 8000
# open http://127.0.0.1:8000 for the web panel

# Everything happens in the web panel:
#   Capture  — text / URL / files / audio / images
#   Graph    — browse the knowledge network, confirm suggested edges
#   Review   — today's due cards (again / hard / good / easy)
#   Verify   — Feynman active recall + generated questions
#   Ask      — graph-grounded Q&A
#   Settings — configure LLM & audio transcription (paste an API key)
```

This project **no longer ships a command-line interface** (CLI removed in v0.4); for
automation / integration, call the `/api/*` endpoints directly.

## Desktop Installers

Download from [Releases](https://github.com/catnuko/knowledge-system/releases) (built by
GitHub Actions):

| Platform | Artifacts |
|---|---|
| macOS (Apple Silicon) | `knowledge-engine_vX.Y.Z_aarch64.dmg` / `_macos_app.zip` |
| Windows x64 | NSIS installer `.exe` / `.msi` |

The app starts its bundled backend automatically and opens the panel; data lives in
`~/.knowledge_engine/`.

## Core Philosophy

- **Capture is not a barrier**: multiple source types (browser extension, clipboard, URL
  extraction, files, audio transcription) extend via adapters, all unified into a "text
  intermediate state"
- **Scientific linking**: network = atomic nodes + 9 typed propositional directed edges +
  prerequisite DAG; every edge is explainable and auditable — no "similarity means connection"
- **Growth is the main engine**: FSRS daily recall + weekly community synthesis + conflict
  detection + Feynman active verification — the north star metric is mastery, not storage volume

## Scientific Foundation

| Theory | Design Rule |
|---|---|
| Ausubel Assimilation Theory | New nodes must link to existing structure, otherwise enter the pending pool |
| Novak Concept Maps | Edges must be typed propositions (9 directed edge types) |
| Knowledge Space Theory (KST) | Prerequisite DAG determines learning & recall order; cycle detection enforced |
| Retrieval Practice + FSRS | Schedule recall along the forgetting curve, prompts first |
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
- Graph queries use recursive CTEs, no graph database (migration trigger: nodes > 10⁵ or
  real-time graph algorithms needed)

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
| `KE_LLM` | `rule` | `rule` = rule mode (zero deps); `openai` = OpenAI-compatible API |

## Development

```bash
uv run pytest -q           # test suite
bash web/build.sh          # static web packaging → web/dist/
bash desktop/scripts/build-backend.sh   # PyInstaller backend binary (for release)
# Desktop local dev: cd desktop && npm install && npm run tauri:dev
```

CI (GitHub Actions):
- `CI` — tests on push/PR
- `Release Please` — release PR (auto version bump + changelog); merging it builds macOS /
  Windows artifacts and publishes the Release automatically
- `Build & Release` — manual packaging (tag selectable)

## Docs

- `docs/architecture.md` — architecture & data model, 9 edge types, link gating,
  FSRS/GraphRAG/Feynman mechanisms, API reference
- `docs/knowledge-system-mvp-plan.html` — MVP architecture & plan v1.1

## License

MIT — see [LICENSE](LICENSE).
