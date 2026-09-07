"""OpenAI 兼容 API（DeepSeek / Qwen / 任意兼容端点）。"""
import json

import requests

from .base import LLMProvider

ATOMIZE_SYS = (
    "你是知识整理助手。把用户提供的文本拆解为若干条原子笔记。"
    "规则：①一条笔记只表达一个主张；②用用户自己的语言重新组织；③每条 body 不超过 200 字。"
    "只输出 JSON 数组，不要输出其他内容，格式：[{\"type\":\"claim|concept|question\",\"title\":\"简短标题\",\"body\":\"主张内容\"}]"
)
JUDGE_SYS = (
    "你是知识图谱构建助手。判断两个知识节点之间是否存在有意义的关系，并选择唯一最合适的关系类型："
    "implies(蕴含/因果) supports(支持/证据) contradicts(反对/矛盾) exemplifies(实例) "
    "refines(细化/精化) prerequisite_of(前提/先决) contrasts(对比/区分) merges(同义合并) relates(弱关联)。"
    "输出 JSON：{\"rel_type\":\"...\",\"confidence\":0.0-1.0,\"rationale\":\"一句话理由\"}；"
    "若确实无关系输出 null。只输出 JSON。"
)
SYNTH_SYS = (
    "你是知识综合专家。基于以下知识节点，写一篇 300-500 字的综述，提炼共同主题、关键结论与未解决问题。"
    "输出 markdown，开头加一级标题。"
)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, cfg):
        self.base = cfg.llm_base.rstrip("/")
        self.key = cfg.llm_key
        self.model = cfg.llm_model
        self._s = requests.Session()
        self._s.headers.update({"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})

    def _chat(self, system: str, user: str, json_mode: bool = True) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": 2000,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = self._s.post(f"{self.base}/chat/completions", json=body, timeout=60)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"LLM 调用失败: {e}") from e

    def atomize(self, text: str) -> list[dict]:
        try:
            out = self._chat(ATOMIZE_SYS, text)
            data = json.loads(out)
        except Exception:
            from .rule import RuleProvider
            return RuleProvider().atomize(text)
        if isinstance(data, dict):  # 兼容 {"items": [...]}
            data = data.get("items") or data.get("notes") or []
        return [d for d in data if isinstance(d, dict) and d.get("body")][:16]

    def judge_relation(self, a: dict, b: dict) -> dict | None:
        user = (
            f"节点A：\n标题：{a.get('title')}\n内容：{a.get('body')}\n\n"
            f"节点B：\n标题：{b.get('title')}\n内容：{b.get('body')}"
        )
        try:
            out = self._chat(JUDGE_SYS, user)
            data = json.loads(out)
        except Exception:
            from .rule import RuleProvider
            return RuleProvider().judge_relation(a, b)
        if data is None:
            return None
        rel = data.get("rel_type")
        if rel not in ("implies", "supports", "contradicts", "exemplifies", "refines",
                       "prerequisite_of", "contrasts", "merges", "relates"):
            return None
        return {
            "rel_type": rel,
            "confidence": round(float(data.get("confidence", 0.5)), 2),
            "rationale": str(data.get("rationale", ""))[:200],
        }

    def synthesize(self, nodes: list[dict], topic: str) -> str:
        user = f"主题：{topic}\n\n" + "\n".join(
            f"- {n.get('title', '')}：{n.get('body', '')}" for n in nodes)
        try:
            return self._chat(SYNTH_SYS, user, json_mode=False)
        except Exception:
            from .rule import RuleProvider
            return RuleProvider().synthesize(nodes, topic)
