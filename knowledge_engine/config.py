"""配置：全部通过环境变量覆盖，默认本地优先。"""
import os
from pathlib import Path


def _default_db() -> Path:
    env = os.environ.get("KE_DB")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".knowledge_engine" / "ke.db"


class Config:
    @property
    def db_path(self) -> Path:
        """动态解析（支持测试注入 KE_DB）。"""
        return _default_db()

    # LLM：rule = 无 key 的规则实现（默认，确定性）；openai = OpenAI 兼容 API（DeepSeek/Qwen 等）
    @property
    def llm_provider(self) -> str:
        return os.environ.get("KE_LLM", "rule")

    @property
    def llm_base(self) -> str:
        return os.environ.get("KE_LLM_BASE", "https://api.deepseek.com/v1")

    @property
    def llm_key(self) -> str:
        return os.environ.get("KE_LLM_KEY", "")

    @property
    def llm_model(self) -> str:
        return os.environ.get("KE_LLM_MODEL", "deepseek-chat")

    # embedding：light = 内置轻量向量（512 维，确定性）；bge = BGE-small-zh 本地语义模型（推荐）
    @property
    def embedding(self) -> str:
        return os.environ.get("KE_EMBEDDING", "light")

    # 建链门控
    auto_threshold: float = 0.85
    pending_threshold: float = 0.5

    # 孤儿规则
    orphan_hours: int = 48
    orphan_archive_days: int = 30
