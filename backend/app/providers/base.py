"""Provider-neutral chat interface.

Each provider keeps its own native message list inside a ``Conversation`` so
tool-call rounds can be appended in the provider's own format (OpenAI-style
``tool`` messages vs Anthropic ``tool_result`` blocks) without the engine
knowing the difference.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    def __iadd__(self, other: Usage) -> Usage:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        return self


@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    usage: Usage
    model: str
    latency_ms: int
    native: Any = None  # provider-native assistant message to append


@dataclass
class Conversation:
    system: str
    messages: list[Any] = field(default_factory=list)


class ProviderError(Exception):
    """Transport, auth or API error. The router may fall back to the next model."""


class ProviderRefusal(ProviderError):
    """The model declined the request on policy grounds."""


class Provider(Protocol):
    name: str

    def start(self, system: str, user: str) -> Conversation: ...

    async def chat(self, conv: Conversation, *, model: str, tools: list[ToolSpec] | None,
                   max_tokens: int, effort: str | None = None) -> ChatResult: ...

    def add_assistant(self, conv: Conversation, result: ChatResult) -> None: ...

    def add_tool_results(self, conv: Conversation, results: list[tuple[str, str, bool]]) -> None:
        """results: (tool_call_id, content, is_error)."""

    def add_user(self, conv: Conversation, text: str) -> None: ...


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = int((time.perf_counter() - self.t0) * 1000)


# ---------------------------------------------------------------- replies cut off by the answer length

LENGTH_STOPS = frozenset({"length", "max_tokens"})  # OpenAI-compatible finish_reason / Anthropic stop_reason
MAX_CONTINUATIONS = 3
CONTINUE_PROMPT = ("Your reply was cut off by the length limit. Continue exactly where you stopped: no repetition, "
                   "no preamble, and finish with everything the response format asks for.")


async def complete_reply(provider, conv, result: ChatResult, *, model: str, max_tokens: int, effort: str | None,
                         on_usage=None) -> tuple[ChatResult, int, bool]:
    """A final reply that stopped at the answer length is continued (up to MAX_CONTINUATIONS times) and the parts are
    joined, so nothing is cut. Returns (joined reply, continuations made, still cut off)."""
    import dataclasses
    texts, n = [result.text], 0
    while result.stop_reason in LENGTH_STOPS and not result.tool_calls and n < MAX_CONTINUATIONS:
        provider.add_assistant(conv, result)
        provider.add_user(conv, CONTINUE_PROMPT)
        result = await provider.chat(conv, model=model, tools=None, max_tokens=max_tokens, effort=effort)
        if on_usage:
            on_usage(result.usage)
        texts.append(result.text)
        n += 1
    return dataclasses.replace(result, text="".join(texts)), n, result.stop_reason in LENGTH_STOPS
