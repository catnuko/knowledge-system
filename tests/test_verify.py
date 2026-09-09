"""主动验证测试：Feynman gap 检测、生成提问、掌握度指标。"""
import os
import tempfile

os.environ["KE_DB"] = tempfile.mktemp(suffix=".db")

from knowledge_engine import db  # noqa: E402
from knowledge_engine.config import Config  # noqa: E402
from knowledge_engine.growth.verify import (  # noqa: E402
    all_mastery, feynman, generate_questions, node_mastery,
)


def test_feynman_scoring_and_persistence():
    """Feynman：复述 → 评分 → 落库 → 历史可查。"""
    con = db.connect()
    nid = db.insert_node(con, "claim", "FSRS 原理",
                         "FSRS 通过稳定性和难度系数计算下次复习间隔，目标保持率 90%。", None)
    r = feynman(con, nid, "FSRS 用稳定度算下次复习时间，目标保持九成。", cfg=Config())
    assert 0 <= r["score"] <= 1
    assert isinstance(r["gaps"], list)
    assert r["nid"] == nid
    # 历史留痕
    assert len(r["history"]) >= 1
    assert r["history"][0]["mode"] == "feynman"
    # 二次提交应累积
    r2 = feynman(con, nid, "另一种复述内容。", cfg=Config())
    assert len(r2["history"]) >= 2
    con.close()


def test_feynman_empty_paraphrase():
    """空复述应返回 0 分 + gap 提示，不抛错。"""
    con = db.connect()
    nid = db.insert_node(con, "concept", "测试概念", "概念定义内容较长一些用于测试。", None)
    r = feynman(con, nid, "", cfg=Config())
    assert r["score"] == 0.0
    assert r["gaps"]  # 非空
    con.close()


def test_generate_questions():
    """生成提问：按节点类型返回 N 条。"""
    con = db.connect()
    nid = db.insert_node(con, "claim", "主张 X", "某条具体可检验的主张内容。", None)
    qs = generate_questions(con, nid, 3, cfg=Config())
    assert len(qs) == 3
    assert all(isinstance(q, str) and q for q in qs)
    # 留痕（generative）
    hist = db.list_verifications(con, nid, mode="generative")
    assert len(hist) >= 1
    con.close()


def test_node_mastery_no_feynman():
    """无 Feynman 验证时，掌握度纯靠 FSRS（应为 0 或低分）。"""
    con = db.connect()
    nid = db.insert_node(con, "claim", "未验证节点", "尚未做任何 Feynman 验证的内容。", None)
    m = node_mastery(con, nid)
    assert m["feynman_count"] == 0
    assert m["feynman_score"] == 0.0
    assert m["score"] == m["fsrs_score"]  # 无 feynman 时退化为 fsrs
    con.close()


def test_node_mastery_with_feynman():
    """有 Feynman 验证后，掌握度应融合 fsrs + feynman。"""
    con = db.connect()
    nid = db.insert_node(con, "claim", "FSRS", "FSRS 算复习间隔的算法描述。", None)
    feynman(con, nid, "FSRS 算复习间隔。", cfg=Config())
    m = node_mastery(con, nid)
    assert m["feynman_count"] >= 1
    assert m["feynman_score"] > 0
    # 融合后 score 应在 fsrs 与 feynman 之间
    assert min(m["fsrs_score"], m["feynman_score"]) - 0.01 <= m["score"] <= max(m["fsrs_score"], m["feynman_score"]) + 0.01
    con.close()


def test_all_mastery_aggregation():
    """总体掌握度聚合：avg/verified/buckets。"""
    con = db.connect()
    a = db.insert_node(con, "claim", "A", "节点 A 内容描述。", None)
    b = db.insert_node(con, "claim", "B", "节点 B 内容描述。", None)
    feynman(con, a, "A 的复述。", cfg=Config())
    m = all_mastery(con)
    assert m["total"] >= 2
    assert m["verified"] >= 1
    assert sum(m["buckets"].values()) == m["total"]
    assert 0 <= m["avg"] <= 1
    con.close()
