"""FastAPI Web 面板：图谱、采集（文本/链接/音频）、回取、建议箱、矛盾、综合。"""
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import db
from ..config import SETTING_KEYS, Config
from ..llm.base import get_provider

STATIC_DIR = Path(__file__).parent / "static"


class IngestIn(BaseModel):
    text: str
    title: str = ""
    kind: str = "clipboard"


class IngestUrlIn(BaseModel):
    url: str


class ReviewIn(BaseModel):
    rating: str


class EdgeConfirmIn(BaseModel):
    action: str  # approve | reject | delete


class ConflictResolveIn(BaseModel):
    action: str  # keep | archive_a | archive_b


class AskIn(BaseModel):
    question: str


class FeynmanIn(BaseModel):
    nid: int
    paraphrase: str


class QuestionsIn(BaseModel):
    nid: int
    n: int = 3


class SettingsIn(BaseModel):
    settings: dict[str, str]


def _mask_key(key: str) -> str:
    return f"***{key[-4:]}" if len(key) > 4 else ("***" if key else "")


# 上传大小上限（字节）：音频 200MB / 图片 20MB
MAX_UPLOAD = {"audio": 200 * 1024 * 1024, "image": 20 * 1024 * 1024}


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config()
    app = FastAPI(title="knowledge-engine", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def _con():
        return db.connect(cfg)

    def _settings_payload() -> dict:
        """当前设置（key 脱敏）+ 预设目录，供设置面板渲染。"""
        from ..ingest.audio import ASR_PRESETS
        from ..llm import openai as llm_openai

        def cur(k):
            return getattr(cfg, k)

        resolved_asr = {}
        try:
            from ..ingest.audio import resolve_asr
            resolved_asr = resolve_asr(cfg)
        except Exception:
            pass
        return {
            "llm": {
                "provider": cur("llm_provider"),
                "base": cur("llm_base"),
                "model": cur("llm_model"),
                "key_masked": _mask_key(cur("llm_key")),
                "has_key": bool(cur("llm_key")),
                "presets": llm_openai.LLM_PRESETS,
            },
            "asr": {
                "provider": cur("asr_provider"),
                "base": resolved_asr.get("base", ""),
                "model": resolved_asr.get("model", ""),
                "key_masked": _mask_key(cur("asr_key")),
                "has_key": bool(cur("asr_key")),
                "presets": ASR_PRESETS,
            },
            "embedding": cur("embedding"),
        }

    @app.get("/api/settings")
    def api_settings_get():
        return _settings_payload()

    @app.put("/api/settings")
    def api_settings_put(body: SettingsIn):
        cfg.save(body.settings)
        return _settings_payload()

    @app.post("/api/settings/test-llm")
    def api_settings_test_llm():
        """用一次最小请求验证 LLM 连通性。"""
        provider = get_provider(cfg)
        if provider.name != "openai":
            return {"ok": False, "error": "当前为 rule 模式：请在设置中选择 LLM 服务并填写 API key"}
        return provider.ping()

    @app.post("/api/settings/test-asr")
    def api_settings_test_asr():
        """用 1 秒静音 wav 验证 ASR 连通性（不产生实际转写内容）。"""
        import io
        import struct
        import wave

        from ..ingest.audio import _transcribe_api, resolve_asr

        resolved = resolve_asr(cfg)
        if not resolved["base"] or not resolved["key"]:
            return {"ok": False, "error": "请先选择转写服务并填写 API key"}
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(struct.pack("<h", 0) * 16000)
        fd, tmp = tempfile.mkstemp(prefix="ke_asr_test_", suffix=".wav")
        try:
            Path(tmp).write_bytes(buf.getvalue())
            text = _transcribe_api(tmp, resolved["base"], resolved["key"], resolved["model"])
            return {"ok": True, "detail": f"{resolved['model']} @ {resolved['base']} 连通正常", "text": text[:50]}
        except RuntimeError as e:
            # 静音音频返回空转写也视为连通（HTTP 层已通过）
            if "返回结果为空" in str(e):
                return {"ok": True, "detail": f"{resolved['model']} @ {resolved['base']} 连通正常（静音）"}
            return {"ok": False, "error": str(e)[:300]}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}
        finally:
            Path(tmp).unlink(missing_ok=True)

    @app.get("/api/stats")
    def api_stats():
        from ..growth.metrics import all_metrics
        con = _con()
        try:
            return all_metrics(con)
        finally:
            con.close()

    @app.get("/api/graph")
    def api_graph(root: int = 1, depth: int = 2):
        con = _con()
        try:
            nodes, edges = db.subgraph(con, root, depth)
            return {"nodes": nodes, "edges": edges}
        finally:
            con.close()

    @app.get("/api/diagnostics")
    def api_diagnostics():
        """图谱诊断：孤儿节点 + pending 边 + 矛盾边，前端用于高亮排查。"""
        con = _con()
        try:
            orphans = [dict(r) for r in con.execute(
                """SELECT id, type, title, status FROM nodes n
                   WHERE n.status IN ('active','pending_link')
                   AND NOT EXISTS (SELECT 1 FROM edges e
                                   WHERE (e.src_id=n.id OR e.dst_id=n.id)
                                   AND e.confirm_status!='rejected')""").fetchall()]
            pending = [dict(r) for r in con.execute(
                """SELECT id, src_id, dst_id, rel_type, confidence
                   FROM edges WHERE confirm_status='pending' ORDER BY id""").fetchall()]
            contradictions = [dict(r) for r in con.execute(
                """SELECT id, src_id, dst_id, confidence
                   FROM edges WHERE rel_type='contradicts'
                   AND confirm_status!='rejected' ORDER BY id""").fetchall()]
            return {"orphans": orphans, "pending_edges": pending,
                    "contradictions": contradictions}
        finally:
            con.close()

    @app.get("/api/nodes")
    def api_nodes(status: str | None = None, limit: int = 200):
        con = _con()
        try:
            return {"nodes": [dict(r) for r in db.list_nodes(con, status, limit)]}
        finally:
            con.close()

    @app.get("/api/edges")
    def api_edges(status: str | None = None):
        con = _con()
        try:
            return {"edges": [dict(r) for r in db.list_edges(con, status)]}
        finally:
            con.close()

    @app.post("/api/edges/{eid}/confirm")
    def api_edge_confirm(eid: int, body: EdgeConfirmIn):
        con = _con()
        try:
            if body.action == "approve":
                db.set_edge_confirm(con, eid, "approved")
            elif body.action == "reject":
                db.set_edge_confirm(con, eid, "rejected")
            elif body.action == "delete":
                db.delete_edge(con, eid)
            else:
                raise HTTPException(400, "action 必须是 approve/reject/delete")
            return {"ok": True}
        finally:
            con.close()

    @app.post("/api/ingest")
    def api_ingest(body: IngestIn):
        from ..ingest.pipeline import ingest_text
        con = _con()
        try:
            provider = get_provider(cfg)
            return ingest_text(con, body.text, kind=body.kind, title=body.title, provider=provider, cfg=cfg)
        finally:
            con.close()

    @app.post("/api/ingest/url")
    def api_ingest_url(body: IngestUrlIn):
        from ..ingest.pipeline import ingest_url
        con = _con()
        try:
            provider = get_provider(cfg)
            return ingest_url(con, body.url, provider=provider, cfg=cfg)
        except (RuntimeError, FileNotFoundError) as e:
            raise HTTPException(422, str(e))
        finally:
            con.close()

    async def _save_upload(file: UploadFile, max_bytes: int) -> str:
        """保存上传文件到临时目录，超限返回 413。"""
        suffix = Path(file.filename or "upload").suffix or ".bin"
        fd, path = tempfile.mkstemp(prefix="ke_upload_", suffix=suffix)
        size = 0
        with open(fd, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    f.close()
                    Path(path).unlink(missing_ok=True)
                    raise HTTPException(413, f"文件超过大小上限（{max_bytes // (1024 * 1024)} MB）")
                f.write(chunk)
        return path

    @app.post("/api/ingest/audio")
    async def api_ingest_audio(file: UploadFile = File(...)):
        from ..ingest.pipeline import ingest_audio
        if not (file.filename or "").lower().endswith((".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma")):
            raise HTTPException(400, "仅支持音频文件：wav/mp3/m4a/ogg/flac/aac/wma")
        path = await _save_upload(file, MAX_UPLOAD["audio"])
        con = _con()
        try:
            provider = get_provider(cfg)
            return ingest_audio(con, path, provider=provider, cfg=cfg)
        except RuntimeError as e:
            raise HTTPException(422, str(e))
        finally:
            Path(path).unlink(missing_ok=True)
            con.close()

    @app.post("/api/ingest/image")
    async def api_ingest_image(file: UploadFile = File(...)):
        from ..ingest.pipeline import ingest_image
        if not (file.filename or "").lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
            raise HTTPException(400, "仅支持图片文件：png/jpg/jpeg/webp/bmp")
        path = await _save_upload(file, MAX_UPLOAD["image"])
        con = _con()
        try:
            provider = get_provider(cfg)
            return ingest_image(con, path, provider=provider, cfg=cfg)
        except RuntimeError as e:
            raise HTTPException(422, str(e))
        finally:
            Path(path).unlink(missing_ok=True)
            con.close()

    @app.get("/api/timeline")
    def api_timeline(date: str | None = None, limit: int = 200):
        """按日分组的来源时间线。date=YYYY-MM-DD 过滤当天；不传返回最近 limit 条。"""
        con = _con()
        try:
            if date:
                rows = con.execute(
                    """SELECT id, kind, title, raw_path, captured_at
                       FROM sources
                       WHERE date(captured_at) = date(?)
                       ORDER BY captured_at DESC LIMIT ?""",
                    (date, limit),
                ).fetchall()
            else:
                rows = con.execute(
                    """SELECT id, kind, title, raw_path, captured_at
                       FROM sources ORDER BY captured_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            items = [dict(r) for r in rows]
            # 按日分组
            grouped: dict[str, list] = {}
            for it in items:
                day = (it.get("captured_at") or "")[:10]
                grouped.setdefault(day, []).append(it)
            return {"days": [{"date": d, "items": grouped[d]} for d in sorted(grouped, reverse=True)]}
        finally:
            con.close()

    @app.get("/api/recall")
    def api_recall(limit: int = 20):
        from ..growth.recall import due_cards
        con = _con()
        try:
            return {"cards": due_cards(con, limit)}
        finally:
            con.close()

    @app.post("/api/recall/{nid}/review")
    def api_review(nid: int, body: ReviewIn):
        from ..growth.recall import review
        con = _con()
        try:
            return review(con, nid, body.rating)
        except ValueError as e:
            raise HTTPException(400, str(e))
        finally:
            con.close()

    @app.get("/api/conflicts")
    def api_conflicts():
        from ..growth.conflict import conflicts
        con = _con()
        try:
            return {"conflicts": conflicts(con)}
        finally:
            con.close()

    @app.post("/api/conflicts/{eid}/resolve")
    def api_conflict_resolve(eid: int, body: ConflictResolveIn):
        from ..growth.conflict import resolve
        con = _con()
        try:
            resolve(con, eid, body.action)
            return {"ok": True}
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e))
        finally:
            con.close()

    @app.post("/api/synthesize")
    def api_synthesize():
        from ..growth.synthesize import weekly_synthesis
        con = _con()
        try:
            provider = get_provider(cfg)
            return weekly_synthesis(con, provider)
        finally:
            con.close()

    @app.post("/api/ask")
    def api_ask(body: AskIn):
        """GraphRAG 问答：召回 + 图扩展 + 冲突感知 + provider.answer。"""
        from ..growth.qa import ask
        con = _con()
        try:
            provider = get_provider(cfg)
            return ask(con, body.question, provider=provider, cfg=cfg)
        finally:
            con.close()

    @app.post("/api/verify/feynman")
    def api_feynman(body: FeynmanIn):
        """Feynman 验证：用户复述 → LLM 找 gap → 落库 → 返回 score/gaps/feedback。"""
        from ..growth.verify import feynman
        con = _con()
        try:
            provider = get_provider(cfg)
            return feynman(con, body.nid, body.paraphrase, provider=provider, cfg=cfg)
        except KeyError as e:
            raise HTTPException(404, str(e))
        finally:
            con.close()

    @app.post("/api/verify/questions")
    def api_questions(body: QuestionsIn):
        """针对节点生成 n 个开放式检验提问（生成式提问）。"""
        from ..growth.verify import generate_questions
        con = _con()
        try:
            provider = get_provider(cfg)
            qs = generate_questions(con, body.nid, body.n, provider=provider, cfg=cfg)
            return {"nid": body.nid, "questions": qs}
        except KeyError as e:
            raise HTTPException(404, str(e))
        finally:
            con.close()

    @app.get("/api/verify/history/{nid}")
    def api_verify_history(nid: int, mode: str | None = None, limit: int = 20):
        """节点的验证历史。"""
        con = _con()
        try:
            from .. import db as _db
            rows = _db.list_verifications(con, nid, mode=mode, limit=limit)
            return {"history": [dict(r) for r in rows]}
        except Exception as e:
            raise HTTPException(500, str(e))
        finally:
            con.close()

    @app.get("/api/mastery")
    def api_mastery():
        """知识库总体掌握度：平均分 + 分级分布 + 已验证节点数。"""
        from ..growth.verify import all_mastery
        con = _con()
        try:
            return all_mastery(con)
        finally:
            con.close()

    @app.get("/api/mastery/{nid}")
    def api_node_mastery(nid: int):
        """单节点掌握度。"""
        from ..growth.verify import node_mastery
        con = _con()
        try:
            return node_mastery(con, nid)
        except Exception as e:
            raise HTTPException(500, str(e))
        finally:
            con.close()

    @app.post("/api/link")
    def api_link():
        from ..graph.linker import link_all_pending, mark_orphans
        con = _con()
        try:
            provider = get_provider(cfg)
            s = link_all_pending(con, provider, cfg)
            s["orphans"] = mark_orphans(con, cfg)
            return s
        finally:
            con.close()

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app
