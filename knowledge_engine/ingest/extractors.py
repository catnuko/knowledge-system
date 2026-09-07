"""采集：内容提取器（本地文件 / URL）。音频、手写走独立适配器（接口预留）。"""
from pathlib import Path


def extract_file(path: str) -> tuple[str, str]:
    """从本地文本类文件提取 (title, text)。支持 txt/md。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    return p.stem, text


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
