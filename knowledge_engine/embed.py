"""Embedding：jieba 分词 + hashing trick + L2 归一化（512 维，确定性，零模型零推理）。

本地语义模型（BGE）已随本地推理一起移除；light 为唯一后端，512 维保持不变。
"""
import hashlib
import math

import jieba

DIM = 512


def embed(text: str) -> list[float]:
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
