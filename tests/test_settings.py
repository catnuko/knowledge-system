"""设置相关测试：config.json 持久化、ASR 预设解析、settings API。"""
import json
import os
from pathlib import Path

import pytest

from knowledge_engine.config import Config, SETTING_KEYS
from knowledge_engine.ingest.audio import ASR_PRESETS, resolve_asr, transcribe_audio
from knowledge_engine.web.app import create_app


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("KE_DB", str(tmp_path / "ke.db"))
    # 清掉可能影响断言的环境变量，保证默认值分支可测
    for var in ("KE_LLM", "KE_LLM_BASE", "KE_LLM_KEY", "KE_LLM_MODEL",
                "KE_ASR", "KE_ASR_BASE", "KE_ASR_KEY", "KE_ASR_MODEL", "KE_EMBEDDING"):
        monkeypatch.delenv(var, raising=False)
    return Config()


def test_defaults(cfg):
    assert cfg.llm_provider == "rule"
    assert cfg.llm_base == "https://api.deepseek.com/v1"
    assert cfg.llm_model == "deepseek-chat"
    assert cfg.asr_provider == "none"
    assert cfg.embedding == "light"


def test_env_overrides_file(cfg, monkeypatch):
    cfg.save({"llm_model": "from-file"})
    monkeypatch.setenv("KE_LLM_MODEL", "from-env")
    assert Config().llm_model == "from-env"  # 环境变量优先
    monkeypatch.delenv("KE_LLM_MODEL")
    assert Config().llm_model == "from-file"  # 文件优先于默认值


def test_save_persists_and_ignores_unknown(cfg):
    saved = cfg.save({"llm_key": "sk-abc", "not_allowed": "x"})
    assert saved["llm_key"] == "sk-abc"
    on_disk = json.loads(cfg.config_path.read_text())
    assert on_disk == {"llm_key": "sk-abc"}
    assert "not_allowed" not in SETTING_KEYS
    assert Config().llm_key == "sk-abc"  # 新实例读回


def test_save_refreshes_cached_instance(cfg):
    cfg.save({"llm_key": "sk-1"})
    assert cfg.llm_key == "sk-1"  # 同一实例立即生效，无需重建


def test_asr_presets_resolve(cfg):
    for provider, base, model in [
        ("dashscope", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-asr-flash"),
        ("siliconflow", "https://api.siliconflow.cn/v1", "FunAudioLLM/SenseVoiceSmall"),
        ("zhipu", "https://open.bigmodel.cn/api/paas/v4", "glm-asr"),
    ]:
        cfg.save({"asr_provider": provider})
        r = resolve_asr(cfg)
        assert (r["base"], r["model"]) == (base, model)


def test_asr_custom_overrides(cfg):
    cfg.save({"asr_provider": "custom", "asr_base": "https://my.corp/v1/", "asr_model": "my-model"})
    r = resolve_asr(cfg)
    assert r["base"] == "https://my.corp/v1"  # 去尾部斜杠
    assert r["model"] == "my-model"


def test_transcribe_requires_config(cfg):
    with pytest.raises(RuntimeError, match="未配置"):
        transcribe_audio("whatever.wav", cfg)
    cfg.save({"asr_provider": "dashscope", "asr_key": "k"})
    with pytest.raises(FileNotFoundError):
        transcribe_audio("whatever.wav", cfg)


def test_all_setting_keys_have_config_properties():
    for key in SETTING_KEYS:
        assert hasattr(Config, key), f"Config 缺少属性 {key}"
    assert "none" in ASR_PRESETS


# ---------- settings API ----------

@pytest.fixture
def client(cfg):
    from fastapi.testclient import TestClient
    return TestClient(create_app(cfg))


def test_api_settings_get_masks_key(client, cfg):
    cfg.save({"llm_key": "sk-secret-9999", "asr_key": "sk-asr-0000"})
    data = client.get("/api/settings").json()
    assert data["llm"]["key_masked"] == "***9999"
    assert data["llm"]["has_key"] is True
    assert "sk-secret" not in json.dumps(data)  # 明文 key 不得出现
    assert "dashscope" in data["asr"]["presets"]


def test_api_settings_put_persists(client, cfg):
    r = client.put("/api/settings", json={"settings": {
        "llm_provider": "openai", "llm_key": "sk-new-key", "evil": "x"}}).json()
    assert r["llm"]["provider"] == "openai"
    assert cfg.config_path.exists()
    on_disk = json.loads(cfg.config_path.read_text())
    assert on_disk["llm_key"] == "sk-new-key"
    assert "evil" not in on_disk


def test_api_test_llm_rule_mode(client):
    r = client.post("/api/settings/test-llm").json()
    assert r["ok"] is False
    assert "rule" in r["error"]


def test_api_test_llm_ping_ok(client, cfg, monkeypatch):
    cfg.save({"llm_provider": "openai", "llm_key": "sk-x"})
    from knowledge_engine.llm.openai import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "ping",
                        lambda self: {"ok": True, "detail": "fake ok"})
    r = client.post("/api/settings/test-llm").json()
    assert r == {"ok": True, "detail": "fake ok"}


def test_api_test_asr_unconfigured(client):
    r = client.post("/api/settings/test-asr").json()
    assert r["ok"] is False
    assert "key" in r["error"]


def test_api_ingest_rejects_oversized_upload(client, monkeypatch):
    import knowledge_engine.web.app as webapp
    monkeypatch.setitem(webapp.MAX_UPLOAD, "audio", 10)
    r = client.post("/api/ingest/audio", files={"file": ("a.wav", b"x" * 11)})
    assert r.status_code == 413
    assert "上限" in r.json()["detail"]


def test_api_ingest_rejects_wrong_suffix(client):
    r = client.post("/api/ingest/audio", files={"file": ("a.txt", b"x")})
    assert r.status_code == 400
