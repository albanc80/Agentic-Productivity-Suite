"""OpenAI-compatible chat completions: OpenAI, DeepSeek, OpenRouter, Ollama, LM Studio, vLLM.

All of these expose ``POST {base_url}/chat/completions``; only ``base_url``,
the API key and optional headers differ.
"""

from __future__ import annotations

import json

import openai

from ..contracts import strip_reasoning
from .base import ChatResult, Conversation, ProviderError, Timer, ToolCall, ToolSpec, Usage


class OpenAICompatibleProvider:
    def __init__(self, name: str, *, base_url: str, api_key: str, timeout_s: float, max_retries: int,
                 headers: dict[str, str] | None = None, http_client=None):
        self.name = name
        self.client = openai.AsyncOpenAI(
            base_url=base_url, api_key=api_key or "not-needed", timeout=timeout_s,
            max_retries=max_retries, default_headers=headers or None, http_client=http_client,
        )

    def start(self, system: str, user: str) -> Conversation:
        return Conversation(system=system, messages=[{"role": "system", "content": system},
                                                     {"role": "user", "content": user}])

    async def chat(self, conv: Conversation, *, model: str, tools: list[ToolSpec] | None,
                   max_tokens: int, effort: str | None = None) -> ChatResult:
        kwargs: dict = {"model": model, "messages": conv.messages, "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description[:1024],
                                                  "parameters": t.parameters}}
                for t in tools
            ]
        try:
            with Timer() as tm:
                resp = await self.client.chat.completions.create(**kwargs)
        except openai.APIStatusError as e:
            raise ProviderError(f"{self.name}: HTTP {e.status_code}: {e.message}") from e
        except openai.APIConnectionError as e:
            raise ProviderError(f"{self.name}: cannot reach {self.client.base_url} ({e})") from e
        except openai.OpenAIError as e:
            raise ProviderError(f"{self.name}: {e}") from e
        if not resp.choices:
            raise ProviderError(f"{self.name}: empty response")
        choice = resp.choices[0]
        msg = choice.message
        calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            raw = tc.function.arguments or "{}"
            try:
                args = json.loads(raw)
                if not isinstance(args, dict):
                    args = {"value": args}
            except json.JSONDecodeError:
                args = {"_invalid_json": raw}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args, raw_arguments=raw))
        usage = Usage(
            input_tokens=getattr(resp.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "completion_tokens", 0) or 0,
        )
        native = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            native["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.raw_arguments}}
                for c in calls
            ]
        return ChatResult(text=strip_reasoning(msg.content or ""), tool_calls=calls,
                          stop_reason=choice.finish_reason or "stop", usage=usage,
                          model=resp.model or model, latency_ms=tm.ms, native=native)

    def add_assistant(self, conv: Conversation, result: ChatResult) -> None:
        conv.messages.append(result.native)

    def add_tool_results(self, conv: Conversation, results: list[tuple[str, str, bool]]) -> None:
        for call_id, content, is_error in results:
            conv.messages.append({"role": "tool", "tool_call_id": call_id,
                                  "content": ("ERROR: " if is_error else "") + content})

    def add_user(self, conv: Conversation, text: str) -> None:
        conv.messages.append({"role": "user", "content": text})
