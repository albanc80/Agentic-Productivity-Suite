"""Anthropic Messages API via the official SDK.

* The system prompt is sent as a cached block (stable suite rules + agent
  instructions come first, so repeated steps reuse the cache).
* Thinking is left at the model default (adaptive on current models); depth is
  controlled with ``output_config.effort`` when the model config sets one.
* On models that support it, server-side refusal fallbacks are enabled
  (``fallbacks="default"``); a final ``refusal`` stop raises ProviderRefusal so
  the router can try the next model in the tier.
"""

from __future__ import annotations

import anthropic

from .base import ChatResult, Conversation, ProviderError, ProviderRefusal, Timer, ToolCall, ToolSpec, Usage

# Models that accept the scalar `fallbacks: "default"` form on the Claude API.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    def __init__(self, name: str, *, api_key: str, timeout_s: float, max_retries: int,
                 refusal_fallback: bool = True, base_url: str | None = None, http_client=None):
        self.name = name
        self.refusal_fallback = refusal_fallback
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s, max_retries=max_retries,
                                               base_url=base_url, http_client=http_client)

    def start(self, system: str, user: str) -> Conversation:
        return Conversation(system=system, messages=[{"role": "user", "content": user}])

    async def chat(self, conv: Conversation, *, model: str, tools: list[ToolSpec] | None,
                   max_tokens: int, effort: str | None = None) -> ChatResult:
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": conv.system, "cache_control": {"type": "ephemeral"}}],
            "messages": conv.messages,
        }
        if tools:
            kwargs["tools"] = [{"name": t.name, "description": t.description[:1024], "input_schema": t.parameters}
                               for t in tools]
        if effort:
            kwargs["output_config"] = {"effort": effort}
        use_fallback = self.refusal_fallback and model in FALLBACK_MODELS
        try:
            with Timer() as tm:
                if use_fallback:
                    resp = await self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
                else:
                    resp = await self.client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            raise ProviderError(f"{self.name}: HTTP {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ProviderError(f"{self.name}: connection error ({e})") from e
        except anthropic.AnthropicError as e:
            raise ProviderError(f"{self.name}: {e}") from e

        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            cat = getattr(details, "category", None) if details else None
            raise ProviderRefusal(f"{self.name}/{model} declined the request (category: {cat or 'unspecified'})")

        text = "\n".join(b.text for b in resp.content if b.type == "text")
        calls = [ToolCall(id=b.id, name=b.name, arguments=b.input if isinstance(b.input, dict) else {"value": b.input})
                 for b in resp.content if b.type == "tool_use"]
        u = resp.usage
        usage = Usage(input_tokens=(u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0),
                      output_tokens=u.output_tokens or 0,
                      cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0)
        native = {"role": "assistant",
                  "content": [b.model_dump(mode="json", exclude_none=True) for b in resp.content]}
        return ChatResult(text=text, tool_calls=calls, stop_reason=resp.stop_reason or "end_turn",
                          usage=usage, model=resp.model or model, latency_ms=tm.ms, native=native)

    def add_assistant(self, conv: Conversation, result: ChatResult) -> None:
        conv.messages.append(result.native)

    def add_tool_results(self, conv: Conversation, results: list[tuple[str, str, bool]]) -> None:
        # All results of one round go back in a single user message.
        conv.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": cid, "content": content, "is_error": is_error}
            for cid, content, is_error in results
        ]})

    def add_user(self, conv: Conversation, text: str) -> None:
        conv.messages.append({"role": "user", "content": text})
