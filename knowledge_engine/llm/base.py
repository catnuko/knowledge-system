"""LLM 提供者接口。默认 rule（无 key 确定性实现），可选 openai 兼容 API。"""
from abc import ABC, abstractmethod

from ..config import Config


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def atomize(self, text: str) -> list[dict]:
        """把一段文本原子化为笔记列表：[{type, title, body}]。"""

    @abstractmethod
    def judge_relation(self, a: dict, b: dict) -> dict | None:
        """判定两个节点间的关系：{rel_type, confidence, rationale} 或 None。"""

    @abstractmethod
    def synthesize(self, nodes: list[dict], topic: str) -> str:
        """基于一组节点生成综述/新主张（markdown 文本）。"""

    def answer(self, question: str, context_nodes: list[dict], contradictions: list[dict] | None = None) -> str:
        """基于召回的节点回答问题。默认实现：返回节点列表（rule 模式降级，不生成答案）。
        context_nodes: [{id, title, body, rel_type?}]
        contradictions: 与召回节点相关的 contradicts 边 [{src_id, dst_id, confidence}]
        返回：答案文本（OpenAI 等实现生成；rule 实现返回节点摘要供前端展示）。
        """
        if not context_nodes:
            return "（无相关节点可回答此问题）"
        lines = ["相关节点："]
        for n in context_nodes:
            lines.append(f"[#{n['id']}] {n.get('title','')}：{n.get('body','')[:80]}")
        if contradictions:
            lines.append("\n存在矛盾：")
            for c in contradictions:
                lines.append(f"  #{c['src_id']} ↔ #{c['dst_id']}（置信 {c.get('confidence',0)}）")
        return "\n".join(lines)

    def feynman(self, node: dict, paraphrase: str) -> dict:
        """Feynman 验证：比较用户复述与节点原文，找出知识 gap。
        返回 {score(0-1), gaps(字符串数组), feedback(总评)}。默认实现：向量相似 + 关键术语召回。
        """
        if not paraphrase:
            return {"score": 0.0, "gaps": ["复述为空"], "feedback": "无复述内容。"}
        from ..embed import cosine, embed
        sim = cosine(embed(paraphrase), embed(node.get("title", "") + " " + node.get("body", "")))
        try:
            import jieba
            body_terms = [t for t in jieba.cut(node.get("body", ""))
                          if len(t) >= 2 and t not in ("的", "了", "是", "在", "和", "与", "或")]
        except ImportError:
            import re
            body_terms = re.findall(r"[\u4e00-\u9fff]{2,}", node.get("body", ""))[:8]
        gaps = [t for t in body_terms[:8] if t not in paraphrase]
        covered = max(1, len(body_terms[:8]))
        score = round(0.5 * sim + 0.5 * (1 - min(1, len(gaps) / covered)), 2)
        fb = f"向量相似 {sim:.2f}；缺失 {len(gaps)} 个关键术语。"
        return {"score": score, "gaps": gaps[:5], "feedback": fb}

    def generate_questions(self, node: dict, n: int = 3) -> list[str]:
        """针对节点生成 N 个检验提问（开放式，主动回忆/生成式提问）。"""
        title = node.get("title", "")
        ntype = node.get("type", "claim")
        if ntype == "question":
            base = [f"请简述对“{title}”的现有理解与困惑。"]
            if n >= 2:
                base.append("该问题的核心定义、可能答案、检验方式分别是什么？")
        elif ntype == "concept":
            base = [f"请用自己的话定义“{title}”。"]
            if n >= 2:
                base.append(f"请举一个“{title}”的例子，并解释理由。")
            if n >= 3:
                base.append(f"对比“{title}”与一个相近概念的区别。")
        else:  # claim
            base = [f"请阐述“{title}”成立的前提与反例。"]
            if n >= 2:
                base.append(f"如果“{node.get('body','')[:60]}”成立，会有什么后续？")
            if n >= 3:
                base.append(f"“{title}”与哪些已学知识冲突或印证？")
        return base[:n]


def get_provider(cfg: Config | None = None) -> LLMProvider:
    cfg = cfg or Config()
    if cfg.llm_provider == "openai" and cfg.llm_key:
        from .openai import OpenAIProvider
        return OpenAIProvider(cfg)
    from .rule import RuleProvider
    return RuleProvider()
