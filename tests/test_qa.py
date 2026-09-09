"""对话问答（GraphRAG）测试：召回、图扩展、冲突感知、rule 模式降级。"""
import os
import tempfile

os.environ["KE_DB"] = tempfile.mktemp(suffix=".db")

from knowledge_engine import db  # noqa: E402
from knowledge_engine.config import Config  # noqa: E402
from knowledge_engine.growth.qa import ask  # noqa: E402
from knowledge_engine.ingest.pipeline import ingest_text  # noqa: E402


def test_ask_recall_and_answer():
    """rule 模式：召回节点 + 生成答案（节点列表降级）。"""
    con = db.connect()
    ingest_text(con, "FSRS 通过稳定性和难度系数计算下次复习间隔，目标保持率 90%。", kind="clipboard", title="fsrs")
    ingest_text(con, "艾宾浩斯遗忘曲线描述记忆随时间衰减，间隔复习可抵消遗忘。", kind="clipboard", title="ebbinghaus")
    cfg = Config()  # rule 模式
    r = ask(con, "FSRS 怎么决定复习间隔？", provider=None, cfg=cfg)
    assert r["question"] == "FSRS 怎么决定复习间隔？"
    assert r["answer"]  # rule 模式也返回节点列表
    assert isinstance(r["cited_nodes"], list)
    # 召回至少命中 fsrs 节点
    assert any("FSRS" in (n.get("title", "") + n.get("body", "")).upper()
               or "稳定" in n.get("body", "") for n in r["cited_nodes"])
    con.close()


def test_ask_empty_kb():
    """空库提问：返回无相关节点。"""
    con = db.connect()
    cfg = Config()
    r = ask(con, "某个根本不存在的话题 zzzxxx", cfg=cfg)
    assert "无相关节点" in r["answer"] or not r["cited_nodes"]
    con.close()


def test_ask_conflict_awareness():
    """存在 contradicts 边时，问答结果应携带矛盾。"""
    con = db.connect()
    a = db.insert_node(con, "claim", "主张 A", "维生素 C 能治愈感冒。", None)
    b = db.insert_node(con, "claim", "主张 B", "维生素 C 对感冒无显著疗效。", None)
    eid = db.insert_edge(con, a, b, "contradicts", "临床试验矛盾", 0.8, "approved")
    assert eid, "边应插入成功"
    cfg = Config()
    r = ask(con, "维生素 C 感冒", cfg=cfg)
    # 命中矛盾节点时 contradictions 非空
    if {n["id"] for n in r["cited_nodes"]} & {a, b}:
        assert r["contradictions"], "应当召回 contradicts 边"
        c = r["contradictions"][0]
        assert c["src_id"] == a and c["dst_id"] == b
    con.close()
