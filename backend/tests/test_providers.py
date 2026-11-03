"""Adapters against mocked HTTP: request shapes, tool calls, errors and refusals."""

import json

import httpx2
import pytest

from app.providers import ModelRouter
from app.providers.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.providers.base import ProviderError, ProviderRefusal, ToolSpec
from app.providers.openai_compat import OpenAICompatibleProvider
from app.settings import ModelConfig, ProviderConfig, Settings

TOOL = ToolSpec("github__get_issue", "Get an issue", {"type": "object", "properties": {"key": {"type": "string"}}})


def transport(handler):
    seen = []

    def wrapped(req):
        seen.append({"url": str(req.url), "headers": dict(req.headers), "body": json.loads(req.content or b"{}")})
        return handler(req)
    return httpx2.AsyncClient(transport=httpx2.MockTransport(wrapped)), seen


def anthropic_reply(content, stop="end_turn"):
    return httpx2.Response(200, json={"id": "m", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                                      "content": content, "stop_reason": stop, "stop_sequence": None,
                                      "usage": {"input_tokens": 20, "output_tokens": 5, "cache_read_input_tokens": 7}})


async def test_anthropic_request_shape_tools_and_fallback():
    client, seen = transport(lambda r: anthropic_reply([
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "tool_use", "id": "tu1", "name": "github__get_issue", "input": {"key": "A-1"}}], stop="tool_use"))
    p = AnthropicProvider("anthropic", api_key="k", timeout_s=10, max_retries=0, http_client=client)
    conv = p.start("SYSTEM", "hello")
    r = await p.chat(conv, model="claude-opus-5-5", tools=[TOOL], max_tokens=1000, effort="medium")
    body, headers = seen[0]["body"], seen[0]["headers"]
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["fallbacks"] == "default" and FALLBACK_BETA in headers["anthropic-beta"]
    assert body["output_config"] == {"effort": "medium"} and body["tools"][0]["input_schema"]["type"] == "object"
    assert "thinking" not in body
    assert r.tool_calls[0].name == "github__get_issue" and r.usage.cache_read_tokens == 7
    p.add_assistant(conv, r)
    p.add_tool_results(conv, [("tu1", "<data>..</data>", False)])
    assert conv.messages[-2]["content"][0]["type"] == "thinking"  # thinking blocks are passed back unchanged
    assert conv.messages[-1]["content"][0] == {"type": "tool_result", "tool_use_id": "tu1", "content": "<data>..</data>", "is_error": False}


async def test_anthropic_no_fallback_on_haiku_and_refusal_raises():
    client, seen = transport(lambda r: anthropic_reply([], stop="refusal"))
    p = AnthropicProvider("anthropic", api_key="k", timeout_s=10, max_retries=0, http_client=client)
    with pytest.raises(ProviderRefusal):
        await p.chat(p.start("s", "u"), model="claude-haiku-5-5", tools=None, max_tokens=100)
    assert "fallbacks" not in seen[0]["body"]


async def test_anthropic_http_error_maps_to_provider_error():
    client, _ = transport(lambda r: httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "bad key"}}))
    p = AnthropicProvider("anthropic", api_key="k", timeout_s=10, max_retries=0, http_client=client)
    with pytest.raises(ProviderError, match="401"):
        await p.chat(p.start("s", "u"), model="claude-sonnet-5-5", tools=None, max_tokens=100)


async def test_openai_compatible_tool_calls_and_reasoning_strip():
    replies = iter([
        {"choices": [{"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "github__get_issue", "arguments": "{\"key\": \"A-1\"}"}}]}}]},
        {"choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "<think>internal</think>Final"}}]},
    ])
    client, seen = transport(lambda r: httpx2.Response(200, json={"id": "x", "object": "chat.completion", "created": 0,
                                                                  "model": "qwen2.5:14b", **next(replies),
                                                                  "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}))
    p = OpenAICompatibleProvider("ollama", base_url="http://localhost:11434/v1", api_key="ollama", timeout_s=10,
                                 max_retries=0, http_client=client)
    conv = p.start("SYS", "hi")
    r = await p.chat(conv, model="qwen2.5:14b", tools=[TOOL], max_tokens=100)
    assert seen[0]["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen[0]["body"]["messages"][0] == {"role": "system", "content": "SYS"}
    assert r.tool_calls[0].arguments == {"key": "A-1"}
    p.add_assistant(conv, r)
    p.add_tool_results(conv, [("c1", "result", False)])
    r2 = await p.chat(conv, model="qwen2.5:14b", tools=None, max_tokens=100)
    assert seen[1]["body"]["messages"][-1] == {"role": "tool", "tool_call_id": "c1", "content": "result"}
    assert "tools" not in seen[1]["body"] and r2.text == "Final"


async def test_openai_compatible_connection_error():
    def boom(req):
        raise httpx2.ConnectError("refused", request=req)
    client, _ = transport(boom)
    p = OpenAICompatibleProvider("lmstudio", base_url="http://localhost:1234/v1", api_key="x", timeout_s=5,
                                 max_retries=0, http_client=client)
    with pytest.raises(ProviderError, match="cannot reach"):
        await p.chat(p.start("s", "u"), model="m", tools=None, max_tokens=10)


def test_router_availability_and_locality(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    s = Settings(home=tmp_path, data_dir=tmp_path, allow_demo_provider=True, providers={
        "ollama": ProviderConfig(type="openai_compatible", locality="local", base_url="http://l/v1", api_key="o", enabled=False),
        "openrouter": ProviderConfig(type="openai_compatible", locality="cloud", base_url="http://r/v1", api_key_env="OPENROUTER_API_KEY"),
        "anthropic": ProviderConfig(type="anthropic", locality="cloud", api_key="sk-test"),
        "demo": ProviderConfig(type="mock", locality="local")},
        models=[ModelConfig(ref="anthropic/claude-sonnet-5-5", tools=True)],
        tiers={"specialist": ["ollama/x", "openrouter/vendor/model", "anthropic/claude-sonnet-5-5", "demo/demo"]})
    r = ModelRouter(s)
    cands, skipped = r.candidates("specialist", "internal")
    assert [c.ref for c in cands] == ["anthropic/claude-sonnet-5-5", "demo/demo"]
    assert any("disabled" in x for x in skipped) and any("OPENROUTER_API_KEY" in x for x in skipped)
    cands, skipped = r.candidates("specialist", "restricted")
    assert [c.ref for c in cands] == ["demo/demo"] and any("not allowed for 'restricted'" in x for x in skipped)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    cands, _ = r.candidates("specialist", "internal")
    assert cands[0].ref == "openrouter/vendor/model" and cands[0].model.model == "vendor/model"
    assert r.settings.model("ollama/unknown").context_tokens == 8192  # conservative default for local
