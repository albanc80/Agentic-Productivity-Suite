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


def apply_runtime(settings: Settings, base: dict, endpoints: list[Endpoint], offline: bool) -> None:
    """Rebuild providers, models and tier chains from the file config plus UI endpoints."""
    providers = dict(base["providers"])
    models = list(base["models"])
    tiers = {k: list(v) for k, v in base["tiers"].items()}
    for ep in endpoints:
        loc = locality_of(ep.base_url)
        providers[ep.provider_name] = ProviderConfig(
            type="openai_compatible", locality=loc, base_url=ep.base_url, api_key="not-needed",
            enabled=True, timeout_s=900, note=f"Added in the app ({loc}). {ep.name}")
        models = [m for m in models if m.ref != ep.ref] + [ModelConfig(
            ref=ep.ref, context_tokens=ep.context_tokens, max_output_tokens=ep.max_output_tokens, tools=ep.tools,
            note="UI endpoint")]
        for t in TIERS:
            chain = [r for r in tiers.get(t, []) if r != ep.ref]
            if t in ep.use_for:
                tiers[t] = [ep.ref] + chain  # tried first
            else:
                # Fallback for every other tier: after real models, ahead of the demo provider.
                demo_at = next((i for i, r in enumerate(chain)
                                if providers.get(r.split("/", 1)[0], ProviderConfig(type="mock")).type == "mock"), len(chain))
                tiers[t] = chain[:demo_at] + [ep.ref] + chain[demo_at:]
    settings.providers = providers
    settings.models = models
    settings.tiers = tiers
    settings.offline = offline
