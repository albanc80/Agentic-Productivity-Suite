# Production Code Patterns

Runnable, idiomatic templates for the components in the design workflow. Adapt names and providers to the project; keep the structure (typed I/O, validation, logging, error handling, tests). All examples are Python with type hints and Pydantic.

## Table of contents
1. Pydantic I/O models & validation
2. Structured-output extraction (OpenAI SDK)
3. Prompt scaffold
4. Function / tool calling
5. LangGraph workflow agent skeleton
6. LlamaIndex RAG skeleton
7. Multi-agent supervisor pattern
8. Memory wiring (Redis + Qdrant)
9. FastAPI service scaffold
10. Logging, error handling, retries
11. Testing patterns (pytest)

> Library APIs evolve. Treat these as structural templates and verify current method signatures against the installed version before shipping. Don't claim a capability a version doesn't have.

---

## 1. Pydantic I/O models & validation

```python
from enum import Enum
from pydantic import BaseModel, Field, field_validator

class TaskStatus(str, Enum):
    completed = "completed"
    needs_review = "needs_review"
    failed = "failed"

class AgentRequest(BaseModel):
    """Validated input contract."""
    query: str = Field(min_length=1, max_length=4000)
    user_id: str
    max_steps: int = Field(default=8, ge=1, le=25)

class Source(BaseModel):
    title: str
    url: str | None = None

class AgentResponse(BaseModel):
    """Validated output contract — the boundary downstream code trusts."""
    task: str
    status: TaskStatus
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    sources: list[Source] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def _round(cls, v: float) -> float:
        return round(v, 3)
```

Validation failures should be caught and handled (retry with the error fed back to the model, fall back, or escalate) — never silently passed downstream.

---

## 2. Structured-output extraction (OpenAI SDK)

```python
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)
client = OpenAI()  # API key from environment / secrets manager

def extract(req: AgentRequest) -> AgentResponse:
    """Force the model into the typed contract; parse + validate."""
    completion = client.beta.chat.completions.parse(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": req.query},
        ],
        response_format=AgentResponse,  # SDK validates against the Pydantic schema
    )
    result = completion.choices[0].message.parsed
    if result is None:
        raise ValueError("Model refused or returned unparseable output")
    logger.info("extracted task=%s status=%s", result.task, result.status)
    return result
```

The same idea applies with other providers via their structured-output / JSON-mode features. The principle is constant: never hand-parse free text when the SDK can enforce a schema.

---

## 3. Prompt scaffold

```python
SYSTEM_PROMPT = """\
<role>You are a research agent for upstream operations analysts.</role>

<objective>Answer the user's question with grounded, cited findings.</objective>

<constraints>
- Use only the provided tools for facts; never invent sources or IDs.
- If evidence is insufficient, set status to needs_review and say what's missing.
</constraints>

<rules>
- Every factual claim must map to a source in the sources list.
- Separate facts from assumptions in the summary.
</rules>

<tools>
- search(query): web/document search. Use for any external fact.
- read_file(path): read an internal document. Use when the user names a file.
</tools>

<output_format>
Return the AgentResponse schema. confidence reflects evidence strength.
</output_format>
"""
```

Each tag maps to a section from the prompt-engineering table. XML tags delimit cleanly and are easy for the model to attend to.

---

## 4. Function / tool calling

```python
import json

TOOLS = [{
    "type": "function",
    "function": {
        "name": "search",
        "description": "Search documents for facts. Use for any external claim.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}]

def run_tool(name: str, args: dict) -> str:
    if name == "search":
        return do_search(args["query"])   # your implementation
    raise ValueError(f"Unknown tool: {name}")

def agent_loop(req: AgentRequest) -> AgentResponse:
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": req.query}]
    for _ in range(req.max_steps):              # bound the loop
        resp = client.chat.completions.create(
            model="gpt-4.1", messages=messages, tools=TOOLS,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return _finalize(msg.content)
        messages.append(msg)
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = run_tool(call.function.name, args)
            messages.append({
                "role": "tool", "tool_call_id": call.id, "content": result,
            })
    return AgentResponse(task="unknown", status=TaskStatus.needs_review,
                         confidence=0.0, summary="Step budget exhausted.")
```

Prefer native function calling over parsing tool calls out of free text — it's validated and far more reliable.

---

## 5. LangGraph workflow agent skeleton

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class State(TypedDict):
    query: str
    plan: str
    findings: list[str]
    answer: str

def plan(s: State) -> dict: ...
def research(s: State) -> dict: ...
def synthesize(s: State) -> dict: ...

def needs_more(s: State) -> str:
    return "research" if len(s["findings"]) < 3 else "synthesize"

g = StateGraph(State)
g.add_node("plan", plan)
g.add_node("research", research)
g.add_node("synthesize", synthesize)
g.add_edge(START, "plan")
g.add_edge("plan", "research")
g.add_conditional_edges("research", needs_more,
                        {"research": "research", "synthesize": "synthesize"})
g.add_edge("synthesize", END)
app = g.compile()
```

LangGraph makes control flow an explicit, inspectable graph — the right tool when you need deterministic, debuggable workflow or multi-agent topologies.

---

## 6. LlamaIndex RAG skeleton

```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter

docs = SimpleDirectoryReader("./corpus").load_data()
nodes = SentenceSplitter(chunk_size=512, chunk_overlap=64).get_nodes_from_documents(docs)
index = VectorStoreIndex(nodes)                       # swap in Qdrant for production
engine = index.as_query_engine(similarity_top_k=5)

response = engine.query("…")
# response.source_nodes carries the citations — surface them in AgentResponse.sources
```

Always carry retrieved sources through to the output contract so claims are traceable.

---

## 7. Multi-agent supervisor pattern

```python
class Supervisor:
    """Owns control flow; routes to specialists; aggregates typed results."""
    def __init__(self, planner, researcher, coder, reviewer, reporter):
        self.planner, self.researcher = planner, researcher
        self.coder, self.reviewer, self.reporter = coder, reviewer, reporter

    def run(self, req: AgentRequest) -> AgentResponse:
        plan = self.planner.make_plan(req.query)
        findings = self.researcher.gather(plan)        # typed message in/out
        draft = self.coder.build(plan, findings)
        review = self.reviewer.check(draft)            # separation of concerns
        if not review.approved:
            draft = self.coder.revise(draft, review.feedback)
        return self.reporter.compose(draft, findings)  # -> AgentResponse
```

Sub-agents exchange typed messages, not raw prose. The supervisor is deterministic and the easiest topology to evaluate and debug.

---

## 8. Memory wiring (Redis short-term + Qdrant long-term)

```python
import json, redis
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

def remember_turn(session: str, role: str, content: str) -> None:
    r.rpush(f"chat:{session}", json.dumps({"role": role, "content": content}))
    r.expire(f"chat:{session}", 3600)                  # short-term TTL

def recent_turns(session: str, n: int = 20) -> list[dict]:
    return [json.loads(x) for x in r.lrange(f"chat:{session}", -n, -1)]

q = QdrantClient(url="http://localhost:6333")          # long-term / semantic

def store_memory(collection: str, vec: list[float], payload: dict, pid: int) -> None:
    q.upsert(collection, [PointStruct(id=pid, vector=vec, payload=payload)])

def recall(collection: str, vec: list[float], k: int = 5):
    return q.search(collection, query_vector=vec, limit=k)
```

Short-term in Redis with a TTL; durable/semantic in a vector store. Don't conflate the two.

---

## 9. FastAPI service scaffold

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Agent Service")

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.post("/v1/agent", response_model=AgentResponse)
def invoke(req: AgentRequest) -> AgentResponse:
    try:
        return agent_loop(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.exception("agent failed")
        raise HTTPException(status_code=500, detail="internal error")
```

Pydantic models double as request/response validation. Add auth, rate limiting, and tracing per `production-hardening.md`. Do not use HTML `<form>` semantics here — this is a JSON API.

---

## 10. Logging, error handling, retries

```python
import logging, time
from functools import wraps

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)

def retry(times: int = 3, base: float = 0.5):
    """Exponential backoff for transient LLM/tool/API errors."""
    def deco(fn):
        @wraps(fn)
        def wrap(*a, **k):
            for i in range(times):
                try:
                    return fn(*a, **k)
                except Exception as e:
                    if i == times - 1:
                        raise
                    logging.warning("retry %d after %s", i + 1, e)
                    time.sleep(base * (2 ** i))
        return wrap
    return deco
```

Structured (JSON) logs are queryable. Retry only transient failures; never silently swallow exceptions.

---

## 11. Testing patterns (pytest)

```python
import pytest

def test_output_contract_rejects_bad_confidence():
    with pytest.raises(Exception):
        AgentResponse(task="t", status=TaskStatus.completed,
                      confidence=1.5, summary="x")     # out of range

def test_tool_loop_is_bounded(monkeypatch):
    """Agent must stop at max_steps even if the model never finalizes."""
    monkeypatch.setattr("mymod.client", _always_calls_tool_stub())
    out = agent_loop(AgentRequest(query="q", user_id="u", max_steps=3))
    assert out.status == TaskStatus.needs_review

def test_validation_failure_does_not_crash_service(client):
    resp = client.post("/v1/agent", json={"query": "", "user_id": "u"})
    assert resp.status_code == 422
```

Test the contracts and the bounds (step/cost caps, validation failures), not just the happy path — those are where production agents actually break.
