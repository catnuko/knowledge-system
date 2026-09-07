"""采集适配器：音频（ASR）为可选重型依赖，未安装时给出明确提示。"""


def transcribe_audio(path: str) -> str:
    """音频 → 转写文本。需要 funasr 或 faster-whisper（用户机器安装后自动启用）。"""
    try:
        from .audio_local import transcribe  # noqa: F401
        return transcribe(path)
    except ImportError:
        raise RuntimeError(
            "音频转写未启用：需要安装本地 ASR。"
            "推荐：pip install funasr modelscope （中文优化）；或 faster-whisper。"
            "安装后重试。"
        )
