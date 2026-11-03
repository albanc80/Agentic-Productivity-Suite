"""Demo provider: deterministic, offline, no model.

Lets the suite run end to end without any model configured (first run, UI
demos, CI). Every output is labelled as demo content and the run is flagged,
so nobody mistakes it for analysis.
"""

from __future__ import annotations

import json
import re

from .base import ChatResult, Conversation, ToolSpec, Usage

DEMO_BANNER = "> **Demo output.** No language model produced this text. Configure a provider in Settings to get real analysis."


class MockProvider:
    name = "mock"

    def start(self, system: str, user: str) -> Conversation:
        return Conversation(system=system, messages=[{"role": "user", "content": user}])

    async def chat(self, conv: Conversation, *, model: str, tools: list[ToolSpec] | None,
                   max_tokens: int, effort: str | None = None) -> ChatResult:
        user = next((m["content"] for m in reversed(conv.messages) if m.get("role") == "user"
                     and isinstance(m.get("content"), str)), "")
        if "ROUTER_TASK" in conv.system:
            text = self._route(conv.system, user)
        elif "Return only the JSON handoff block" in user:
            text = "```json\n" + json.dumps({"status": "PARTIAL", "summary": "Demo repair."}) + "\n```"
        else:
            text = self._deliverable(conv.system, user)
        n_in = (len(conv.system) + sum(len(str(m.get("content", ""))) for m in conv.messages)) // 4
        return ChatResult(text=text, tool_calls=[], stop_reason="stop",
                          usage=Usage(input_tokens=n_in, output_tokens=len(text) // 4),
                          model="mock", latency_ms=1, native={"role": "assistant", "content": text})

    def add_assistant(self, conv: Conversation, result: ChatResult) -> None:
        conv.messages.append(result.native)

    def add_tool_results(self, conv: Conversation, results) -> None:
        for cid, content, _ in results:
            conv.messages.append({"role": "tool", "tool_call_id": cid, "content": content})

    def add_user(self, conv: Conversation, text: str) -> None:
        conv.messages.append({"role": "user", "content": text})

    # ------------------------------------------------------------------ #

    @staticmethod
    def _route(system: str, user: str) -> str:
        # Keyword overlap between the request and each playbook's trigger list.
        words = set(re.findall(r"[a-z]+", user.lower()))
        best, best_score = None, 0
        for m in re.finditer(r"^- (\S+): .*?\[triggers: (.*?)\]$", system, re.M):
            pid, triggers = m.group(1), [t.strip().lower() for t in m.group(2).split(",")]
            score = sum(1 for t in triggers if set(t.split()) <= words)
            if score > best_score:
                best, best_score = pid, score
        conf = min(0.4 + 0.2 * best_score, 0.95) if best else 0.2
        return json.dumps({"playbook": best or "quick-ask", "confidence": conf, "reason": "demo keyword match"})

    @staticmethod
    def _deliverable(system: str, user: str) -> str:
        agent = re.search(r"^You are acting as: (.+)$", system, re.M)
        task = re.search(r"^## Your task\n(.+?)(?:\n\n|\Z)", user, re.S | re.M)
        review = "VERDICT_REQUIRED" in user
        name = agent.group(1) if agent else "Agent"
        task_text = (task.group(1).strip() if task else "the requested task")[:400]
        body = (
            f"{DEMO_BANNER}\n\n### {name}\n\n"
            f"**Task:** {task_text}\n\n"
            "- This section shows where the agent's analysis will appear.\n"
            "- The inputs and prior steps were received and are listed in the run timeline.\n"
        )
        contract = {
            "status": "PARTIAL",
            "summary": f"Demo output from {name}; no model was called.",
            "claims": [{"text": "No analysis was performed in demo mode.", "label": "FACT", "trace": "provider:mock"}],
            "risks": [{"risk": "Demo content could be mistaken for analysis.", "severity": "low",
                       "mitigation": "Configure a model provider."}],
            "open_questions": [],
            "next_action": {"action": "Configure a model provider and re-run.", "owner": "user", "gate": ""},
            "skills_invoked": [],
            "evidence": "NOT_EXECUTED",
            "verdict": "PASS_WITH_CHANGES" if review else None,
            "findings": ["Demo review: no findings generated."] if review else [],
        }
        return body + "\n```json\n" + json.dumps(contract, indent=2) + "\n```"
