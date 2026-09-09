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


def get_provider(cfg: Config | None = None) -> LLMProvider:
    cfg = cfg or Config()
    if cfg.llm_provider == "openai" and cfg.llm_key:
        from .openai import OpenAIProvider
        return OpenAIProvider(cfg)
    from .rule import RuleProvider
    return RuleProvider()
