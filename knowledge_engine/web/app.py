"""FastAPI Web 面板：图谱、采集（文本/链接/音频）、回取、建议箱、矛盾、综合。"""
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import db
from ..config import Config
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


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config()
    app = FastAPI(title="knowledge-engine", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def _con():
        return db.connect(cfg)

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

    async def _save_upload(file: UploadFile) -> str:
        """保存上传文件到临时目录，返回路径。"""
        suffix = Path(file.filename or "upload").suffix or ".bin"
        fd, path = tempfile.mkstemp(prefix="ke_upload_", suffix=suffix)
        with open(fd, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
        return path

    @app.post("/api/ingest/audio")
    async def api_ingest_audio(file: UploadFile = File(...)):
        from ..ingest.pipeline import ingest_audio
        if not (file.filename or "").lower().endswith((".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma")):
            raise HTTPException(400, "仅支持音频文件：wav/mp3/m4a/ogg/flac/aac/wma")
        path = await _save_upload(file)
        con = _con()
        try:
            provider = get_provider(cfg)
            return ingest_audio(con, path, provider=provider, cfg=cfg)
        except RuntimeError as e:
            raise HTTPException(422, str(e))
        finally:
            Path(path).unlink(missing_ok=True)
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
