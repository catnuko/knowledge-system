"""规则实现：无 API key 时的确定性降级。保证 MVP 可闭环，后续可无缝切换 LLM/BGE。

科学口径：规则模式只做「显式术语关联」检测（Zettelkasten 的显式链接思想），
不做隐式语义推断；隐式关联由 LLM 或语义模型负责。保守门控 + 建议箱。
"""
import re

import jieba

from ..embed import cosine, embed
from .base import LLMProvider

MIN_BODY = 20
MAX_BODY = 600
STOPWORDS = {
    "的", "了", "是", "在", "与", "和", "及", "或", "等", "有", "对", "把", "被", "从",
    "为", "以", "于", "就", "都", "而", "所", "中", "上", "下", "一个", "一种",
    "通过", "可以", "进行", "以及", "并且", "这个", "那个", "我们", "你们", "他们",
    "之", "其", "也", "不", "很", "更", "最", "但", "却", "如果", "因为", "所以", "因此",
}


class RuleProvider(LLMProvider):
    name = "rule"

    def atomize(self, text: str) -> list[dict]:
        items = []
        for para in re.split(r"\n\s*\n|(?<=[。！？!?])\s*\n", text):
            para = re.sub(r"\s+", " ", para).strip()
            if len(para) < MIN_BODY:
                continue
            if len(para) > MAX_BODY:
                para = para[:MAX_BODY]
            title = (para[:24] + "…") if len(para) > 24 else para
            items.append({"type": "claim", "title": title, "body": para})
        return items[:16]

    def judge_relation(self, a: dict, b: dict) -> dict | None:
        at = (a.get("title", "") + " " + a.get("body", "")).strip()
        bt = (b.get("title", "") + " " + b.get("body", "")).strip()
        vec_sim = cosine(embed(at), embed(bt))
        shared = _shared_terms(at, bt)
        title_hit = (a.get("title", "")[:6] and a["title"][:6] in bt) or \
                    (b.get("title", "")[:6] and b["title"][:6] in at)

        # 显式术语关联：共享 ≥1 个概念词，或向量强重叠
        if len(shared) == 0 and vec_sim < 0.32 and not title_hit:
            return None

        if title_hit:
            rel, conf = "refines", round(min(0.92, 0.6 + vec_sim), 2)
        elif len(shared) >= 2 and vec_sim >= 0.35:
            rel, conf = "refines", round(min(0.88, 0.55 + vec_sim), 2)
        elif len(shared) >= 1 or vec_sim >= 0.5:
            # 弱关联 → 必须人工确认（建议箱）
            rel, conf = "relates", round(min(0.68, max(0.5, vec_sim + 0.08 * len(shared))), 2)
        else:
            rel, conf = "relates", round(vec_sim, 2)

        rationale = (f"共享术语[{','.join(sorted(shared)[:5])}] " if shared else "语义向量 ")
        rationale += f"相似度 {vec_sim:.2f}" + ("；标题互含" if title_hit else "")
        return {"rel_type": rel, "confidence": conf, "rationale": rationale[:200]}

    def synthesize(self, nodes: list[dict], topic: str) -> str:
        lines = [f"# {topic}（自动综合）", ""]
        for n in nodes:
            lines.append(f"- **{n.get('title', '')}**：{n.get('body', '')}")
        lines.append("")
        lines.append("> 由 knowledge-engine 规则模式生成：汇总当前社区节点，供人工精炼。")
        return "\n".join(lines)


def _shared_terms(at: str, bt: str) -> set[str]:
    a = {t for t in jieba.cut(at) if len(t) >= 2 and t not in STOPWORDS}
    b = {t for t in jieba.cut(bt) if len(t) >= 2 and t not in STOPWORDS}
    return a & b
