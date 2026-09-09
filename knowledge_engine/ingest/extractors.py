"""采集：内容提取器（本地文件 / URL / 图片 OCR）。音频走独立适配器（接口预留）。"""
from pathlib import Path


def extract_file(path: str) -> tuple[str, str]:
    """从本地文本类文件提取 (title, text)。支持 txt/md。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    return p.stem, text


def extract_image(path: str) -> tuple[str, str]:
    """从图片提取 (title, text)。rapidocr-onnxruntime 本地推理，未安装时给出明确提示。
    支持 png/jpg/jpeg/webp/bmp。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        raise RuntimeError(
            "图片 OCR 未启用：需要安装 rapidocr-onnxruntime。"
            "pip install rapidocr-onnxruntime （首次自动下载 ONNX 模型约 10MB）"
        ) from e
    engine = RapidOCR()
    result, _elapsed = engine(str(p))
    lines = [item[1] for item in result] if result else []
    text = "\n".join(lines).strip()
    if not text:
        raise RuntimeError(f"图片无可识别文本: {path}")
    title = (text[:24] + "…") if len(text) > 24 else text
    return title, text


def extract_url(url: str, timeout: int = 20) -> tuple[str, str]:
    """从 URL 提取 (title, text)。trafilatura 优先，失败抛异常。"""
    import trafilatura

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise RuntimeError(f"无法抓取 URL: {url}")
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
    if not text:
        raise RuntimeError(f"URL 无可提取正文: {url}")
    title = _title_of(downloaded, url)
    return title, text


def _title_of(html: str, url: str) -> str:
    import re
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        t = re.sub(r"\s+", " ", m.group(1)).strip()
        if t:
            return t[:120]
    return url[:120]
