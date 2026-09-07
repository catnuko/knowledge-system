"""手写/印刷文字识别：PaddleOCR（ch_PP-OCRv5，本地推理）。

首次调用自动下载模型（约 15MB），缓存于默认模型目录。
"""
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("ke.ocr")

_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is not None:
        return _ocr
    from paddleocr import PaddleOCR

    t0 = time.time()
    log.info("加载 PaddleOCR 模型（首次自动下载）…")
    _ocr = PaddleOCR(
        lang="ch",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    log.info("PaddleOCR 模型加载完成，耗时 %.1fs", time.time() - t0)
    return _ocr


def recognize(path: str) -> str:
    """图片文件 → 识别文本（按行拼接）。"""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    ocr = _get_ocr()
    result = ocr.predict(str(Path(path).resolve()))
    texts: list[str] = []
    for page in result:
        if isinstance(page, dict):
            rec = page.get("rec_texts")
            if rec:
                texts.extend(str(t).strip() for t in rec if str(t).strip())
    if not texts:
        raise RuntimeError(f"图片未识别到文字: {path}")
    return "\n".join(texts)
