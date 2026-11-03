"""Model routing across local and cloud providers.

A step asks for a tier (router, specialist, synthesis, review) or names model
refs explicitly. The router returns the ordered candidates that are:
  1. configured and enabled (cloud providers also need their API key),
  2. allowed for the run's data class (e.g. ``restricted`` -> local only).
The engine tries them in order and falls back on provider errors or refusals.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..settings import ModelConfig, ProviderConfig, Settings
from .anthropic_provider import AnthropicProvider
from .base import ChatResult, Conversation, Provider, ProviderError, ProviderRefusal, ToolCall, ToolSpec, Usage
from .openai_compat import OpenAICompatibleProvider

__all__ = [
    "ChatResult", "Conversation", "ModelRouter", "Provider", "ProviderError",
    "ProviderRefusal", "Resolved", "ToolCall", "ToolSpec", "Usage", "NoModelAvailable",
]


class NoModelAvailable(Exception):
    pass


@dataclass
class Resolved:
    ref: str
    provider: Provider
    model: ModelConfig
    config: ProviderConfig

    def cost(self, usage: Usage) -> float:
        # Conservative: cache reads are billed at the full input rate here.
        return (usage.input_tokens + usage.cache_read_tokens) * self.model.price_in_per_mtok / 1e6 + \
            usage.output_tokens * self.model.price_out_per_mtok / 1e6


class ModelRouter:
    def __init__(self, settings: Settings, http_client=None):
        self.settings = settings
        self._http_client = http_client
        self._instances: dict[str, Provider] = {}

    # ---------------------------------------------------------------- status

    def _api_key(self, cfg: ProviderConfig) -> str | None:
        env = os.environ.get(cfg.api_key_env) if cfg.api_key_env else None
        return env or cfg.api_key or None

    def key_source(self, cfg: ProviderConfig) -> str | None:
        if cfg.api_key_env and os.environ.get(cfg.api_key_env):
            return "env"
        if cfg.key_saved_in_app:
            return "app"
        return "config" if cfg.api_key else None

    def availability(self, name: str) -> tuple[bool, str]:
        cfg = self.settings.providers.get(name)
        if cfg is None:
            return False, "not configured"
        if not cfg.enabled:
            return False, "switched off"
        if cfg.locality == "cloud" and self.settings.offline:
            return False, "offline mode"
        if cfg.locality == "cloud" and not self._api_key(cfg):
            return False, "missing API key (add it with Edit" + (f", or set {cfg.api_key_env}" if cfg.api_key_env else "") + ")"
        return True, "ready"

    def describe(self) -> list[dict]:
        out = []
        for name, cfg in self.settings.providers.items():
            ok, reason = self.availability(name)
            out.append({"name": name, "type": cfg.type, "locality": cfg.locality, "base_url": cfg.base_url,
                        "enabled": cfg.enabled, "available": ok, "reason": reason,
                        "offline_paused": cfg.locality == "cloud" and self.settings.offline, "api_key_env": cfg.api_key_env,
                        "api_key_source": self.key_source(cfg), "edited_in_app": cfg.edited_in_app,
                        "endpoint": name.startswith("ep-"), "note": cfg.note,
                        "models": [m.model_dump() for m in self.settings.models if m.provider == name]})
        return out

    # ---------------------------------------------------------------- build

    def provider(self, name: str) -> Provider:
        if name in self._instances:
            return self._instances[name]
        cfg = self.settings.providers[name]
        p: Provider
        if cfg.type == "anthropic":
            p = AnthropicProvider(name, api_key=self._api_key(cfg) or "", timeout_s=cfg.timeout_s,
                                  max_retries=cfg.max_retries, refusal_fallback=cfg.refusal_fallback,
                                  base_url=cfg.base_url, http_client=self._http_client)
        else:
            if not cfg.base_url:
                raise ProviderError(f"provider {name} needs base_url")
            p = OpenAICompatibleProvider(name, base_url=cfg.base_url, api_key=self._api_key(cfg) or "",
                                         timeout_s=cfg.timeout_s, max_retries=cfg.max_retries,
                                         headers=cfg.headers, http_client=self._http_client)
        self._instances[name] = p
        return p

    # ---------------------------------------------------------------- resolve

    def chain(self, tier: str, agent_id: str | None = None, override: list[str] | None = None) -> list[str]:
        if override:
            return list(override)
        if agent_id and agent_id in self.settings.agent_overrides:
            return list(self.settings.agent_overrides[agent_id])
        return list(self.settings.tiers.get(tier) or self.settings.tiers.get("specialist") or [])

    def candidates(self, tier: str, data_class: str, *, agent_id: str | None = None,
                   override: list[str] | None = None) -> tuple[list[Resolved], list[str]]:
        allowed = set(self.settings.data_classes.get(data_class, ["local"]))
        result: list[Resolved] = []
        skipped: list[str] = []
        for ref in self.chain(tier, agent_id, override):
            pname = ref.split("/", 1)[0]
            ok, reason = self.availability(pname)
            if not ok:
                skipped.append(f"{ref}: {reason}")
                continue
            cfg = self.settings.providers[pname]
            if cfg.locality not in allowed:
                skipped.append(f"{ref}: {cfg.locality} provider not allowed for '{data_class}' data")
                continue
            result.append(Resolved(ref=ref, provider=self.provider(pname), model=self.settings.model(ref), config=cfg))
        return result, skipped
