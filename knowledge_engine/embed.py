"""Embedding 后端：light（内置确定性）与 bge（本地语义模型）可插拔，统一 512 维。

- light：jieba 分词 + hashing trick + L2 归一化（零依赖、可复现）
- bge：BAAI/bge-small-zh-v1.5 本地推理（KE_EMBEDDING=bge 启用，首次调用自动加载模型）
"""
import hashlib
import math

import jieba

DIM = 512


def embed(text: str) -> list[float]:
    from .config import Config
    if Config().embedding == "bge":
        return _embed_bge(text)
    return _embed_light(text)


def _embed_light(text: str) -> list[float]:
    """jieba 词语 + 字符 bigram 双通道 hashing，L2 归一化。"""
    vec = [0.0] * DIM
    for tok in jieba.cut(text):
        if not tok.strip():
            continue
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
        vec[h % DIM] += 1.0
    s = "".join(text.split())
    for i in range(len(s) - 1):
        h = int(hashlib.md5(s[i:i + 2].encode("utf-8")).hexdigest()[:8], 16)
        vec[h % DIM] += 0.5
    return _normalize(vec)


# ---------- BGE 本地语义模型 ----------

_bge_model = None
_bge_tokenizer = None
_bge_cache: dict[str, list[float]] = {}


def _embed_bge(text: str) -> list[float]:
    global _bge_model, _bge_tokenizer
    hit = _bge_cache.get(text)
    if hit is not None:
        return hit
    if _bge_model is None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        from .config import Config
        cache_dir = str(Config().db_path.parent / "models" / "bge-small-zh")
        _bge_tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-small-zh-v1.5", cache_dir=cache_dir)
        _bge_model = AutoModel.from_pretrained("BAAI/bge-small-zh-v1.5", cache_dir=cache_dir)
        _bge_model.eval()
    import torch
    with torch.no_grad():
        enc = _bge_tokenizer([text], padding=True, truncation=True, max_length=512, return_tensors="pt")
        pooled = _bge_model(**enc).last_hidden_state.mean(1)[0].tolist()
    vec = _normalize(pooled)
    if len(_bge_cache) > 2048:  # 防止无限增长
        _bge_cache.clear()
    _bge_cache[text] = vec
    return vec


# ---------- 工具 ----------

def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    s = sum(x * y for x, y in zip(a, b))
    return max(0.0, min(1.0, s))


def fingerprint(text: str) -> str:
    """去重指纹：归一化文本的 sha1。"""
    norm = "".join(text.split())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()
