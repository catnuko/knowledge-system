"""音频转写（ASR）：全部走在线 provider（OpenAI 兼容 /audio/transcriptions 协议）。

预设 provider（设置面板/CLI 只需填 API key）：
- siliconflow：硅基流动，SenseVoice-small
- dashscope：阿里云百炼，qwen3-asr-flash
- zhipu：智谱开放平台，glm-asr
- custom：自定义 OpenAI 兼容端点（自填 base/model）

不再支持本地推理（FunASR 已移除，见 v0.4 变更）。
"""
import logging
from pathlib import Path

import requests

from ..config import Config

log = logging.getLogger("ke.asr")

ASR_PRESETS = {
    "none": {"label": "未启用", "base": "", "model": ""},
    "siliconflow": {
        "label": "硅基流动 SiliconFlow",
        "base": "https://api.siliconflow.cn/v1",
        "model": "FunAudioLLM/SenseVoiceSmall",
    },
    "dashscope": {
        "label": "阿里云百炼（Qwen-ASR）",
        "base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3-asr-flash",
    },
    "zhipu": {
        "label": "智谱 GLM-ASR",
        "base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-asr",
    },
    "custom": {"label": "自定义 OpenAI 兼容", "base": "", "model": ""},
}


def resolve_asr(cfg: Config) -> dict:
    """根据配置解析出 {base, key, model}。provider=none 或缺配置时返回空 base。"""
    provider = cfg.asr_provider
    preset = ASR_PRESETS.get(provider, ASR_PRESETS["none"])
    base = (cfg.asr_base if provider == "custom" else "") or preset["base"]
    model = (cfg.asr_model if provider == "custom" else "") or preset["model"]
    return {"base": base.rstrip("/"), "key": cfg.asr_key, "model": model, "provider": provider}


def _transcribe_api(path: str, base: str, key: str, model: str) -> str:
    """调 OpenAI 兼容 /audio/transcriptions，返回转写文本。"""
    audio = Path(path)
    if not audio.exists():
        raise FileNotFoundError(path)
    r = requests.post(
        f"{base}/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": (audio.name, audio.read_bytes())},
        data={"model": model},
        timeout=300,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ASR API 错误（HTTP {r.status_code}）: {r.text[:300]}")
    data = r.json()
    text = data.get("text") if isinstance(data, dict) else None
    if not text:
        raise RuntimeError("ASR API 返回结果为空")
    return str(text).strip()


def transcribe_audio(path: str, cfg: Config | None = None) -> str:
    """音频文件 → 转写文本。需在设置中配置 ASR provider（填 API key 即用）。"""
    cfg = cfg or Config()
    resolved = resolve_asr(cfg)
    if not resolved["base"] or not resolved["key"]:
        raise RuntimeError(
            "音频转写未配置：请在设置面板（或 config.json 的 asr_* 项）选择一个转写服务并填写 API key。"
            "预设：siliconflow（硅基流动）/ dashscope（阿里云百炼）/ zhipu（智谱）/ custom。"
        )
    text = _transcribe_api(path, resolved["base"], resolved["key"], resolved["model"])
    log.info("ASR 完成（provider=%s）", resolved["provider"])
    return text
