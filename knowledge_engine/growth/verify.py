"""主动验证：Feynman 复述找 gap + 生成式提问 + 节点掌握度。

主动回忆验证（盲测）由前端纯前端实现：隐藏 body → 用户复述 → 揭示 → 自评 → 调 FSRS。
后端只提供 Feynman 评分与生成提问两个能力。
"""
from .. import db
from ..config import Config
from ..llm.base import get_provider


def feynman(con, nid: int, paraphrase: str, *, provider=None, cfg: Config | None = None) -> dict:
    """Feynman 验证：用户复述 → LLM 找 gap → 落库 → 返回结果。
    返回 {nid, score, gaps, feedback, history:[最近5条]}。
    """
    cfg = cfg or Config()
    provider = provider or get_provider(cfg)
    node = db.get_node(con, nid)
    if node is None:
        raise KeyError(f"节点 {nid} 不存在")
    node_dict = {"id": nid, "type": node["type"], "title": node["title"], "body": node["body"]}
    result = provider.feynman(node_dict, paraphrase)
    score = float(result.get("score", 0))
    gaps = list(result.get("gaps", []))
    feedback = str(result.get("feedback", ""))
    db.insert_verification(con, nid, "feynman", paraphrase, gaps, score, feedback)
    history = [dict(r) for r in db.list_verifications(con, nid, mode="feynman", limit=5)]
    return {"nid": nid, "score": score, "gaps": gaps, "feedback": feedback, "history": history}


def generate_questions(con, nid: int, n: int = 3, *,
                       provider=None, cfg: Config | None = None) -> list[str]:
    """针对节点生成 n 个开放式检验提问。生成式提问留痕（mode=generative）。"""
    cfg = cfg or Config()
    provider = provider or get_provider(cfg)
    node = db.get_node(con, nid)
    if node is None:
        raise KeyError(f"节点 {nid} 不存在")
    node_dict = {"id": nid, "type": node["type"], "title": node["title"], "body": node["body"]}
    qs = provider.generate_questions(node_dict, n)
    # 留痕：记一次生成提问（score=0，paraphrase 空）
    db.insert_verification(con, nid, "generative", "", qs, 0.0, "生成提问")
    return qs


def node_mastery(con, nid: int) -> dict:
    """节点掌握度（封装 db.node_mastery）。"""
    return db.node_mastery(con, nid)


def all_mastery(con) -> dict:
    """知识库总体掌握度（封装 db.all_mastery）。"""
    return db.all_mastery(con)
