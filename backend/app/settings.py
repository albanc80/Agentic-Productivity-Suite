"""Suite configuration.

Configuration lives in ``config/suite.yaml`` (falls back to ``config/suite.example.yaml``).
Secrets never live in the file: providers and connectors name the environment
variable that holds a credential (``api_key_env``, ``${VAR}``) and the value is
read at call time. The suite never persists or logs credential values.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

DataClass = Literal["public", "internal", "confidential", "restricted"]
Locality = Literal["local", "cloud"]
Tier = Literal["router", "specialist", "synthesis", "review"]

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def expand_env(value: Any, env: dict[str, str] | None = None) -> Any:
    """Expand ``${VAR}`` and ``${VAR:-default}`` in strings, lists and dicts."""
    env = os.environ if env is None else env
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: env.get(m.group(1), m.group(2) if m.group(2) is not None else ""), value)
    if isinstance(value, list):
        return [expand_env(v, env) for v in value]
    if isinstance(value, dict):
        return {k: expand_env(v, env) for k, v in value.items()}
    return value


def env_refs(value: Any) -> set[str]:
    """Return the environment variable names referenced by ``${VAR}`` without a default."""
    found: set[str] = set()
    if isinstance(value, str):
        for m in _ENV_RE.finditer(value):
            if m.group(2) is None:
                found.add(m.group(1))
    elif isinstance(value, list):
        for v in value:
            found |= env_refs(v)
    elif isinstance(value, dict):
        for v in value.values():
            found |= env_refs(v)
    return found


class ProviderConfig(BaseModel):
    type: Literal["openai_compatible", "anthropic", "mock"]
    locality: Locality = "cloud"
    base_url: str | None = None
    api_key: str | None = None  # only for keyless local servers (e.g. "ollama")
    api_key_env: str | None = None
    enabled: bool = True
    timeout_s: float = 300.0
    max_retries: int = 2
    headers: dict[str, str] = Field(default_factory=dict)
    refusal_fallback: bool = True  # anthropic only: server-side refusal fallbacks
    note: str = ""


class ModelConfig(BaseModel):
    """Capabilities and pricing of one model on one provider. ``ref`` = provider/model."""

    ref: str
    context_tokens: int = 8192
    max_output_tokens: int = 8000
    tools: bool = False
    price_in_per_mtok: float = 0.0
    price_out_per_mtok: float = 0.0
    effort: str | None = None  # anthropic output_config.effort
    note: str = ""

    @property
    def provider(self) -> str:
        return self.ref.split("/", 1)[0]

    @property
    def model(self) -> str:
        return self.ref.split("/", 1)[1]

    @field_validator("ref")
    @classmethod
    def _has_provider(cls, v: str) -> str:
        if "/" not in v:
            raise ValueError("model ref must be 'provider/model'")
        return v


class Budgets(BaseModel):
    max_run_cost_usd: float = 2.0
    max_run_tokens: int = 400_000
    max_steps: int = 40
    max_tool_calls_per_step: int = 8
    max_tool_result_chars: int = 12_000
    max_context_fraction: float = 0.75


class PersonaSettings(BaseModel):
    chat: bool = True
    exports: bool = False


class Settings(BaseModel):
    home: Path
    data_dir: Path
    profile_path: Path | None = None
    store_prompts: bool = False
    allow_demo_provider: bool = True
    persona: PersonaSettings = PersonaSettings()
    output_policies: list[str] = Field(default_factory=lambda: ["plain-voice", "action-first"])
    budgets: Budgets = Budgets()
    data_classes: dict[str, list[Locality]] = Field(
        default_factory=lambda: {
            "public": ["local", "cloud"],
            "internal": ["local", "cloud"],
            "confidential": ["local", "cloud"],
            "restricted": ["local"],
        }
    )
    default_data_class: DataClass = "internal"
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    models: list[ModelConfig] = Field(default_factory=list)
    tiers: dict[str, list[str]] = Field(default_factory=dict)
    agent_overrides: dict[str, list[str]] = Field(default_factory=dict)
    connectors_path: Path | None = None
    theme_dir: Path | None = None

    @property
    def registry_dir(self) -> Path:
        return self.home / "registry"

    @property
    def playbooks_dir(self) -> Path:
        return self.home / "playbooks"

    @property
    def policies_dir(self) -> Path:
        return self.home / "config" / "policies"

    def model(self, ref: str) -> ModelConfig:
        for m in self.models:
            if m.ref == ref:
                return m
        provider = ref.split("/", 1)[0]
        local = self.providers.get(provider, ProviderConfig(type="mock")).locality == "local"
        # Unknown model: conservative defaults (small context, no tools, unpriced).
        return ModelConfig(ref=ref, context_tokens=8192 if local else 128_000, tools=False)


def _first_existing(*paths: Path) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def load_settings(home: Path | None = None, config_path: Path | None = None) -> Settings:
    home = (home or Path(os.environ.get("SUITE_HOME", Path(__file__).resolve().parents[2]))).resolve()
    cfg_path = config_path or (Path(os.environ["SUITE_CONFIG"]) if os.environ.get("SUITE_CONFIG") else None)
    cfg_path = cfg_path or _first_existing(home / "config" / "suite.yaml", home / "config" / "suite.example.yaml")
    raw: dict[str, Any] = {}
    if cfg_path and cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    def rel(p: str | None) -> Path | None:
        if not p:
            return None
        q = Path(expand_env(p))
        return q if q.is_absolute() else home / q

    data_dir = rel(os.environ.get("SUITE_DATA_DIR") or raw.get("data_dir")) or home / "data"
    profile = _first_existing(*(x for x in (rel(raw.get("profile")), home / "config" / "profile.yaml",
                                            home / "config" / "profile.example.yaml") if x))
    connectors = _first_existing(*(x for x in (rel(os.environ.get("SUITE_CONNECTORS") or raw.get("connectors")),
                                               home / "config" / "connectors.yaml",
                                               home / "config" / "connectors.example.yaml") if x))
    theme = rel(os.environ.get("SUITE_THEME_DIR") or raw.get("theme_dir"))
    fields = {k: v for k, v in raw.items() if k in Settings.model_fields and k not in {"home", "data_dir", "profile_path", "connectors_path", "theme_dir"}}
    s = Settings(home=home, data_dir=data_dir, profile_path=profile, connectors_path=connectors, theme_dir=theme, **fields)
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s


def load_profile(settings: Settings) -> dict[str, Any]:
    if settings.profile_path and settings.profile_path.exists():
        return yaml.safe_load(settings.profile_path.read_text(encoding="utf-8")) or {}
    return {}
