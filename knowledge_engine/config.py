"""配置：环境变量 > ~/.knowledge_engine/config.json > 默认值。

设置面板通过 PUT /api/settings 写 config.json，运行时生效（无需重启）；
环境变量仍可覆盖配置文件，保持 CLI 工作流兼容。
"""
import json
import os
from pathlib import Path


def _default_db() -> Path:
    env = os.environ.get("KE_DB")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".knowledge_engine" / "ke.db"


# config.json 中允许写入的键（其余忽略，防止任意写入）
SETTING_KEYS = (
    "llm_provider", "llm_base", "llm_key", "llm_model", "embedding",
    "asr_provider", "asr_base", "asr_key", "asr_model",
)

_file_cache: dict = {"path": None, "mtime": None, "data": {}}


def _load_file(path: Path) -> dict:
    """读取 config.json，带 mtime 缓存（设置保存后立即生效）。"""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _file_cache.update(path=None, mtime=None, data={})
        return {}
    if _file_cache["path"] == path and _file_cache["mtime"] == mtime:
        return _file_cache["data"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        data = {k: str(raw[k]) for k in SETTING_KEYS if raw.get(k) is not None and str(raw[k]) != ""}
    except (OSError, ValueError, TypeError):
        data = {}
    _file_cache.update(path=path, mtime=mtime, data=data)
    return data


class Config:
    def __init__(self) -> None:
        self._file = _load_file(self.config_path)

    def _get(self, key: str, env: str, default: str = "") -> str:
        return os.environ.get(env) or self._file.get(key) or default

    @property
    def db_path(self) -> Path:
        """动态解析（支持测试注入 KE_DB）。"""
        return _default_db()

    @property
    def config_path(self) -> Path:
        return self.db_path.parent / "config.json"

    def save(self, updates: dict) -> dict:
        """把更新合并写入 config.json（仅接受 SETTING_KEYS）。返回合并后的完整配置。"""
        clean = {k: str(v).strip() for k, v in updates.items()
                 if k in SETTING_KEYS and v is not None and str(v).strip() != ""}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        try:
            existing = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        existing.update(clean)
        self.config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        self._file = _load_file(self.config_path)  # 强制刷新缓存
        return {k: getattr(self, k) for k in SETTING_KEYS}

    # LLM：rule = 无 key 的规则实现（默认，确定性）；openai = OpenAI 兼容 API（DeepSeek/Qwen 等）
    @property
    def llm_provider(self) -> str:
        return self._get("llm_provider", "KE_LLM", "rule")

    @property
    def llm_base(self) -> str:
        return self._get("llm_base", "KE_LLM_BASE", "https://api.deepseek.com/v1")

    @property
    def llm_key(self) -> str:
        return self._get("llm_key", "KE_LLM_KEY", "")

    @property
    def llm_model(self) -> str:
        return self._get("llm_model", "KE_LLM_MODEL", "deepseek-chat")

    # embedding：light = 内置轻量向量（512 维，确定性，非模型推理）
    @property
    def embedding(self) -> str:
        return self._get("embedding", "KE_EMBEDDING", "light")

    # ASR：音频转写 provider（在线 OpenAI 兼容 /audio/transcriptions）
    @property
    def asr_provider(self) -> str:
        return self._get("asr_provider", "KE_ASR", "none")

    @property
    def asr_base(self) -> str:
        return self._get("asr_base", "KE_ASR_BASE", "")

    @property
    def asr_key(self) -> str:
        return self._get("asr_key", "KE_ASR_KEY", "")

    @property
    def asr_model(self) -> str:
        return self._get("asr_model", "KE_ASR_MODEL", "")

    # 建链门控
    auto_threshold: float = 0.85
    pending_threshold: float = 0.5

    # 孤儿规则
    orphan_hours: int = 48
    orphan_archive_days: int = 30
