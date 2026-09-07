"""音频转写：FunASR（SenseVoiceSmall，中文优化，本地推理，轻量快速）。

模型经 ModelScope 下载，缓存于 ~/.cache/modelscope/。
首次调用自动下载（约 1GB），之后常驻内存。
"""
import logging
import os
import re
import time

log = logging.getLogger("ke.asr")

_MODEL_NAME = "iic/SenseVoiceSmall"

_model = None


def _get_model():
    global _model
    if _model is not None:
        return _model
    from funasr import AutoModel

    t0 = time.time()
    log.info("加载 FunASR SenseVoice 模型（首次需下载，约 1GB）…")
    _model = AutoModel(
        model=_MODEL_NAME,
        disable_update=True,
        device="cpu",
        trust_remote_code=False,
    )
    log.info("FunASR 模型加载完成，耗时 %.1fs", time.time() - t0)
    return _model


# SenseVoice 输出的富文本标签，如 <|zh|><|NEUTRAL|><|Speech|><|woitn|>
_TAG_RE = re.compile(r"<\|[^|]+\|>")


def transcribe(path: str) -> str:
    """音频文件 → 中文转写文本（剥离 SenseVoice 标签）。"""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    model = _get_model()
    res = model.generate(input=path, cache={}, language="auto", use_itn=True)
    if not res or not res[0].get("text"):
        raise RuntimeError(f"音频转写结果为空: {path}")
    raw = str(res[0]["text"])
    text = _TAG_RE.sub("", raw).strip()
    if not text:
        raise RuntimeError(f"音频转写结果为空（标签剥离后）: {path}")
    return text
