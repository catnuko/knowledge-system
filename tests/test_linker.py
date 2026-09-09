"""建链引擎测试：召回判定、双向去重、孤儿标记、前提环检测。"""
import os
import tempfile

os.environ["KE_DB"] = tempfile.mktemp(suffix=".db")

from knowledge_engine import db  # noqa: E402
from knowledge_engine.graph.dag import creates_cycle, path_exists  # noqa: E402
from knowledge_engine.graph.linker import link_all_pending, link_node, mark_orphans  # noqa: E402


def test_link_and_dedup():
    con = db.connect()
    a = db.insert_node(con, "claim", "间隔重复算法", "通过遗忘曲线安排复习时间点，提升长期记忆保持率。", None)
    b = db.insert_node(con, "claim", "检索练习", "主动从记忆中提取信息，比重读更能巩固长期记忆。", None)
    s1 = link_node(con, a)
    s2 = link_node(con, b)
    total = s1["linked"] + s1["pending"] + s2["linked"] + s2["pending"]
    assert total >= 1  # 至少一条候选边
    edges = db.list_edges(con)
    # 无双向重复
    pairs = {(e["src_id"], e["dst_id"]) for e in edges}
    rev = {(e["dst_id"], e["src_id"]) for e in edges}
    assert not (pairs & rev)
    con.close()


def test_orphan_mark():
    con = db.connect()
    nid = db.insert_node(con, "claim", "孤立节点", "没有任何关系的新知识点内容。", None)
    o = mark_orphans(con)
    assert o >= 0
    node = db.get_node(con, nid)
    assert node["status"] in ("active", "pending_link")  # 未超 48h 不标记
    con.close()


def test_prerequisite_cycle():
    con = db.connect()
    a = db.insert_node(con, "concept", "A 概念", "前提 A 的内容描述", None)
    b = db.insert_node(con, "concept", "B 概念", "前提 B 的内容描述", None)
    db.insert_edge(con, a, b, "prerequisite_of", "A 是 B 的前提", 0.9, "auto")
    assert path_exists(con, a, b)
    assert creates_cycle(con, b, a)  # 再加 b→a 会成环
    assert not creates_cycle(con, a, b)
    con.close()
