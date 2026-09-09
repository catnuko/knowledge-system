"""GraphRAG 问答：召回 → 沿边扩展子图 → 冲突感知 → provider.answer。

召回策略与 linker 一致：向量 Top-K ∪ FTS Top-K，向量不可用时退化为 FTS+全量余弦。
扩展：对召回的每个节点，沿 1-2 跳边补充相邻节点进 context。
"""
from .. import db
from ..config import Config
from ..embed import embed
from ..llm.base import get_provider


def ask(con, question: str, *, top_k: int = 8, hop: int = 1,
        provider=None, cfg: Config | None = None) -> dict:
    """对知识库提问。返回 {question, answer, cited_nodes, contradictions}。

    - answer: provider 生成的答案（rule 模式降级为节点列表）
    - cited_nodes: 召回+扩展的节点 [{id, title, body, rel_type?}]
    - contradictions: 与召回节点相关的 contradicts 边
    """
    cfg = cfg or Config()
    provider = provider or get_provider(cfg)

    q_vec = embed(question)
    candidates: set[int] = set()

    # 召回：向量 Top-K
    vec_hits = db.vector_search(con, q_vec, k=top_k)
    for r in vec_hits:
        candidates.add(r["rowid"])

    # FTS 补充（问题分词）
    fts_query = _fts_query(question)
    if fts_query:
        k = top_k if vec_hits else top_k * 3  # 无向量时放宽
        for r in db.fts_search(con, fts_query, k=k):
            candidates.add(r["rowid"])

    # 无向量索引：全量余弦兜底
    if not vec_hits:
        candidates.update(_brute_cosine(con, q_vec, k=top_k))

    if not candidates:
        return {"question": question, "answer": "（知识库中无相关节点）",
                "cited_nodes": [], "contradictions": []}

    # 图扩展：对每个召回节点沿 1 跳边补相邻节点
    cited_ids = set(candidates)
    if hop > 0:
        for nid in list(candidates):
            for r in db.neighbors(con, nid, hop):
                cited_ids.add(r["id"])

    # 加载节点详情
    cited_nodes = []
    for nid in sorted(cited_ids):
        node = db.get_node(con, nid)
        if node is None or node["status"] == "archived":
            continue
        cited_nodes.append({"id": nid, "title": node["title"], "body": node["body"]})
        if len(cited_nodes) >= top_k * 2:  # 限制 context 长度
            break

    # 冲突感知：召回的节点对里若有 contradicts 边
    cited_id_list = [n["id"] for n in cited_nodes]
    contradictions = []
    if cited_id_list:
        ph = ",".join("?" * len(cited_id_list))
        rows = con.execute(
            f"""SELECT src_id, dst_id, confidence FROM edges
                WHERE rel_type='contradicts' AND confirm_status!='rejected'
                AND src_id IN ({ph}) AND dst_id IN ({ph})""",
            cited_id_list + cited_id_list,
        ).fetchall()
        contradictions = [dict(r) for r in rows]

    answer = provider.answer(question, cited_nodes, contradictions)
    return {"question": question, "answer": answer,
            "cited_nodes": cited_nodes, "contradictions": contradictions}


def _fts_query(text: str) -> str:
    """简单 FTS 查询：取前若干名词词根，空格连接（FTS5 默认 AND）。"""
    import re
    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", text)
    # 中文按 2 字滑窗切分（FTS5 jieba 分词后），这里直接交给 jieba
    try:
        import jieba
        toks = [t for t in jieba.cut(text) if len(t) > 1][:8]
        return " ".join(toks) if toks else " ".join(tokens[:6])
    except ImportError:
        return " ".join(tokens[:6])


def _brute_cosine(con, q_vec: list[float], k: int = 20) -> list[int]:
    """无向量索引时的全量余弦召回。"""
    from ..embed import cosine
    rows = con.execute(
        "SELECT id, title, body FROM nodes WHERE status IN ('active','pending_link')").fetchall()
    scored = []
    for r in rows:
        try:
            v = embed(r["title"] + " " + r["body"])
            score = cosine(v, q_vec)
            if score > 0:
                scored.append((score, r["id"]))
        except Exception:
            continue
    scored.sort(reverse=True)
    return [nid for _, nid in scored[:k]]
