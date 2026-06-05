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
    p.write_text(
        json.dumps({"default_model": "pro", "default_templates": ["soap", "rx"]})
    )
    cfg = ScribeConfig.load(path=p, load_env=False)
    assert cfg.default_model == "pro"
    assert cfg.default_templates == ["soap", "rx"]


def test_yaml_file(tmp_path):
    p = tmp_path / "scribe.config.yaml"
    p.write_text("transcript_language: en\ndefault_model: pro\n")
    cfg = ScribeConfig.load(path=p, load_env=False)
    assert cfg.transcript_language == "en"
    assert cfg.default_model == "pro"


def test_env_overrides_file(tmp_path, monkeypatch):
    p = tmp_path / "scribe.config.json"
    p.write_text(json.dumps({"default_model": "lite"}))
    monkeypatch.setenv("SCRIBE_CLIENT_ID", "env_id")
    monkeypatch.setenv("SCRIBE_DEFAULT_TEMPLATES", "a,b,c")
    monkeypatch.setenv("SCRIBE_DEFAULT_MODEL", "pro")
    cfg = ScribeConfig.load(path=p, load_env=False)
    assert cfg.client_id == "env_id"
    assert cfg.default_model == "pro"
    assert cfg.default_templates == ["a", "b", "c"]


@pytest.mark.parametrize("secret_key", ["client_id", "client_secret"])
def test_credentials_in_json_file_rejected(tmp_path, secret_key):
    p = tmp_path / "scribe.config.json"
    p.write_text(json.dumps({secret_key: "should-not-be-here"}))
    with pytest.raises(ConfigError, match=secret_key):
        ScribeConfig.load(path=p, load_env=False)


@pytest.mark.parametrize("secret_key", ["client_id", "client_secret"])
def test_credentials_in_yaml_file_rejected(tmp_path, secret_key):
    p = tmp_path / "scribe.config.yaml"
    p.write_text(f"{secret_key}: should-not-be-here\n")
    with pytest.raises(ConfigError, match=secret_key):
        ScribeConfig.load(path=p, load_env=False)


def test_credentials_from_env(tmp_path, monkeypatch):
    """Secrets come from env even when a (secret-free) config file is present."""
    p = tmp_path / "scribe.config.json"
    p.write_text(json.dumps({"default_model": "pro"}))
    monkeypatch.setenv("SCRIBE_CLIENT_ID", "env_id")
    monkeypatch.setenv("SCRIBE_CLIENT_SECRET", "env_secret")
    cfg = ScribeConfig.load(path=p, load_env=False)
    assert cfg.client_id == "env_id"
    assert cfg.client_secret == "env_secret"


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
