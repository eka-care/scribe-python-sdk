import json

import pytest

from scribe_sdk.config import ScribeConfig
from scribe_sdk.errors import ConfigError


def test_defaults():
    cfg = ScribeConfig.load(load_env=False)
    assert cfg.base_url == "https://api.eka.care/voice"
    assert cfg.default_templates == []


def test_json_file(tmp_path):
    p = tmp_path / "scribe.config.json"
    p.write_text(json.dumps({"client_id": "cid", "default_templates": ["soap", "rx"]}))
    cfg = ScribeConfig.load(path=p, load_env=False)
    assert cfg.client_id == "cid"
    assert cfg.default_templates == ["soap", "rx"]


def test_yaml_file(tmp_path):
    p = tmp_path / "scribe.config.yaml"
    p.write_text("client_id: yid\ndefault_model: pro\n")
    cfg = ScribeConfig.load(path=p, load_env=False)
    assert cfg.client_id == "yid"
    assert cfg.default_model == "pro"


def test_env_overrides_file(tmp_path, monkeypatch):
    p = tmp_path / "scribe.config.json"
    p.write_text(json.dumps({"client_id": "file_id"}))
    monkeypatch.setenv("SCRIBE_CLIENT_ID", "env_id")
    monkeypatch.setenv("SCRIBE_DEFAULT_TEMPLATES", "a,b,c")
    cfg = ScribeConfig.load(path=p, load_env=False)
    assert cfg.client_id == "env_id"
    assert cfg.default_templates == ["a", "b", "c"]


def test_kwargs_override_env(monkeypatch):
    monkeypatch.setenv("SCRIBE_CLIENT_ID", "env_id")
    cfg = ScribeConfig.load(load_env=False, client_id="explicit")
    assert cfg.client_id == "explicit"


def test_unknown_key_rejected(tmp_path):
    p = tmp_path / "scribe.config.json"
    p.write_text(json.dumps({"not_a_field": 1}))
    with pytest.raises(ConfigError):
        ScribeConfig.load(path=p, load_env=False)


def test_require_credentials():
    with pytest.raises(ConfigError):
        ScribeConfig().require_credentials()
    # explicit creds are accepted
    ScribeConfig(client_id="a", client_secret="b").require_credentials()
    # jwt_payload path is allowed without client creds
    ScribeConfig(jwt_payload={"b-id": "x"}).require_credentials()
