"""OpenAI 兼容 API（DeepSeek / Qwen / 任意兼容端点）。"""
import json

import requests

from .base import LLMProvider

LLM_PRESETS = {
    "custom": {"label": "自定义 OpenAI 兼容", "base": "", "model": ""},
    "deepseek": {
        "label": "DeepSeek",
        "base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "siliconflow": {
        "label": "硅基流动 SiliconFlow",
        "base": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
    },
    "dashscope": {
        "label": "阿里云百炼（Qwen）",
        "base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "zhipu": {
        "label": "智谱 GLM",
        "base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
}

ATOMIZE_SYS = (
    "你是知识整理助手。把用户提供的文本拆解为若干条原子笔记。"
    "规则：①一条笔记只表达一个主张；②用用户自己的语言重新组织；③每条 body 不超过 200 字。"
    "只输出 JSON 对象，不要输出其他内容，格式：{\"items\":[{\"type\":\"claim|concept|question\",\"title\":\"简短标题\",\"body\":\"主张内容\"}]}"
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

    def ping(self) -> dict:
        """连通性测试：一次最小 chat 请求。"""
        try:
            self._chat("你是连通性测试助手。", "回复 OK 两个字母即可。", json_mode=False)
            return {"ok": True, "detail": f"{self.model} @ {self.base} 连通正常"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}

    def atomize(self, text: str) -> list[dict]:
        try:
            out = self._chat(ATOMIZE_SYS, text)
            data = json.loads(out)
        except Exception:
            from .rule import RuleProvider
            return RuleProvider().atomize(text)
        if isinstance(data, list):  # 兼容裸数组
            items = data
        elif isinstance(data, dict):  # 兼容 {"items": [...]} / {"notes": [...]}
            items = data.get("items") or data.get("notes") or []
        else:
            items = []
        return [d for d in items if isinstance(d, dict) and d.get("body")][:16]

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

    def answer(self, question: str, context_nodes: list[dict], contradictions: list[dict] | None = None) -> str:
        """GraphRAG 问答：强制引用节点 id 溯源，冲突感知。"""
        context = "\n\n".join(
            f"[#{n['id']}] {n.get('title','')}\n{n.get('body','')}" for n in context_nodes)
        contra = ""
        if contradictions:
            contra = "\n\n矛盾（需在答案中标注）：\n" + "\n".join(
                f"- #{c['src_id']} ↔ #{c['dst_id']}（置信 {c.get('confidence',0)}）" for c in contradictions)
        sys = (
            "你是知识库问答助手。基于以下知识节点回答用户问题。"
            "规则：1) 每个事实陈述后用 [#节点id] 标注来源；"
            "2) 若节点间存在矛盾，明确指出“A 说 X，但 B 说 Y”并标注两侧 id；"
            "3) 不要编造未在节点中出现的信息；4) 答案简洁。"
        )
        user = f"知识节点：\n{context}{contra}\n\n问题：{question}"
        try:
            return self._chat(sys, user, json_mode=False)
        except Exception:
            from .rule import RuleProvider
            return RuleProvider().answer(question, context_nodes, contradictions)

    def feynman(self, node: dict, paraphrase: str) -> dict:
        """Feynman：LLM 比较用户复述 vs 节点原文，输出 {score, gaps, feedback}。"""
        sys = (
            "你是费曼学习法教练。给定一个知识节点原文与用户复述，"
            "评估复述的准确性与完整度。输出 JSON："
            "{\"score\":0.0-1.0(准确度),\"gaps\":[缺失/错误的关键点],\"feedback\":\"一句话总评\"}。"
            "只输出 JSON。"
        )
        user = (f"节点原文：\n标题：{node.get('title','')}\n内容：{node.get('body','')}\n\n"
                f"用户复述：\n{paraphrase}")
        try:
            out = self._chat(sys, user)
            data = json.loads(out)
            return {
                "score": round(float(data.get("score", 0.5)), 2),
                "gaps": [str(g)[:80] for g in (data.get("gaps") or [])][:5],
                "feedback": str(data.get("feedback", ""))[:200],
            }
        except Exception:
            from .rule import RuleProvider
            return RuleProvider().feynman(node, paraphrase)

    def generate_questions(self, node: dict, n: int = 3) -> list[str]:
        """生成 N 个针对节点的检验提问。"""
        sys = (
            "你是教学提问设计专家。针对给定知识节点，生成开放式检验提问，"
            "用于主动回忆与生成式学习。要求：1) 不问是非；2) 引发复述/类比/反例；"
            f"3) 输出 JSON：{{\"items\":[\"问题1\",\"问题2\",...]}}，恰好 {n} 条。只输出 JSON。"
        )
        user = f"节点：\n类型：{node.get('type','claim')}\n标题：{node.get('title','')}\n内容：{node.get('body','')}"
        try:
            out = self._chat(sys, user)
            data = json.loads(out)
            items = data.get("items") if isinstance(data, dict) else data
            return [str(q)[:120] for q in (items or [])][:n]
        except Exception:
            from .rule import RuleProvider
            return RuleProvider().generate_questions(node, n)
