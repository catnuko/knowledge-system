"""SQLite 存储层：三表 + vec0 向量 + FTS5 全文 + 递归 CTE 图查询。"""
import json
import sqlite3
from pathlib import Path

import sqlite_vec

from .config import Config
from .embed import embed

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('url','clipboard','message','file','audio','synthesis')),
    raw_path TEXT NOT NULL DEFAULT '',
    text_extracted TEXT NOT NULL DEFAULT '',
    fingerprint TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    captured_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('concept','claim','question')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source_ref INTEGER REFERENCES sources(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','archived','pending_link')),
    recall_state TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id INTEGER NOT NULL REFERENCES nodes(id),
    dst_id INTEGER NOT NULL REFERENCES nodes(id),
    rel_type TEXT NOT NULL CHECK (rel_type IN ('implies','supports','contradicts','exemplifies','refines','prerequisite_of','contrasts','merges','relates')),
    rationale TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    confirm_status TEXT NOT NULL DEFAULT 'pending' CHECK (confirm_status IN ('auto','pending','approved','rejected')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (src_id, dst_id, rel_type)
);
CREATE VIRTUAL TABLE IF NOT EXISTS node_vec USING vec0(embedding float[512]);
CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(title, body, tokenize='trigram');
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_nodes_source ON nodes(source_ref);
"""


def connect(cfg: Config | None = None) -> sqlite3.Connection:
    cfg = cfg or Config()
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(cfg.db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    con.executescript(SCHEMA)
    return con


# ---------- 节点 ----------

def insert_node(con, type_: str, title: str, body: str, source_ref: int | None,
                status: str = "active", recall_state: dict | None = None) -> int:
    with con:
        cur = con.execute(
            "INSERT INTO nodes(type, title, body, source_ref, status, recall_state) VALUES (?,?,?,?,?,?)",
            (type_, title, body, source_ref, status, json.dumps(recall_state or {})),
        )
        nid = cur.lastrowid
        # 向量 + 全文索引（与节点同事务）
        vec = embed(title + " " + body)
        con.execute("INSERT INTO node_vec(rowid, embedding) VALUES (?, ?)", (nid, json.dumps(vec)))
        con.execute("INSERT INTO node_fts(rowid, title, body) VALUES (?, ?, ?)", (nid, title, body))
    return nid


def update_node_status(con, nid: int, status: str) -> None:
    with con:
        con.execute("UPDATE nodes SET status=?, updated_at=datetime('now') WHERE id=?", (status, nid))


def update_recall_state(con, nid: int, state: dict) -> None:
    with con:
        con.execute("UPDATE nodes SET recall_state=?, updated_at=datetime('now') WHERE id=?", (json.dumps(state), nid))


def get_node(con, nid: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()


def list_nodes(con, status: str | None = None, limit: int = 500) -> list[sqlite3.Row]:
    if status:
        return con.execute("SELECT * FROM nodes WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
    return con.execute("SELECT * FROM nodes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# ---------- 边 ----------

def insert_edge(con, src_id: int, dst_id: int, rel_type: str, rationale: str,
                confidence: float, confirm_status: str) -> int | None:
    with con:
        try:
            cur = con.execute(
                "INSERT INTO edges(src_id, dst_id, rel_type, rationale, confidence, confirm_status) VALUES (?,?,?,?,?,?)",
                (src_id, dst_id, rel_type, rationale, confidence, confirm_status),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # 重复边


def list_edges(con, status: str | None = None, limit: int = 1000) -> list[sqlite3.Row]:
    if status:
        return con.execute(
            "SELECT * FROM edges WHERE confirm_status=? ORDER BY id LIMIT ?", (status, limit)).fetchall()
    return con.execute("SELECT * FROM edges ORDER BY id LIMIT ?", (limit,)).fetchall()


def set_edge_confirm(con, eid: int, status: str) -> None:
    with con:
        con.execute("UPDATE edges SET confirm_status=? WHERE id=?", (status, eid))


def reject_edge(con, eid: int) -> None:
    with con:
        con.execute("UPDATE edges SET confirm_status='rejected' WHERE id=?", (eid,))


def delete_edge(con, eid: int) -> None:
    with con:
        con.execute("DELETE FROM edges WHERE id=?", (eid,))


# ---------- 来源 ----------

def insert_source(con, kind: str, text_extracted: str = "", raw_path: str = "",
                  title: str = "", fingerprint: str = "") -> int:
    with con:
        cur = con.execute(
            "INSERT INTO sources(kind, text_extracted, raw_path, title, fingerprint) VALUES (?,?,?,?,?)",
            (kind, text_extracted, raw_path, title, fingerprint),
        )
        return cur.lastrowid


def get_source(con, sid: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()


def find_source_by_fingerprint(con, fp: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM sources WHERE fingerprint=? LIMIT 1", (fp,)).fetchone()


# ---------- 检索 ----------

def vector_search(con, vec: list[float], k: int = 20) -> list[sqlite3.Row]:
    """vec0 KNN：返回 {rowid, distance}。"""
    return con.execute(
        "SELECT rowid, distance FROM node_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
        (json.dumps(vec), k),
    ).fetchall()


def fts_search(con, query: str, k: int = 10) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT rowid, bm25(node_fts) AS score FROM node_fts WHERE node_fts MATCH ? ORDER BY score LIMIT ?",
        (query, k),
    ).fetchall()


# ---------- 图查询（递归 CTE） ----------

def neighbors(con, nid: int, depth: int = 2) -> list[sqlite3.Row]:
    """返回与 nid 在 depth 跳内的所有节点及路径信息。"""
    return con.execute(
        """
        WITH RECURSIVE reach(id, hops) AS (
            SELECT src_id, 0 FROM edges WHERE dst_id = ? AND confirm_status != 'rejected'
            UNION
            SELECT dst_id, 0 FROM edges WHERE src_id = ? AND confirm_status != 'rejected'
            UNION
            SELECT e.src_id, r.hops + 1 FROM edges e JOIN reach r ON e.dst_id = r.id
                WHERE r.hops < ? AND e.confirm_status != 'rejected'
            UNION
            SELECT e.dst_id, r.hops + 1 FROM edges e JOIN reach r ON e.src_id = r.id
                WHERE r.hops < ? AND e.confirm_status != 'rejected'
        )
        SELECT DISTINCT reach.id, reach.hops FROM reach JOIN nodes ON reach.id = nodes.id
        WHERE reach.id != ? ORDER BY reach.hops, reach.id LIMIT 200
        """,
        (nid, nid, depth, depth, nid),
    ).fetchall()


def subgraph(con, nid: int, depth: int = 2) -> tuple[list[dict], list[dict]]:
    """返回 (节点列表, 边列表) 用于前端图谱渲染。"""
    ids = [r["id"] for r in neighbors(con, nid, depth)]
    if nid not in ids:
        ids.insert(0, nid)
    if not ids:
        return [], []
    ph = ",".join("?" * len(ids))
    nodes = [dict(r) for r in con.execute(f"SELECT id, type, title, status FROM nodes WHERE id IN ({ph})", ids)]
    edges = [dict(r) for r in con.execute(
        f"""SELECT e.id, e.src_id, e.dst_id, e.rel_type, e.confidence, e.confirm_status
            FROM edges e WHERE e.src_id IN ({ph}) AND e.dst_id IN ({ph})
            AND e.confirm_status != 'rejected'""", ids + ids)]
    return nodes, edges


# ---------- 统计 ----------

def stats(con) -> dict:
    nodes = con.execute("SELECT COUNT(*) c FROM nodes").fetchone()["c"]
    active = con.execute("SELECT COUNT(*) c FROM nodes WHERE status IN ('active','pending_link')").fetchone()["c"]
    edges = con.execute("SELECT COUNT(*) c FROM edges WHERE confirm_status != 'rejected'").fetchone()["c"]
    orphan = con.execute(
        """SELECT COUNT(*) c FROM nodes n WHERE n.status IN ('active','pending_link')
           AND NOT EXISTS (SELECT 1 FROM edges e WHERE (e.src_id=n.id OR e.dst_id=n.id) AND e.confirm_status!='rejected')
           AND n.source_ref IS NOT NULL""").fetchone()["c"]
    density = round(edges / active, 2) if active else 0.0
    return {"nodes": nodes, "active": active, "edges": edges,
            "link_density": density, "orphan_rate": round(orphan / active, 3) if active else 0.0}
