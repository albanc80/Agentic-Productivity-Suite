"""Which connector tools a model is offered: all of them, each connector's core set, or on demand.

On demand, the model starts with one small tool, ``suite__find_tools``, and a line per connected source. It asks for
what it needs ("search mail", "calendar this week"), the matching tools are loaded for the rest of the answer, and it
calls them as usual. Tool definitions were most of every prompt (about 55,000 tokens for Microsoft 365, Google
Workspace and GitHub, even compacted), so this keeps the room for instructions, history and reasoning.

Matching is deterministic (words in the request against tool names and descriptions), so it is cheap, repeatable and
auditable. Read-only is unaffected: only allowed tools are ever listed, and calls still go through the connector
manager's checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .providers import ToolSpec

ToolMode = Literal["core", "all", "on_demand"]
TOOL_MODES: tuple[str, ...] = ("core", "all", "on_demand")
FIND_TOOL = "suite__find_tools"
FIND_LIMIT = 8  # tools loaded per search
LOAD_LIMIT = 40  # tools loaded in one answer at most
ON_DEMAND_RESERVE = 8_000  # tokens kept for tools loaded during an answer (about 16 compact tools)

FIND_SPEC = ToolSpec(
    FIND_TOOL,
    "Load the connector tools you need, then call them. Describe the task in a few words (e.g. 'search mail', "
    "'calendar events this week', 'read a OneDrive file', 'open pull requests'); optionally name the source. "
    "Returns the tools now available to you. Search again for a different task.",
    {"type": "object", "properties": {
        "query": {"type": "string", "description": "What you need to do, in a few words."},
        "connector": {"type": "string", "description": "Optional: only this connected source (its name or id)."},
        "names": {"type": "array", "items": {"type": "string"}, "description": "Optional: exact tool names to load."}},
     "required": ["query"]})

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(("a an and the to of in on for my me i with from by at is are be this that it all any get list open show "
                   "find please about week today tomorrow yesterday latest recent new some").split())
# Plain words people use, mapped to the words tool names use.
_SYNONYMS = {"email": "mail", "emails": "mail", "inbox": "mail", "message": "mail", "messages": "mail",
             "meeting": "calendar", "meetings": "calendar", "event": "calendar", "events": "calendar",
             "schedule": "calendar", "file": "drive", "files": "drive", "document": "drive", "documents": "drive",
             "doc": "docs", "folder": "folder", "task": "todo", "tasks": "todo", "todos": "todo", "pr": "pull",
             "prs": "pull", "issue": "issues", "ticket": "issues", "tickets": "issues", "repo": "repository",
             "repos": "repository", "contact": "contacts", "people": "contacts", "sheet": "sheets",
             "spreadsheet": "sheets", "excel": "excel", "notes": "onenote", "note": "onenote"}


# Subjects: when a request names one, only tools about that subject match (no commit search for "mail").
_TOPICS = frozenset(set(_SYNONYMS.values()) | {"gmail", "outlook", "onedrive", "commit", "branch", "release", "workflow",
                                               "teams", "sharepoint", "slides", "presentation", "notebook", "page"})
# Specialised variants rank below the everyday tool with the same subject.
_NICHE = ("delta", "mime", "thumbnail", "permission", "version", "tips", "override", "rules", "linked", "format")


def _words(text: str, synonyms: bool = True) -> set[str]:
    """Words of a request or tool name. Synonyms are for requests and names only: a description saying "commit
    message" must not make a commit tool a mail tool."""
    out = set()
    for w in _WORD.findall(text.lower()):
        if w in _STOP:
            continue
        out.add(w)
        if synonyms and w in _SYNONYMS:
            out.add(_SYNONYMS[w])
        if w.endswith("s") and len(w) > 3:
            out.add(w[:-1])
    return out


@dataclass
class ToolMenu:
    """The tools for one answer. ``connector_of`` maps a tool's qualified name to its connector id; tools missing from
    it (calculators, the skill reader) are not connector tools and are always offered."""

    tools: list[ToolSpec]
    connector_of: dict[str, str]
    mode: str = "core"
    names: dict[str, str] = field(default_factory=dict)  # connector id -> display name
    loaded: dict[str, ToolSpec] = field(default_factory=dict)
    searches: int = 0

    @property
    def deferred(self) -> bool:
        return self.mode == "on_demand" and any(t.name in self.connector_of for t in self.tools)

    def offered(self) -> list[ToolSpec]:
        if not self.deferred:
            return self.tools
        always = [t for t in self.tools if t.name not in self.connector_of]
        return [*always, FIND_SPEC, *self.loaded.values()]

    def note(self) -> str:
        """What the agent is told when tools load on demand."""
        if not self.deferred:
            return ""
        counts: dict[str, int] = {}
        for t in self.tools:
            cid = self.connector_of.get(t.name)
            if cid:
                counts[cid] = counts.get(cid, 0) + 1
        sources = ", ".join(f"{self.names.get(c, c)} ({n} tools)" for c, n in counts.items())
        return (f"- Connector tools load on demand: call `{FIND_TOOL}` with what you need, then call the tools it "
                f"returns. Connected: {sources}.\n")

    def find(self, arguments: dict) -> str:
        """Load the best matches for a request; return what is now available, as text for the model."""
        self.searches += 1
        pool = [t for t in self.tools if t.name in self.connector_of]
        want = str(arguments.get("connector") or "").strip().lower()
        if want:
            pool = [t for t in pool if want in self.connector_of[t.name].lower()
                    or want in self.names.get(self.connector_of[t.name], "").lower()] or pool
        exact = {str(n) for n in arguments.get("names") or []}
        picked = [t for t in pool if t.name in exact or t.name.split("__", 1)[-1] in exact]
        q = _words(str(arguments.get("query") or ""))
        if q:
            subjects = q & _TOPICS
            scored = []
            for t in pool:
                if t in picked:
                    continue
                name_words = _words(t.name.split("__", 1)[-1].replace("-", " ").replace("_", " "))
                desc_words = _words(t.description.split("] ", 1)[-1][:300], synonyms=False)
                if subjects and not subjects & (name_words | desc_words):
                    continue
                score = 3 * len(q & name_words) + len(q & desc_words) + 2 * len(subjects & name_words)
                score -= 2 * sum(n in t.name for n in _NICHE)
                if score > 0:
                    scored.append((score, -len(t.name), t))
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            picked += [t for _s, _l, t in scored[:FIND_LIMIT]]
        new = [t for t in picked if t.name not in self.loaded][: max(0, LOAD_LIMIT - len(self.loaded))]
        for t in new:
            self.loaded[t.name] = t
        if not picked:
            return ("No connector tool matched. Try other words (for example 'mail', 'calendar', 'files', 'issues'), "
                    "or name the source.")
        lines = [f"- {t.name}: {t.description.split('] ', 1)[-1][:160]}" for t in picked]
        more = "" if len(self.loaded) < LOAD_LIMIT else " (the most tools one answer may load is reached)"
        return "These tools are available now; call them directly" + more + ":\n" + "\n".join(lines)
