"""冲突检测：contradicts 边 → 矛盾报告。"""
from .. import db


def conflicts(con) -> list[dict]:
    rows = con.execute(
        """SELECT e.id, e.src_id, e.dst_id, e.rationale, e.confidence, e.confirm_status
           FROM edges e WHERE e.rel_type = 'contradicts' AND e.confirm_status != 'rejected'
           ORDER BY e.id DESC LIMIT 100""").fetchall()
    out = []
    for e in rows:
        s = db.get_node(con, e["src_id"])
        d = db.get_node(con, e["dst_id"])
        out.append({
            "edge_id": e["id"],
            "a": {"id": e["src_id"], "title": s["title"] if s else "?", "body": s["body"] if s else ""},
            "b": {"id": e["dst_id"], "title": d["title"] if d else "?", "body": d["body"] if d else ""},
            "rationale": e["rationale"],
            "confidence": e["confidence"],
            "status": e["confirm_status"],
        })
    return out


def resolve(con, edge_id: int, action: str) -> None:
    """action: keep / archive_a / archive_b（保留并存标注 / 归档一方）。"""
    e = con.execute("SELECT * FROM edges WHERE id=?", (edge_id,)).fetchone()
    if not e:
        raise KeyError(edge_id)
    if action == "keep":
        db.set_edge_confirm(con, edge_id, "approved")
    elif action in ("archive_a", "archive_b"):
        nid = e["src_id"] if action == "archive_a" else e["dst_id"]
        db.update_node_status(con, nid, "archived")
        db.set_edge_confirm(con, edge_id, "rejected")
    else:
        raise ValueError(f"未知动作: {action}")
