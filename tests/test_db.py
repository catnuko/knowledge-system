"""存储层测试：CRUD、向量/FTS 检索、子图、统计。"""
import os
import tempfile

os.environ["KE_DB"] = tempfile.mktemp(suffix=".db")

from knowledge_engine import db  # noqa: E402
from knowledge_engine.embed import embed  # noqa: E402


def _con():
    return db.connect()


def test_source_and_node_crud():
    con = _con()
    sid = db.insert_source(con, "clipboard", text_extracted="原文", title="t")
    nid = db.insert_node(con, "claim", "标题A", "正文A", sid)
    assert db.get_node(con, nid)["title"] == "标题A"
    assert db.get_source(con, sid)["kind"] == "clipboard"
    assert db.find_source_by_fingerprint(con, "fp-none") is None
    con.close()


def test_edge_unique_and_crud():
    con = _con()
    a = db.insert_node(con, "claim", "A", "x" * 30, None)
    b = db.insert_node(con, "concept", "B", "y" * 30, None)
    e1 = db.insert_edge(con, a, b, "relates", "r", 0.6, "pending")
    assert e1 is not None
    assert db.insert_edge(con, a, b, "relates", "r", 0.6, "pending") is None  # 唯一约束
    db.set_edge_confirm(con, e1, "approved")
    assert db.list_edges(con, status="approved")[0]["id"] == e1
    db.delete_edge(con, e1)
    assert db.list_edges(con) == []
    con.close()


def test_vector_and_fts_search():
    import pytest
    con = _con()
    if not db._vec_ok(con):
        pytest.skip("本环境无 sqlite_vec 扩展加载能力，跳过向量检索断言")
    db.insert_node(con, "claim", "间隔重复算法", "通过遗忘曲线安排复习，提升记忆保持率。", None)
    db.insert_node(con, "claim", "检索练习", "主动提取信息能巩固长期记忆。", None)
    hits = db.vector_search(con, embed("间隔重复 遗忘曲线"), k=5)
    assert hits, "向量检索应有结果"
    assert hits[0]["rowid"] == 1
    fts = db.fts_search(con, "间隔重复", k=5)
    assert fts and fts[0]["rowid"] == 1
    con.close()


def test_subgraph_and_stats():
    con = _con()
    a = db.insert_node(con, "claim", "A", "x" * 30, None)
    b = db.insert_node(con, "claim", "B", "y" * 30, None)
    c = db.insert_node(con, "claim", "C", "z" * 30, None)
    db.insert_edge(con, a, b, "supports", "s", 0.9, "auto")
    nodes, edges = db.subgraph(con, a, depth=2)
    assert {n["id"] for n in nodes} == {a, b}
    assert len(edges) == 1
    s = db.stats(con)
    assert s["nodes"] == 3 and s["edges"] == 1
    con.close()
