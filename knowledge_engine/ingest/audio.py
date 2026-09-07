"""采集适配器：音频（ASR）与手写（OCR）为可选重型依赖，未安装时给出明确提示。"""


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


def ocr_handwritten(path: str) -> str:
    """手写图片/扫描件 → 文本。需要 paddleocr。"""
    try:
        from .ocr_local import recognize  # noqa: F401
        return recognize(path)
    except ImportError:
        raise RuntimeError(
            "手写识别未启用：需要安装 paddleocr。"
            "推荐：pip install paddleocr paddlepaddle。安装后重试。"
        )
