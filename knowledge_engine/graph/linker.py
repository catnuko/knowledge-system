"""建链引擎：召回 → 命题判定 → 置信度门控 → 前提 DAG 校验 → 入边。"""
from datetime import datetime, timedelta

from .. import db
from ..config import Config
from ..embed import embed
from ..llm.base import get_provider


def link_node(con, nid: int, provider=None, cfg: Config | None = None) -> dict:
    """对单个新节点执行建链。返回 {linked, pending, rejected, cycles}。"""
    cfg = cfg or Config()
    provider = provider or get_provider(cfg)
    node = db.get_node(con, nid)
    if node is None:
        return {"linked": 0, "pending": 0, "cycles": 0}

    # 召回：向量 Top-20 ∪ FTS Top-10，排除自身
    vec = embed(node["title"] + " " + node["body"])
    candidates: set[int] = set()
    for r in db.vector_search(con, vec, k=20):
        candidates.add(r["rowid"])
    query = _fts_query(node["title"])
    if query:
        for r in db.fts_search(con, query, k=10):
            candidates.add(r["rowid"])
    candidates.discard(nid)

    stat = {"linked": 0, "pending": 0, "cycles": 0}
    node_dict = {"title": node["title"], "body": node["body"], "type": node["type"]}
    for cid in sorted(candidates):
        cand = db.get_node(con, cid)
        if cand is None or cand["status"] == "archived":
            continue
        # 同源材料内部段落不互相建链（Zettelkasten：链接发生在不同来源之间，同源由来源结构承载）
        if cand["source_ref"] is not None and cand["source_ref"] == node["source_ref"]:
            continue
        result = provider.judge_relation(node_dict, {"title": cand["title"], "body": cand["body"], "type": cand["type"]})
        if not result:
            continue
        rel = result.get("rel_type")
        conf = float(result.get("confidence", 0.0))
        rationale = result.get("rationale", "")[:200]
        # 去重：任意方向已存在同类型边则跳过（避免双向重复）
        dup = con.execute(
            """SELECT 1 FROM edges WHERE rel_type=?
               AND ((src_id=? AND dst_id=?) OR (src_id=? AND dst_id=?))""",
            (rel, nid, cid, cid, nid),
        ).fetchone()
        if dup:
            continue
        if rel == "merges":
            # 同义合并：建边 + 标记新节点，交给人工决定归档
            db.insert_edge(con, nid, cid, "merges", rationale, conf, "pending")
            stat["pending"] += 1
            continue
        if rel == "prerequisite_of" and db_dag_cycle(con, nid, cid):
            stat["cycles"] += 1
            # 成环：降级为 relates 待人工确认（方案 §6.1 规则）
            rel, conf = "relates", min(conf, 0.6)
        if conf >= cfg.auto_threshold:
            confirm = "auto"
            stat["linked"] += 1
        elif conf >= cfg.pending_threshold:
            confirm = "pending"
            stat["pending"] += 1
        else:
            continue
        db.insert_edge(con, nid, cid, rel, rationale, conf, confirm)
    return stat


def db_dag_cycle(con, src: int, dst: int) -> bool:
    from .dag import creates_cycle
    return creates_cycle(con, src, dst)


def link_all_pending(con, provider=None, cfg: Config | None = None, limit: int = 50) -> dict:
    """为所有尚未建链的新节点执行建链。"""
    cfg = cfg or Config()
    rows = con.execute(
        """SELECT n.id FROM nodes n
           WHERE n.status = 'active'
             AND NOT EXISTS (SELECT 1 FROM edges e
                             WHERE (e.src_id = n.id OR e.dst_id = n.id) AND e.confirm_status != 'rejected')
           ORDER BY n.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    total = {"linked": 0, "pending": 0, "cycles": 0}
    for r in rows:
        s = link_node(con, r["id"], provider, cfg)
        for k in total:
            total[k] += s[k]
    return total


def mark_orphans(con, cfg: Config | None = None) -> int:
    """孤儿规则：入库超 48h 仍无边 → pending_link。"""
    cfg = cfg or Config()
    cutoff = (datetime.now() - timedelta(hours=cfg.orphan_hours)).strftime("%Y-%m-%d %H:%M:%S")
    cur = con.execute(
        """UPDATE nodes SET status='pending_link', updated_at=datetime('now')
           WHERE status='active' AND created_at < ?
             AND NOT EXISTS (SELECT 1 FROM edges e
                             WHERE (e.src_id=nodes.id OR e.dst_id=nodes.id) AND e.confirm_status!='rejected')""",
        (cutoff,),
    )
    con.commit()
    return cur.rowcount


def _fts_query(title: str) -> str:
    """从标题提取 2-4 字的关键片段做 FTS 查询（trigram 需要连续字符）。"""
    import re
    toks = [t for t in re.split(r"[^\w\u4e00-\u9fff]+", title) if t]
    if not toks:
        return ""
    words = [t for t in toks if len(t) >= 2]
    return " ".join(words[:4]) or ""
