from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from app.connectors import ConnectorConfig, ConnectorManager
from app.engine import Engine
from app.playbooks import load_playbooks
from app.providers import ModelRouter
from app.providers.base import ChatResult, Conversation, Usage
from app.registry import Registry
from app.settings import Budgets, ModelConfig, ProviderConfig, Settings
from app.store import Store

ROOT = Path(__file__).resolve().parents[2]


def contract(status="COMPLETE", **kw) -> str:
    body = {"status": status, "summary": kw.pop("summary", "ok"),
            "claims": kw.pop("claims", [{"text": "Input received", "label": "FACT", "trace": "input:request"}]),
            "risks": kw.pop("risks", []), "open_questions": [], "next_action": {"action": "next", "owner": "user"},
            "skills_invoked": [], "evidence": kw.pop("evidence", "NOT_EXECUTED"), **kw}
    return "```json\n" + json.dumps(body) + "\n```"


class ScriptedProvider:
    """Deterministic stand-in for a model. `script(system, messages, tools)` returns text or ToolCalls."""

    def __init__(self, name: str, script: Callable | None = None):
        self.name = name
        self.script = script or (lambda system, messages, tools: "Deliverable text.\n\n" + contract())
        self.calls: list[dict] = []

    def start(self, system: str, user: str) -> Conversation:
        return Conversation(system=system, messages=[{"role": "user", "content": user}])

    async def chat(self, conv, *, model, tools, max_tokens, effort=None) -> ChatResult:
        self.calls.append({"system": conv.system, "messages": list(conv.messages), "tools": tools, "model": model})
        out = self.script(conv.system, conv.messages, tools)
        if isinstance(out, Exception):
            raise out
        if isinstance(out, list):
            return ChatResult("", out, "tool_calls", Usage(100, 10), model, 5, {"role": "assistant", "tool_calls": out})
        return ChatResult(out, [], "stop", Usage(100, 50), model, 5, {"role": "assistant", "content": out})

    def add_assistant(self, conv, result):
        conv.messages.append(result.native)

    def add_tool_results(self, conv, results):
        for cid, content, err in results:
            conv.messages.append({"role": "tool", "tool_call_id": cid, "content": content, "is_error": err})

    def add_user(self, conv, text):
        conv.messages.append({"role": "user", "content": text})


def agent_of(system: str) -> str:
    m = re.search(r"^You are acting as: (.+?) \(", system, re.M)
    return m.group(1) if m else ""


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        home=ROOT, data_dir=tmp_path, profile_path=ROOT / "config" / "profile.example.yaml",
        allow_demo_provider=False,
        providers={
            "local": ProviderConfig(type="openai_compatible", locality="local", base_url="http://local/v1", api_key="x"),
            "cloud": ProviderConfig(type="openai_compatible", locality="cloud", base_url="http://cloud/v1", api_key="k"),
        },
        models=[ModelConfig(ref="local/small", context_tokens=200_000, tools=True),
                ModelConfig(ref="cloud/big", context_tokens=200_000, tools=True,
                            price_in_per_mtok=1.0, price_out_per_mtok=2.0)],
        tiers={t: ["cloud/big", "local/small"] for t in ("router", "specialist", "synthesis", "review")},
        budgets=Budgets(),
    )


@pytest.fixture
def make_engine(settings):
    created = []

    def _make(local_script=None, cloud_script=None, connectors: ConnectorManager | None = None, **overrides):
        s = settings.model_copy(update=overrides)
        reg = Registry(s.registry_dir, s.policies_dir)
        conns = connectors or ConnectorManager([])
        books, _ = load_playbooks(s.playbooks_dir, reg, set(conns.configs) or None)
        router = ModelRouter(s)
        local, cloud = ScriptedProvider("local", local_script), ScriptedProvider("cloud", cloud_script)
        router._instances.update({"local": local, "cloud": cloud})
        store = Store(s.data_dir / "test.db")
        eng = Engine(s, reg, books, router, conns, store, {"role": "Tester"})
        created.append(conns)
        return eng, local, cloud
    yield _make


@pytest.fixture
def tracker_connector():
    from tests.fake_mcp_server import server
    cfg = ConnectorConfig(id="github", name="Fake GitHub", transport="stdio", command="unused")
    return ConnectorManager([cfg], env={}, in_process={"github": server})


async def run_to_rest(eng: Engine, rid: str) -> dict:
    for _ in range(50):
        await eng.wait(rid)
        r = eng.store.run(rid)
        if r["status"] not in ("queued", "running"):
            return r
    raise AssertionError("run did not settle")
