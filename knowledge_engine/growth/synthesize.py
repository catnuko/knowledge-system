"""每周综合：连通分量 + 综述 → 新节点挂回图（GraphRAG 思路的轻量实现）。"""
from .. import db


def _components(con, node_ids: list[int]) -> list[list[int]]:
    """并查集求连通分量。"""
    parent = {n: n for n in node_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for e in db.list_edges(con, limit=100000):
        if e["src_id"] in parent and e["dst_id"] in parent:
            union(e["src_id"], e["dst_id"])
    comps: dict[int, list[int]] = {}
    for n in node_ids:
        comps.setdefault(find(n), []).append(n)
    return list(comps.values())


def weekly_synthesis(con, provider, limit_components: int = 1, max_nodes: int = 20) -> dict:
    """选取最大连通分量 → 生成综述 → 新节点（source=synthesis）挂回图。"""
    active = [r["id"] for r in con.execute(
        "SELECT id FROM nodes WHERE status='active' AND type != 'question'").fetchall()]
    if not active:
        return {"synthesized": 0, "node_id": None, "topic": "", "size": 0}
    comps = sorted(_components(con, active), key=len, reverse=True)
    results = []
    for comp in comps[:limit_components]:
        comp = comp[:max_nodes]
        if len(comp) < 2:
            continue
        rows = [db.get_node(con, n) for n in comp]
        rows = [r for r in rows if r]
        # 主题：分量内边数最多的节点标题
        topic = _topic_of(con, rows)
        nodes_for_llm = [{"title": r["title"], "body": r["body"], "type": r["type"]} for r in rows]
        summary = provider.synthesize(nodes_for_llm, topic)
        sid = db.insert_source(con, "synthesis", text_extracted=summary, title=f"综合：{topic}", fingerprint="")
        nid = db.insert_node(con, "claim", f"综合：{topic}", summary[:800], sid)
        # 挂回图：与分量内代表节点建立 refines 边（自动）
        rep = rows[0]
        db.insert_edge(con, nid, rep["id"], "refines", f"综合产物，基于 {len(rows)} 个节点", 0.9, "auto")
        results.append({"node_id": nid, "topic": topic, "size": len(rows)})
    return {"synthesized": len(results), "items": results}


def _topic_of(con, rows: list) -> str:
    """选择分量中连接最多的节点标题作为主题。"""
    ids = [r["id"] for r in rows]
    ph = ",".join("?" * len(ids))
    degree = {i: 0 for i in ids}
    for e in con.execute(
            f"SELECT src_id, dst_id FROM edges WHERE src_id IN ({ph}) AND dst_id IN ({ph}) "
            "AND confirm_status != 'rejected'", ids + ids):
        degree[e["src_id"]] = degree.get(e["src_id"], 0) + 1
        degree[e["dst_id"]] = degree.get(e["dst_id"], 0) + 1
    if not degree:
        return rows[0]["title"]
    top = max(degree, key=degree.get)
    return next((r["title"] for r in rows if r["id"] == top), rows[0]["title"])[:60]
