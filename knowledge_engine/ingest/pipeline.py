"""采集队列 + 统一加工流水线（多模态归一为文本中间态后走同一条链路）。"""
from .. import db
from ..config import Config
from ..embed import fingerprint
from ..llm.base import get_provider


def ingest_text(con, text: str, *, kind: str = "clipboard", title: str = "",
                raw_path: str = "", provider=None, cfg: Config | None = None) -> dict:
    """统一入口：去重 → 原子化 → 质量门 → 入图。返回统计。"""
    cfg = cfg or Config()
    provider = provider or get_provider(cfg)
    text = text.strip()
    if not text:
        return {"source_id": None, "added": 0, "deduped": True, "skipped": 0, "node_ids": []}

    fp = fingerprint(text)
    existing = db.find_source_by_fingerprint(con, fp)
    if existing:
        return {"source_id": existing["id"], "added": 0, "deduped": True, "skipped": 0, "node_ids": []}

    sid = db.insert_source(con, kind=kind, text_extracted=text, raw_path=raw_path,
                           title=title[:200], fingerprint=fp)

    items = provider.atomize(text) or []
    node_ids = []
    added = 0
    for it in items[:16]:
        body = it.get("body", "").strip()
        if len(body) < 20 or len(body) > 800:
            continue  # 质量门：过短/过长不入图
        ntype = it.get("type", "claim") if it.get("type", "claim") in ("concept", "claim", "question") else "claim"
        nid = db.insert_node(con, ntype, it.get("title", body[:24])[:120], body, sid)
        node_ids.append(nid)
        added += 1
    return {"source_id": sid, "added": added, "deduped": False, "skipped": len(items) - added, "node_ids": node_ids}


def ingest_url(con, url: str, provider=None, cfg: Config | None = None) -> dict:
    """链接采集：抓取正文后走统一流水线。"""
    from .extractors import extract_url
    title, text = extract_url(url)
    result = ingest_text(con, text, kind="url", title=f"{title} ({url})",
                         raw_path=url, provider=provider, cfg=cfg)
    return result


def ingest_file(con, path: str, provider=None, cfg: Config | None = None) -> dict:
    """本地文本文件采集。"""
    from .extractors import extract_file
    title, text = extract_file(path)
    return ingest_text(con, text, kind="file", title=title, raw_path=path, provider=provider, cfg=cfg)


def ingest_audio(con, path: str, provider=None, cfg: Config | None = None) -> dict:
    """音频采集：ASR 转写 → 统一流水线。"""
    from .audio import transcribe_audio
    text = transcribe_audio(path)
    title = path.rsplit("/", 1)[-1]
    return ingest_text(con, text, kind="audio", title=title, raw_path=path, provider=provider, cfg=cfg)
