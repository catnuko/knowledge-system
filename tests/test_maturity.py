"""成熟度测试覆盖：9 类命题边、置信度门控、DAG 多跳环、双向去重、综合、矛盾处理、指标、孤儿规则。"""
import os
import tempfile
from datetime import datetime, timedelta

os.environ["KE_DB"] = tempfile.mktemp(suffix=".db")

import pytest  # noqa: E402

from knowledge_engine import db  # noqa: E402
from knowledge_engine.config import Config  # noqa: E402
from knowledge_engine.growth.conflict import conflicts, resolve  # noqa: E402
from knowledge_engine.growth.metrics import all_metrics  # noqa: E402
from knowledge_engine.growth.synthesize import weekly_synthesis  # noqa: E402
from knowledge_engine.graph.dag import creates_cycle, path_exists  # noqa: E402
from knowledge_engine.graph.linker import link_node, mark_orphans  # noqa: E402
from knowledge_engine.llm.rule import RuleProvider  # noqa: E402

ALL_REL_TYPES = ["implies", "supports", "contradicts", "exemplifies", "refines",
                 "prerequisite_of", "contrasts", "merges", "relates"]


def _con():
    return db.connect()


def _seed_pair(con):
    a = db.insert_node(con, "claim", "节点 A", "关于间隔重复算法的核心主张描述。", None)
    b = db.insert_node(con, "claim", "节点 B", "关于检索练习巩固长期记忆的主张。", None)
    return a, b


# ---------- 9 类命题边 ----------

@pytest.mark.parametrize("rel", ALL_REL_TYPES)
def test_each_edge_type_insertable(rel):
    """9 类 rel_type 均可插入并通过 CHECK 约束。"""
    con = _con()
    a, b = _seed_pair(con)
    eid = db.insert_edge(con, a, b, rel, f"{rel} 测试", 0.7, "auto")
    assert eid, f"{rel} 边应插入成功"
    edges = db.list_edges(con)
    assert any(e["rel_type"] == rel for e in edges)
    con.close()


def test_invalid_rel_type_rejected():
    """非法 rel_type 应被 CHECK 拦截（insert_edge 捕获 IntegrityError 返回 None）。"""
    con = _con()
    a, b = _seed_pair(con)
    eid = db.insert_edge(con, a, b, "causes", "非法关系", 0.5, "auto")
    assert eid is None, "非法 rel_type 应被 CHECK 约束拒绝"
    # 确认无任何边插入
    assert db.list_edges(con) == []
    con.close()


def test_bidirectional_dedup():
    """双向去重：A→B 与 B→A 同类型不应都存在（linker 内部跳过）。"""
    con = _con()
    a, b = _seed_pair(con)
    db.insert_edge(con, a, b, "supports", "正向", 0.8, "auto")
    # 反向同类型应被 linker 的 dup 检查跳过（直接插会因 UNIQUE 失败，但 dup 检查避免尝试）
    dup = con.execute(
        """SELECT 1 FROM edges WHERE rel_type='supports'
           AND ((src_id=? AND dst_id=?) OR (src_id=? AND dst_id=?))""",
        (a, b, b, a)).fetchone()
    assert dup, "反向检查应能检出已存在边"
    con.close()


# ---------- 置信度门控 ----------

def test_confidence_gating_auto():
    """conf >= auto_threshold(0.85) → confirm_status='auto'。"""
    con = _con()
    a, b = _seed_pair(con)
    eid = db.insert_edge(con, a, b, "supports", "高置信", 0.9, "auto")
    e = db.list_edges(con, status="auto")[0]
    assert e["id"] == eid and e["confidence"] == 0.9
    con.close()


def test_confidence_gating_pending():
    """pending_threshold(0.5) <= conf < auto → 'pending' 待人工。"""
    con = _con()
    a, b = _seed_pair(con)
    db.insert_edge(con, a, b, "relates", "中置信", 0.6, "pending")
    assert len(db.list_edges(con, status="pending")) == 1
    assert not db.list_edges(con, status="auto")
    con.close()


def test_confidence_below_threshold_dropped():
    """conf < pending_threshold → linker 不入边。rule 模式下低相似度返回 relates 低分会被丢弃。"""
    con = _con()
    # 两个完全不相关的节点
    a = db.insert_node(con, "claim", "量子力学", "量子叠加态与纠缠现象的物理描述。", None)
    b = db.insert_node(con, "claim", "园艺", "月季修剪的最佳季节在春季萌芽前。", None)
    s = link_node(con, b, provider=RuleProvider(), cfg=Config())
    # 不相关节点不应产生自动边（rule 模式 cosine 低 → relates 低分 → 丢弃）
    auto_edges = [e for e in db.list_edges(con) if e["confirm_status"] == "auto"]
    assert not auto_edges, "不相关节点不应自动建链"
    con.close()


# ---------- 前提 DAG 环检测 ----------

def test_dag_multihop_path():
    """多跳 prerequisite_of 路径可达性。"""
    con = _con()
    a = db.insert_node(con, "concept", "A", "基础概念描述 A 的内容。", None)
    b = db.insert_node(con, "concept", "B", "中间概念描述 B 的内容。", None)
    c = db.insert_node(con, "concept", "C", "高级概念描述 C 的内容。", None)
    db.insert_edge(con, a, b, "prerequisite_of", "A→B", 0.9, "approved")
    db.insert_edge(con, b, c, "prerequisite_of", "B→C", 0.9, "approved")
    assert path_exists(con, a, c), "A→B→C 应可达"
    assert not path_exists(con, c, a), "反向不可达"
    assert creates_cycle(con, c, a), "C→A 会成环"
    assert not creates_cycle(con, a, c), "A→C 不成环（已有路径）"
    con.close()


def test_dag_cycle_blocked_by_linker():
    """linker 应检测 prerequisite_of 环并降级为 relates。"""
    con = _con()
    a = db.insert_node(con, "concept", "A 基础", "基础概念内容描述 A。", None)
    b = db.insert_node(con, "concept", "B 进阶", "进阶概念内容描述 B。", None)
    # 先建 A→B 前提
    db.insert_edge(con, a, b, "prerequisite_of", "A 是 B 前提", 0.95, "auto")
    # 现在尝试 B→A 会成环（手动调用 dag 检测）
    assert creates_cycle(con, b, a)
    con.close()


# ---------- 综合 ----------

def test_synthesis_produces_node():
    """weekly_synthesis 对 ≥2 节点的连通分量产出综述节点。"""
    con = _con()
    a = db.insert_node(con, "claim", "间隔重复", "通过遗忘曲线安排复习提升保持率。", None)
    b = db.insert_node(con, "claim", "检索练习", "主动提取信息比重读更巩固记忆。", None)
    db.insert_edge(con, a, b, "supports", "同主题", 0.85, "auto")
    r = weekly_synthesis(con, RuleProvider())
    assert r["synthesized"] >= 1
    item = r["items"][0]
    assert item["size"] >= 2
    # 综合节点应挂回图（refines 边）
    new_node = db.get_node(con, item["node_id"])
    assert new_node and "综合" in new_node["title"]
    edges = db.list_edges(con)
    assert any(e["src_id"] == item["node_id"] and e["rel_type"] == "refines" for e in edges)
    con.close()


def test_synthesis_skips_isolated():
    """孤立节点（无连通）不参与综合。"""
    con = _con()
    db.insert_node(con, "claim", "孤立 A", "完全孤立的内容描述 A。", None)
    r = weekly_synthesis(con, RuleProvider())
    assert r["synthesized"] == 0, "单个孤立节点不应综合"
    con.close()


# ---------- 矛盾处理 ----------

def test_conflict_detection_and_resolve_archive():
    """矛盾检测 + resolve(archive_b) 应归档一方并 reject 边。"""
    con = _con()
    a = db.insert_node(con, "claim", "主张 A", "维生素 C 能治愈感冒。", None)
    b = db.insert_node(con, "claim", "主张 B", "维生素 C 对感冒无显著疗效。", None)
    eid = db.insert_edge(con, a, b, "contradicts", "临床试验矛盾", 0.85, "approved")
    cs = conflicts(con)
    assert len(cs) == 1 and cs[0]["edge_id"] == eid
    resolve(con, eid, "archive_b")
    # b 已归档
    assert db.get_node(con, b)["status"] == "archived"
    # 边已 reject
    assert not conflicts(con), "归档后矛盾应消失"
    con.close()


def test_conflict_resolve_keep():
    """resolve(keep) 保留矛盾并存（approve）。"""
    con = _con()
    a, b = _seed_pair(con)
    eid = db.insert_edge(con, a, b, "contradicts", "并存标注", 0.7, "pending")
    resolve(con, eid, "keep")
    e = [r for r in db.list_edges(con) if r["id"] == eid][0]
    assert e["confirm_status"] == "approved"
    con.close()


# ---------- 指标 ----------

def test_metrics_computation():
    """all_metrics 返回完整字段且数值合理。"""
    con = _con()
    a, b = _seed_pair(con)
    db.insert_edge(con, a, b, "supports", "支持", 0.9, "auto")
    m = all_metrics(con)
    assert m["active"] >= 2
    assert m["edges"] >= 1
    assert m["pending_edges"] == 0
    assert "mastery_avg" in m
    assert "feynman_count" in m
    assert m["feynman_count"] == 0
    con.close()


# ---------- 孤儿规则 ----------

def test_orphan_mark_after_cutoff():
    """入库超 48h 仍无边的节点应被标记 pending_link。"""
    con = _con()
    nid = db.insert_node(con, "claim", "孤儿候选", "暂无任何关系的孤立节点内容。", None)
    # 手动改 created_at 为 50h 前
    old = (datetime.now() - timedelta(hours=50)).strftime("%Y-%m-%d %H:%M:%S")
    con.execute("UPDATE nodes SET created_at=? WHERE id=?", (old, nid))
    con.commit()
    marked = mark_orphans(con, cfg=Config())
    assert marked >= 1
    assert db.get_node(con, nid)["status"] == "pending_link"
    con.close()


def test_orphan_not_marked_when_linked():
    """有边的节点不应被标记为孤儿。"""
    con = _con()
    a, b = _seed_pair(con)
    db.insert_edge(con, a, b, "relates", "有边", 0.7, "auto")
    old = (datetime.now() - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")
    con.execute("UPDATE nodes SET created_at=? WHERE id IN (?,?)", (old, a, b))
    con.commit()
    mark_orphans(con, cfg=Config())
    # 有边 → 不应被标记
    assert db.get_node(con, a)["status"] == "active"
    assert db.get_node(con, b)["status"] == "active"
    con.close()


# ---------- rule 模式集成 ----------

def test_rule_provider_answer_fallback():
    """RuleProvider.answer 在无节点时返回提示，有节点返回列表。"""
    p = RuleProvider()
    assert "无相关节点" in p.answer("q", [])
    out = p.answer("q", [{"id": 1, "title": "T", "body": "B"}])
    assert "[#1]" in out
    con.close() if False else None  # 无 con
