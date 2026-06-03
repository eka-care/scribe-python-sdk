"""Configuration loading for the Scribe SDK.

Resolution precedence (highest wins):

    explicit kwargs  >  environment variables  >  config file  >  defaults

Config file may be JSON or YAML and is discovered (in order) from:
    1. an explicit path passed to `ScribeConfig.load(path=...)`
    2. the ``SCRIBE_CONFIG`` env var
    3. ``scribe.config.json`` / ``scribe.config.yaml`` in the current dir

A `.env` file in the cwd is loaded first so ``SCRIBE_*`` vars can live there.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .errors import ConfigError

DEFAULT_BASE_URL = "https://api.eka.care/voice"
DEFAULT_AUTH_BASE_URL = "https://api.eka.care"
_ENV_PREFIX = "SCRIBE_"
_FILE_CANDIDATES = ("scribe.config.json", "scribe.config.yaml", "scribe.config.yml")


@dataclass
class ScribeConfig:
    """Resolved SDK configuration."""

    # Auth / endpoints
    client_id: str | None = None
    client_secret: str | None = None
    api_key: str | None = None
    b_id: str | None = None  # business id, required for the streaming path
    base_url: str = DEFAULT_BASE_URL  # protocol base, e.g. https://api.eka.care/voice
    auth_base_url: str = DEFAULT_AUTH_BASE_URL  # connect-auth host

    # Session defaults (used when create_session() args are omitted)
    default_templates: list[str] = field(default_factory=list)
    default_model: str = "lite"
    default_language_hint: list[str] | None = None
    transcript_language: str | None = None

    # Dev escape hatch: send jwt-payload directly instead of Bearer (no gateway).
    # When set (a dict), it is JSON-encoded into the `jwt-payload` header and
    # the login/Bearer flow is skipped. Intended for local backend testing only.
    jwt_payload: dict[str, Any] | None = None

    # Behaviour
    request_timeout: float = 60.0
    poll_interval: float = 3.0
    poll_timeout: float = 600.0

    # ------------------------------------------------------------------ #
    @classmethod
    def load(
        cls,
        path: str | Path | None = None,
        *,
        load_env: bool = True,
        **overrides: Any,
    ) -> ScribeConfig:
        """Build a config from file + env + explicit overrides."""
        if load_env:
            load_dotenv()

        data: dict[str, Any] = {}
        data.update(_from_file(path))
        data.update(_from_env())
        # Drop None overrides so they don't clobber file/env values.
        data.update({k: v for k, v in overrides.items() if v is not None})

        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ConfigError(f"Unknown config keys: {sorted(unknown)}")
        return cls(**data)

    # ------------------------------------------------------------------ #
    def require_credentials(self) -> None:
        """Validate that an auth path is available."""
        if self.jwt_payload is not None:
            return
        if not (self.client_id and self.client_secret):
            raise ConfigError(
                "Missing credentials: set client_id and client_secret (or pass a "
                "jwt_payload for direct/dev auth)."
            )

    def require_b_id(self) -> str:
        if not self.b_id:
            raise ConfigError("Streaming requires `b_id` (business id) in config.")
        return self.b_id


def _from_file(path: str | Path | None) -> dict[str, Any]:
    resolved = _resolve_file(path)
    if resolved is None:
        return {}
    text = resolved.read_text()
    if resolved.suffix in (".yaml", ".yml"):
        import yaml  # local import: pyyaml is a core dep but keep import lazy

        loaded = yaml.safe_load(text) or {}
    else:
        loaded = json.loads(text) if text.strip() else {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"Config file {resolved} must contain a JSON/YAML object.")
    return loaded


def _resolve_file(path: str | Path | None) -> Path | None:
    if path:
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Config file not found: {p}")
        return p
    env_path = os.getenv(f"{_ENV_PREFIX}CONFIG")
    if env_path:
        p = Path(env_path)
        if not p.exists():
            raise ConfigError(f"SCRIBE_CONFIG points to a missing file: {p}")
        return p
    for candidate in _FILE_CANDIDATES:
        p = Path.cwd() / candidate
        if p.exists():
            return p
    return None


# Env var name -> (config field, parser)
_ENV_FIELDS: dict[str, tuple[str, Any]] = {
    f"{_ENV_PREFIX}CLIENT_ID": ("client_id", str),
    f"{_ENV_PREFIX}CLIENT_SECRET": ("client_secret", str),
    f"{_ENV_PREFIX}API_KEY": ("api_key", str),
    f"{_ENV_PREFIX}B_ID": ("b_id", str),
    f"{_ENV_PREFIX}BASE_URL": ("base_url", str),
    f"{_ENV_PREFIX}AUTH_BASE_URL": ("auth_base_url", str),
    f"{_ENV_PREFIX}DEFAULT_TEMPLATES": ("default_templates", "csv"),
    f"{_ENV_PREFIX}DEFAULT_MODEL": ("default_model", str),
    f"{_ENV_PREFIX}DEFAULT_LANGUAGE_HINT": ("default_language_hint", "csv"),
    f"{_ENV_PREFIX}TRANSCRIPT_LANGUAGE": ("transcript_language", str),
    f"{_ENV_PREFIX}REQUEST_TIMEOUT": ("request_timeout", float),
    f"{_ENV_PREFIX}POLL_INTERVAL": ("poll_interval", float),
    f"{_ENV_PREFIX}POLL_TIMEOUT": ("poll_timeout", float),
}


def _from_env() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for env_name, (field_name, parser) in _ENV_FIELDS.items():
        raw = os.getenv(env_name)
        if raw is None:
            continue
        if parser == "csv":
            out[field_name] = [p.strip() for p in raw.split(",") if p.strip()]
        else:
            out[field_name] = parser(raw)
    return out
