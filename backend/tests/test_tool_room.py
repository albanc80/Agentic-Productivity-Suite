"""Connector tools no longer crowd out the conversation: models get compact tool definitions, the cause is named,
and the default answer length is 8,192 tokens (1.0.0)."""

import json

from fastapi.testclient import TestClient

from app.connectors import PARAM_DESC_MAX, TOOL_DESC_MAX, compact_schema, model_tool, short_text
from app.main import create_app
from app.prompts import tool_share_note
from app.settings import ModelConfig, load_settings
from tests.conftest import ROOT

# Shaped like a real Microsoft 365 server tool (get-calendar-view): long help on every parameter.
LONG = ("The start date and time of the time range, represented in ISO 8601 format. For example, 2019-11-08T19:00:00-08:00. "
        "Use the time zone of the calendar owner when you can; otherwise UTC is assumed by Microsoft Graph for this request. ") * 3
SCHEMA = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object", "required": ["startDateTime"],
          "properties": {"startDateTime": {"type": "string", "description": LONG, "examples": ["2019-11-08T19:00:00Z"]},
                         "description": {"type": "string", "description": "A parameter that happens to be called description."},
                         "examples": {"type": "array", "items": {"type": "string"}},
                         "orderby": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}}],
                                     "description": LONG}}}


def test_compact_schema_keeps_what_a_call_needs_and_drops_the_essay():
    out = compact_schema(SCHEMA)
    assert "$schema" not in out and out["required"] == ["startDateTime"] and out["type"] == "object"
    props = out["properties"]
    assert set(props) == {"startDateTime", "description", "examples", "orderby"}  # parameter names are never dropped
    assert props["startDateTime"]["type"] == "string" and "examples" not in props["startDateTime"]
    assert len(props["startDateTime"]["description"]) <= PARAM_DESC_MAX
    assert props["startDateTime"]["description"].startswith("The start date and time of the time range")
    assert props["orderby"]["anyOf"][1]["items"]["enum"] == ["a", "b"]
    assert props["examples"] == {"type": "array", "items": {"type": "string"}}
    assert len(json.dumps(out)) < len(json.dumps(SCHEMA)) / 2


def test_short_text_cuts_at_a_sentence_or_a_word():
    assert short_text("Short.", 50) == "Short."
    assert short_text("First sentence here. Second sentence that is long.", 30) == "First sentence here."
    assert short_text("one two three four five six seven", 15).endswith("…")
    desc, schema = model_tool("microsoft365", "x " * 500, None)
    assert desc.startswith("[microsoft365, read-only] ") and len(desc) <= len("[microsoft365, read-only] ") + TOOL_DESC_MAX + 1
    assert schema == {"type": "object"}


def test_the_note_names_connector_tools_when_they_take_the_room():
    note = tool_share_note("openrouter/qwen", 55_000, 128_000, chat=True)
    assert "connector tools take about 55,000 of the model's 128,000-token context" in note and "switches under the chat" in note
    assert tool_share_note("openrouter/qwen", 9_000, 128_000, chat=True) is None


def test_default_answer_length_is_8192_and_old_saved_defaults_are_raised_once(tmp_path, monkeypatch):
    assert ModelConfig(ref="x/y").max_output_tokens == 8192
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    app = create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"))
    store = app.state.suite.store
    store.set_setting("upgraded_max_answer_default", False)
    store.set_setting("provider_overrides", {"openrouter": {"models": [
        {"model": "qwen/qwen3.8-flash", "context_tokens": 128000, "max_output_tokens": 8000, "tools": True},
        {"model": "other", "context_tokens": 128000, "max_output_tokens": 4000, "tools": False}]}})
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"))) as c:
        models = c.app.state.suite.store.get_setting("provider_overrides", {})["openrouter"]["models"]
        assert [m["max_output_tokens"] for m in models] == [8192, 4000]  # only the old default changes
        c.app.state.suite.store.set_setting("provider_overrides", {"openrouter": {"models": [{**models[0], "max_output_tokens": 8000}]}})
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"))) as c:  # once only
        assert c.app.state.suite.store.get_setting("provider_overrides", {})["openrouter"]["models"][0]["max_output_tokens"] == 8000


def _length_then_rest_server(calls: list, status: str = "NEEDS_INPUT"):
    """A model whose first reply stops at the answer length before its contract (like qwen3.8-flash on PB-07)."""
    import httpx2

    from tests.conftest import contract

    def handler(req):
        if req.url.path.endswith("/models"):
            return httpx2.Response(200, json={"object": "list", "data": [{"id": "m1", "object": "model", "created": 0, "owned_by": "x"}]})
        body = json.loads(req.content)
        calls.append(body)
        last = body["messages"][-1]["content"]
        if "cut off by the length limit" in last:
            text, why = " deliverable.\n" + contract(status, open_questions=["What is your budget?"]), "stop"
        else:
            text, why = "A long deliverable that runs out of room mid", "length"
        return httpx2.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": body["model"],
                                          "choices": [{"index": 0, "finish_reason": why, "message": {"role": "assistant", "content": text}}],
                                          "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}})
    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def test_an_answer_cut_at_the_length_limit_is_continued_so_the_run_still_asks_for_input(tmp_path, monkeypatch):
    from tests.test_api import wait
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    calls: list = []
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), http_client=_length_then_rest_server(calls))) as c:
        c.post("/api/endpoints", json={"id": "lan", "name": "Box", "base_url": "http://10.0.0.7:1234", "model": "m1",
                                       "context_tokens": 128000, "use_for": ["router", "specialist", "synthesis", "review"]})
        rid = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "Open a pet spa franchise"}}).json()["id"]
        run = wait(c, rid)
        assert run["status"] == "awaiting_approval"  # paused for the person's answer, not marked PARTIAL
        step = c.get(f"/api/runs/{rid}").json()["steps"][0]
        assert step["status"] == "NEEDS_INPUT" and "What is your budget?" in json.dumps(c.get("/api/approvals").json())
        assert any("was continued 1 time" in w for w in step["warnings"])
        assert not any("contract repair failed" in w for w in step["warnings"])


def test_nothing_is_cut_by_default_and_the_next_model_that_fits_is_used():
    from app.prompts import PromptTooLarge, fit_or_refuse
    system = [("rules", "R" * 300, 0), ("agent", "A" * 30_000, 1), ("persona", "P" * 3_000, 6)]
    user = [("message", "M" * 300, 0)]
    whole = fit_or_refuse(system, user, ref="big", context_tokens=128_000, share=0.75, out_tokens=8192, tool_tokens=0,
                          shorten=False, chat=True)
    assert not whole.cuts and "A" * 30_000 in whole.system and "P" * 3_000 in whole.system
    # Over the share but within the whole window: still sent whole.
    near = fit_or_refuse(system, user, ref="mid", context_tokens=20_000, share=0.5, out_tokens=4000, tool_tokens=0,
                         shorten=False, chat=True)
    assert not near.cuts and "A" * 30_000 in near.system
    try:
        fit_or_refuse(system, user, ref="phone", context_tokens=4096, share=0.75, out_tokens=1024, tool_tokens=500,
                      shorten=False, chat=True)
        raise AssertionError("expected PromptTooLarge")
    except PromptTooLarge as e:
        assert "phone cannot take the whole prompt without cutting it" in str(e) and "4,096" in str(e)
