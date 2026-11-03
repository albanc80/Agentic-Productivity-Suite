# ADR 0002: Provider-neutral model layer with tiered fallback chains

Status: accepted · 2026-11-03

## Context
Users want to mix local models (Ollama, LM Studio, vLLM) with OpenAI-compatible clouds (OpenAI, DeepSeek, OpenRouter) and Anthropic, sometimes inside one run. Data sensitivity varies per run, and the end user owns data clearance.

## Decision
- Two adapters: OpenAI-compatible chat completions (official `openai` SDK with a configurable `base_url`) and Anthropic Messages (official `anthropic` SDK). A demo provider runs without any model.
- Each provider keeps its native message format inside a `Conversation`, so tool rounds are appended correctly per provider.
- Steps request a tier. Tiers are ordered chains of `provider/model` refs; per-agent and per-step overrides are allowed.
- Candidates are filtered by availability (enabled, key present) and by the run's data class → allowed localities, before any call. Errors and refusals fall through to the next candidate.
- Model capability (context size, tool calling, price) is configuration, not code. Unknown models get conservative defaults.

## Consequences
- Swapping or adding a provider is a config change.
- Sensitive runs can be kept local, and the block is explicit when no local model is configured.
- Prompt caching applies on Anthropic: system prompt order is fixed. Other providers simply ignore it.
