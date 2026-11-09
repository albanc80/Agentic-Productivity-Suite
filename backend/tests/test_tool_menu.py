"""Fewer tokens before any reasoning: core tool sets, tools on demand, prompt caching that is counted, lean routing."""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
import yaml
from fastapi.testclient import TestClient

from app.connectors import ConnectorConfig, ConnectorManager
from app.main import create_app
from app.providers import Resolved, ToolSpec, Usage
from app.providers.anthropic_provider import _with_cache_breakpoint
from app.providers.openai_compat import cached_prompt_tokens
from app.settings import ModelConfig, ProviderConfig, load_settings
from app.toolmenu import FIND_TOOL, LOAD_LIMIT, ToolMenu
from tests.conftest import ROOT
from tests.test_chat import KEYS

OLD = Path(__file__).resolve().parent / "fixtures" / "old-connectors"
PRESETS = ROOT / "config" / "connectors.example.yaml"


def spec(name, desc):
    return ToolSpec(name, f"[x, read-only] {desc}", {"type": "object"})


MAIL = [spec("ms__list-mail-messages", "List, search and filter Outlook email messages."),
        spec("ms__get-mail-message", "Get a single Outlook email message by id."),
        spec("ms__list-mail-folder-messages-delta", "Messages added or changed in a folder."),
        spec("ms__get-calendar-view", "Events in a calendar view for a time range."),
        spec("gh__search_commits", "Search commits by message."),
        spec("gh__list_pull_requests", "List pull requests in a repository.")]
ROUTES = {t.name: t.name.split("__")[0] for t in MAIL}


def test_on_demand_starts_with_one_tool_and_loads_what_is_asked():
    calc = ToolSpec("casing_check", "A calculator.", {"type": "object"})
    menu = ToolMenu([*MAIL, calc], ROUTES, "on_demand", {"ms": "Microsoft 365", "gh": "GitHub"})
    assert [t.name for t in menu.offered()] == ["casing_check", FIND_TOOL]  # calculators stay; connector tools wait
    assert "Microsoft 365 (4 tools)" in menu.note() and FIND_TOOL in menu.note()
    out = menu.find({"query": "search my email"})
    loaded = [t.name for t in menu.offered()]
    assert "ms__list-mail-messages" in loaded and "ms__get-mail-message" in loaded
    assert "gh__search_commits" not in loaded and "ms__get-calendar-view" not in loaded  # subject: mail only
    assert loaded.index("ms__list-mail-messages") < loaded.index("ms__list-mail-folder-messages-delta")  # niche last
    assert "available now" in out
    menu.find({"query": "anything", "names": ["gh__list_pull_requests"]})
    assert "gh__list_pull_requests" in [t.name for t in menu.offered()]
    assert "No connector tool matched" in menu.find({"query": "weather in Paris"})


def test_core_and_all_offer_tools_directly_and_loading_is_capped():
    assert ToolMenu(MAIL, ROUTES, "core").offered() == MAIL and ToolMenu(MAIL, ROUTES, "all").note() == ""
    many = [spec(f"ms__list-mail-thing-{i}", "mail tool") for i in range(LOAD_LIMIT + 10)]
    menu = ToolMenu(many, {t.name: "ms" for t in many}, "on_demand")
    for _ in range(10):
        menu.find({"query": "mail", "names": [t.name for t in many]})
    assert len(menu.loaded) == LOAD_LIMIT


def test_microsoft365_core_set_reaches_every_old_connectors_file():
    shipped = next(c for c in yaml.safe_load(PRESETS.read_text())["connectors"] if c["id"] == "microsoft365")["core_tools"]
    assert 15 <= len(shipped) <= 25 and "list-mail-messages" in shipped and "list-accounts" in shipped
    for f in sorted(OLD.glob("*.yaml")):
        mgr = ConnectorManager.from_file(f, presets=PRESETS)
        assert mgr.configs["microsoft365"].core_tools == shipped, f.name


@pytest.mark.asyncio
async def test_core_filters_a_connectors_tools_to_its_core_set():
    from tests.fake_mcp_server import server
    mgr = ConnectorManager([ConnectorConfig(id="tracker", name="Tracker", transport="stdio", command="unused", enabled=True,
                                            core_tools=["get_issue"])], in_process={"tracker": server})
    try:
        every = {t.name for t in (await mgr.tools_for_agent()).tools}
        core = {t.name for t in (await mgr.tools_for_agent(core=True)).tools}
        assert core == {"get_issue"} and {"list_issues", "get_issue"} <= every
    finally:
        await mgr.shutdown()


def finder_model(seen: list):
    """Asks for tracker tools first, then calls the one it was given, then answers."""
    def handler(req):
        if req.url.path.endswith("/models"):
            return httpx2.Response(200, json={"object": "list", "data": [{"id": "m", "object": "model", "created": 0, "owned_by": "x"}]})
        body = json.loads(req.content)
        seen.append(body)
        offered = {t["function"]["name"] for t in body.get("tools") or []}
        results = [m for m in body["messages"] if m.get("role") == "tool"]
        if FIND_TOOL in offered and not results:
            call = {"name": FIND_TOOL, "arguments": json.dumps({"query": "list issues"})}
        elif "tracker__list_issues" in offered and len(results) == 1:
            call = {"name": "tracker__list_issues", "arguments": json.dumps({"project": "OPS"})}
        else:
            call = None
        msg = ({"role": "assistant", "content": None, "tool_calls": [{"id": f"t{len(results)}", "type": "function", "function": call}]}
               if call else {"role": "assistant", "content": "Open: " + (results[-1]["content"] if results else "none")})
        return httpx2.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": body["model"],
                                          "choices": [{"index": 0, "finish_reason": "tool_calls" if call else "stop", "message": msg}],
                                          "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                                                    "prompt_tokens_details": {"cached_tokens": 60}}})
    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def test_chat_on_demand_loads_the_tool_then_uses_it_and_counts_cached_tokens(tmp_path, monkeypatch):
    from tests.fake_mcp_server import server
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path / "data"))
    conns = ConnectorManager([ConnectorConfig(id="tracker", name="Team tracker", transport="stdio", command="unused",
                                              enabled=True)], in_process={"tracker": server})
    seen: list = []
    app = create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), connectors=conns, http_client=finder_model(seen))
    with TestClient(app) as c:
        c.put("/api/providers/openai", json={"enabled": True, "api_key": "sk-test",
                                             "models": [{"model": "gpt-x", "context_tokens": 128000, "tools": True}]})
        assert c.get("/api/overview").json()["tool_mode"] == "core"
        assert c.put("/api/settings/general", json={"tool_mode": "on_demand"}).status_code == 200
        assert c.get("/api/overview").json()["tool_mode"] == "on_demand"
        chat = c.post("/api/chats", json={"agent_id": "critical-mentor", "data_class": "public"}).json()
        msg = c.post(f"/api/chats/{chat['id']}/messages", json={"content": "What is open in OPS?"}).json()
        first = [t["function"]["name"] for t in seen[0]["tools"]]
        assert first == [FIND_TOOL]  # one small tool instead of every tracker tool
        assert "Connector tools load on demand" in seen[0]["messages"][0]["content"]
        assert "tracker__list_issues" in [t["function"]["name"] for t in seen[1]["tools"]]
        assert "OPS-1" in msg["content"] and msg["tool_calls"][0]["tool"] == "list_issues"
        assert msg["cached_tokens"] == 60 * len(seen) and msg["tokens"] == 120 * len(seen)  # cached counted, not lost
        assert c.put("/api/settings/general", json={"tool_mode": "everything"}).status_code == 422


def test_cached_tokens_are_read_and_priced():
    assert cached_prompt_tokens(SimpleNamespace(prompt_tokens_details=SimpleNamespace(cached_tokens=900))) == 900
    assert cached_prompt_tokens(SimpleNamespace(prompt_tokens_details=None, prompt_cache_hit_tokens=500)) == 500  # DeepSeek
    assert cached_prompt_tokens(SimpleNamespace(prompt_tokens_details=None)) == 0
    u = Usage(input_tokens=1_000_000, output_tokens=0, cache_read_tokens=1_000_000)
    model = ModelConfig(ref="a/m", price_in_per_mtok=3.0, price_out_per_mtok=15.0)
    anth = Resolved("a/m", None, model, ProviderConfig(type="anthropic", locality="cloud"))
    other = Resolved("o/m", None, model, ProviderConfig(type="openai_compatible", locality="cloud"))
    assert anth.cost(u) == pytest.approx(3.0 + 0.3)  # Anthropic cache reads: a tenth of the input price
    assert other.cost(u) == pytest.approx(6.0)  # unknown discount: full price, until one is set
    priced = Resolved("o/m", None, model.model_copy(update={"price_cached_per_mtok": 0.75}), other.config)
    assert priced.cost(u) == pytest.approx(3.75)


def test_anthropic_caches_the_conversation_without_changing_it():
    msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "data"}]}]
    out = _with_cache_breakpoint(msgs)
    assert out[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in msgs[-1]["content"][-1]  # the stored conversation is untouched
    assert sum("cache_control" in json.dumps(m) for m in out) == 1
    assert _with_cache_breakpoint([{"role": "user", "content": "x"}])[0]["content"][0]["cache_control"]


def test_routing_call_is_lean_and_shared_parts_come_first(tmp_path, monkeypatch):
    from tests.test_chat import server, setup_models
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    seen: list = []
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), http_client=server(seen, True))) as c:
        setup_models(c)
        cid = c.post("/api/chats", json={}).json()["id"]
        c.post(f"/api/chats/{cid}/messages", json={"content": "Should we build an AI assistant?"})
    route = next(x for x in seen if "Decide how to handle" in x["system"])
    answer = next(x for x in seen if x["role"] == "Chief of Staff" and "Decide how to handle" not in x["system"])
    assert "FIXTURE INSTRUCTIONS" not in route["system"] and "FIXTURE INSTRUCTIONS" in answer["system"]
    assert len(route["system"]) < len(answer["system"]) / 3
    assert answer["system"].index("# Output policies") < answer["system"].index("# Your role")
