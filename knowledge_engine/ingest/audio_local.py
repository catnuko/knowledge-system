"""音频转写：FunASR（paraformer-zh，中文优化，本地推理）。

模型经 ModelScope 下载，缓存于 ~/.knowledge_engine/models/（与 BGE 同一目录）。
首次调用自动下载（约 1GB），之后常驻内存。
"""
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("ke.asr")

_MODEL_NAME = "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
_VAD_MODEL = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
_PUNC_MODEL = "iic/punc_ct-transformer_cn-en-common-vocab471067-large"

_model = None


def _cache_dir() -> str:
    from ..config import Config
    return str(Config().db_path.parent / "models")


def _get_model():
    global _model
    if _model is not None:
        return _model
    from funasr import AutoModel

    t0 = time.time()
    log.info("加载 FunASR 模型（首次需下载，约 1GB）…")
    _model = AutoModel(
        model=_MODEL_NAME,
        vad_model=_VAD_MODEL,
        punc_model=_PUNC_MODEL,
        cache_dir=_cache_dir(),
        disable_update=True,
        device="cpu",
    )
    log.info("FunASR 模型加载完成，耗时 %.1fs", time.time() - t0)
    return _model


def transcribe(path: str) -> str:
    """音频文件 → 中文转写文本。"""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    model = _get_model()
    res = model.generate(input=path, batch_size_s=300)
    if not res or not res[0].get("text"):
        raise RuntimeError(f"音频转写结果为空: {path}")
    return str(res[0]["text"]).strip()
