"""Model endpoints added from the UI, and the runtime offline switch.

An endpoint is any OpenAI-compatible server the user points the suite at: a
small model served by an app on a phone, a laptop on the same network, a GPU
box. The suite only connects; loading and configuring models stays with the
server that hosts them.

Locality is decided from the address, not from the user's say-so, because it
controls where "restricted" data may go: only loopback, private-network and
``.local`` hosts count as local. Anything else is treated as cloud.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator

from .settings import ModelConfig, ProviderConfig, Settings

TIERS = ("router", "specialist", "synthesis", "review")


class Endpoint(BaseModel):
    id: str
    name: str
    base_url: str
    model: str
    context_tokens: int = Field(default=4096, ge=1024, le=2_000_000)
    max_output_tokens: int = Field(default=1024, ge=128, le=128_000)
    tools: bool = False
    use_for: list[str] = Field(default_factory=lambda: ["router", "specialist"])
    api_key: str | None = None  # some local servers require one; never returned by the API

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = re.sub(r"[^a-z0-9-]+", "-", v.strip().lower()).strip("-")[:40]
        if not v:
            raise ValueError("id is required")
        return v

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str) -> str:
        return normalize_url(v)

    @field_validator("use_for")
    @classmethod
    def _tiers(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in TIERS]
        if bad:
            raise ValueError(f"unknown tiers {bad}")
        return list(dict.fromkeys(v))

    @property
    def provider_name(self) -> str:
        return f"ep-{self.id}"

    @property
    def ref(self) -> str:
        return f"{self.provider_name}/{self.model}"


class ModelEdit(BaseModel):
    model: str
    context_tokens: int = Field(default=8192, ge=1024, le=2_000_000)
    max_output_tokens: int = Field(default=2048, ge=128, le=128_000)
    tools: bool = False
    price_in_per_mtok: float | None = Field(default=None, ge=0, le=10_000)  # USD per million tokens
    price_cached_per_mtok: float | None = Field(default=None, ge=0, le=10_000)  # cached input; None: see ModelConfig
    price_out_per_mtok: float | None = Field(default=None, ge=0, le=10_000)

    @field_validator("model")
    @classmethod
    def _model(cls, v: str) -> str:
        v = v.strip()
        if not v or "\n" in v:
            raise ValueError("model id is required")
        return v


class ProviderOverride(BaseModel):
    """Changes made in the app to a provider from the config file. Unset fields keep the file value."""

    enabled: bool | None = None
    base_url: str | None = None
    api_key: str | None = None
    models: list[ModelEdit] | None = None

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return normalize_url(v) if v else None


def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if "://" not in raw:
        raw = "http://" + raw
    u = urlparse(raw)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("enter an http(s) address such as http://192.168.1.20:8080")
    path = u.path.rstrip("/") or "/v1"  # OpenAI-compatible servers serve under /v1
    return urlunparse((u.scheme, u.netloc, path, "", "", ""))


def is_local_host(host: str, resolve: bool = True) -> bool:
    """True for loopback, private, link-local and unique-local addresses and *.local names."""
    host = (host or "").strip("[]").lower()
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if not resolve:
            return False
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError:
            return False
        addrs = {i[4][0] for i in infos}
        return bool(addrs) and all(is_local_host(a, resolve=False) for a in addrs)
    return ip.is_loopback or ip.is_private or ip.is_link_local


def locality_of(base_url: str) -> str:
    return "local" if is_local_host(urlparse(base_url).hostname or "") else "cloud"


def _apply_override(name: str, ov: ProviderOverride, providers: dict, models: list, tiers: dict) -> list:
    cfg: ProviderConfig = providers[name]
    upd: dict = {"edited_in_app": True}
    if ov.enabled is not None:
        upd["enabled"] = ov.enabled
    if ov.base_url:
        upd["base_url"] = ov.base_url
        # A local provider pointed at an address outside your network is treated as cloud.
        if cfg.locality == "local" and locality_of(ov.base_url) != "local":
            upd["locality"] = "cloud"
    if ov.api_key:
        upd["api_key"] = ov.api_key
        upd["key_saved_in_app"] = True
    providers[name] = cfg.model_copy(update=upd)
    if ov.models is not None:
        old = {m.ref: m for m in models if m.provider == name}
        new = []
        for m in ov.models:
            ref = f"{name}/{m.model}"
            prev = old.get(ref)
            new.append(ModelConfig(ref=ref, context_tokens=m.context_tokens, max_output_tokens=m.max_output_tokens,
                                   tools=m.tools,
                                   price_in_per_mtok=m.price_in_per_mtok if m.price_in_per_mtok is not None
                                   else (prev.price_in_per_mtok if prev else 0.0),
                                   price_out_per_mtok=m.price_out_per_mtok if m.price_out_per_mtok is not None
                                   else (prev.price_out_per_mtok if prev else 0.0),
                                   price_cached_per_mtok=m.price_cached_per_mtok if m.price_cached_per_mtok is not None
                                   else (prev.price_cached_per_mtok if prev else None),
                                   effort=prev.effort if prev else None, note="edited in the app"))
        models = [m for m in models if m.provider != name] + new
        keep = {m.ref for m in new}
        first = new[0].ref if new else None
        for t, chain in tiers.items():
            out: list[str] = []
            for r in chain:
                if r.split("/", 1)[0] == name and r not in keep:
                    r = first  # chain slots that used a removed model now use the provider's first model
                if r and r not in out:
                    out.append(r)
            tiers[t] = out
    # Switched on in the app: also a fallback for every tier that does not use this provider yet,
    # so turning on one local model is enough to run any playbook.
    if providers[name].enabled and ov.enabled:
        own = [m.ref for m in models if m.provider == name]
        if own:
            for t in TIERS:
                chain = tiers.setdefault(t, [])
                if not any(r.split("/", 1)[0] == name for r in chain):
                    chain.append(own[0])
    return models


def apply_runtime(settings: Settings, base: dict, endpoints: list[Endpoint], offline: bool,
                  overrides: dict[str, ProviderOverride] | None = None) -> None:
    """Rebuild providers, models and tier chains: file config, then app edits, then app endpoints."""
    providers = dict(base["providers"])
    models = list(base["models"])
    tiers = {k: list(v) for k, v in base["tiers"].items()}
    for name, ov in (overrides or {}).items():
        if name in providers:
            models = _apply_override(name, ov, providers, models, tiers)
    for ep in endpoints:
        loc = locality_of(ep.base_url)
        providers[ep.provider_name] = ProviderConfig(
            type="openai_compatible", locality=loc, base_url=ep.base_url, api_key=ep.api_key or "not-needed",
            key_saved_in_app=bool(ep.api_key), enabled=True, timeout_s=900, note=f"Added in the app ({loc}). {ep.name}")
        models = [m for m in models if m.ref != ep.ref] + [ModelConfig(
            ref=ep.ref, context_tokens=ep.context_tokens, max_output_tokens=ep.max_output_tokens, tools=ep.tools,
            note="UI endpoint")]
        for t in TIERS:
            chain = [r for r in tiers.get(t, []) if r != ep.ref]
            if t in ep.use_for:
                tiers[t] = [ep.ref] + chain  # tried first
            else:
                tiers[t] = chain + [ep.ref]  # fallback for every other tier, after the models already there
    settings.providers = providers
    settings.models = models
    settings.tiers = tiers
    settings.offline = offline
