# Agent Design Workflow (expanded)

The ten-stage workflow from SKILL.md, expanded with decision criteria, ASCII diagrams, and the reasoning behind each design choice. Read top-to-bottom for teaching; jump to a stage for a build/review task.

## Table of contents
1. Problem definition & agent-type selection
2. Input & output design
3. Prompt & protocol engineering
4. Reasoning & tool usage
5. Multi-agent architecture
6. Memory systems
7. Multimodal
8. Output design
9. (Deployment — see `production-hardening.md`)
10. (Evaluation — see `production-hardening.md`)

---

## 1. Problem definition & agent-type selection

Never start with code. Start with five questions:

- **What problem are we solving?** (the job to be done, not the feature)
- **Who are the users?** (skill level, trust requirements, volume)
- **What is the desired outcome?** (a decision, a document, an action taken in a system)
- **What tasks should be automated?** (and which stay human)
- **What failure cost do we accept?** (this sets how much guardrailing and eval you need)

### Agent-type decision tree

```
Is there a fixed, known sequence of steps?
├─ YES → does any step need an LLM judgment call?
│        ├─ NO  → it's a SCRIPT/PIPELINE, not an agent. Don't add an LLM.
│        └─ YES → WORKFLOW AGENT (deterministic graph, LLM at specific nodes)
└─ NO  → does the task need the model to choose its own steps/tools at runtime?
         ├─ NO, just Q&A over content → CHATBOT / RAG ASSISTANT
         └─ YES → can one agent hold all the tools + context reliably?
                  ├─ YES → SINGLE TOOL-USING (AUTONOMOUS) AGENT
                  └─ NO  → MULTI-AGENT SYSTEM (specialized roles + supervisor)
```

**Bias toward the simplest option that works.** Autonomous and multi-agent systems are harder to evaluate, debug, and cost-control. Earn the complexity. The most common engineering mistake is reaching for a multi-agent swarm when a workflow agent with three tools would be more reliable and one-tenth the cost.

### Output of this stage
A short spec: problem, users, outcome, automated tasks, chosen agent type (with the one-line reason), and the accepted failure cost. Everything downstream references this.

---

## 2. Input & output design

Design the data contract **before** the logic. This is the single highest-leverage reliability decision in agent engineering.

```
User request
   ↓
[Pydantic model: validated input]
   ↓
   LLM
   ↓
[Pydantic model: validated output]  ← structured, not free text
   ↓
Application / downstream system
```

**Why structured outputs beat free-form text:**
- **Determinism at the boundary.** Downstream code consumes typed fields, not regex over prose.
- **Validation catches model errors early.** A confidence score out of range or a missing required field fails loudly instead of silently corrupting a pipeline.
- **Cheaper to evaluate.** You assert on fields, not fuzzy-match paragraphs.
- **Composable.** One agent's typed output is the next agent's typed input.

Default to structured outputs. Reserve free text only for the human-readable layer (see Stage 8), and even then pair it with JSON.

Define for every agent: input schema, output schema, validation rules (ranges, enums, required fields, cross-field constraints), and what happens on validation failure (retry with the error fed back, fall back, or escalate to a human). Code templates in `code-patterns.md`.

---

## 3. Prompt & protocol engineering

A production prompt is a contract, not a wish. Include every section explicitly:

| Section | Why it exists |
|---|---|
| **Role** | Sets capability framing and vocabulary the model draws on. |
| **Context** | The task-specific facts; reduces hallucination by grounding. |
| **Objective** | The single outcome; prevents drift. |
| **Constraints** | Hard limits (length, scope, what *not* to do). |
| **Rules** | Behavioral guarantees (cite sources, never fabricate IDs). |
| **Available tools** | What the agent may call, with when-to-use guidance. |
| **Examples** | Few-shot anchors for format and judgment (the strongest lever for consistency). |
| **Expected output format** | The schema/contract the response must satisfy. |

**Format choice:** XML-style tags delimit sections cleanly and are easy for the model to attend to; Markdown is readable; JSON is best when the *output* must be machine-parsed. Pick per use case and be consistent.

**Patterns:**
- **ReAct** (reason → act → observe → repeat) for tool-using agents that must plan adaptively.
- **Tool/function calling** for structured, validated tool invocation (preferred over parsing free text for tool calls).
- **MCP-compatible design** when tools should be portable across hosts/clients rather than hard-wired.
- Encourage step-by-step reasoning for the model's benefit, but do **not** design systems that depend on exposing hidden chain-of-thought to users — surface a clean rationale instead.

Explain each section's purpose when teaching; a prompt nobody understands is a prompt nobody can debug.

---

## 4. Reasoning & tool usage

Tools are how an agent affects the world and gets fresh, grounded facts. The engineering work is in **tool selection** and **failure handling**, not in having many tools.

Common tools: search, REST APIs, databases, sandboxed Python execution, web browsing, retrieval, file reading, code generation, SQL, email, calendar, CRM.

**Design rules:**
- **Describe tools for the model, not for humans.** The tool's name + description + parameter docs are the model's only basis for choosing it. Vague descriptions cause wrong-tool errors.
- **One tool, one job.** Narrow, composable tools beat a "do-everything" tool with a mode flag.
- **Validate tool inputs and outputs** with the same rigor as agent I/O.
- **Plan → act → reflect.** After a tool result, let the agent check whether the result actually advances the objective (reflection) and self-correct (retry, switch tool, or escalate) rather than barreling forward.
- **Bound the loop.** Cap tool-call iterations and total cost per task so a confused agent can't spiral.

```
        ┌─────────────┐
        │   Plan      │  what's the next step toward the objective?
        └──────┬──────┘
               ↓
        ┌─────────────┐
        │  Select +   │  choose tool from descriptions; validate args
        │  call tool  │
        └──────┬──────┘
               ↓
        ┌─────────────┐
        │  Observe +  │  did this advance the goal? error? retry/switch/stop
        │  reflect    │
        └──────┬──────┘
               ↓   (loop, bounded by max steps / max cost)
        ┌─────────────┐
        │  Finalize   │  validated structured output
        └─────────────┘
```

---

## 5. Multi-agent architecture

Reach for this only when a single agent genuinely can't hold the job reliably — typically when the task spans distinct skill domains, needs separation of concerns for review/safety, or has parallelizable subtasks.

```
            ┌──────────────┐
            │  Supervisor  │  decomposes, routes, aggregates
            └──────┬───────┘
        ┌──────────┼───────────┬──────────────┐
        ↓          ↓           ↓              ↓
   ┌─────────┐ ┌────────┐ ┌─────────┐   ┌──────────┐
   │ Planner │ │Research│ │  Code   │   │ Reviewer │
   └─────────┘ └────────┘ └─────────┘   └──────────┘
                                              ↓
                                        ┌──────────┐
                                        │ Reporter │
                                        └──────────┘
```

**Coordination concerns:**
- **Communication** — typed messages between agents (reuse your Pydantic contracts; don't pass raw prose).
- **Task delegation** — supervisor assigns and tracks subtasks; each sub-agent has a narrow charter.
- **Shared memory** — a common store (state object, vector DB, or scratchpad) so agents don't re-derive context.
- **Supervisor pattern** — one orchestrator owns control flow; deterministic and debuggable. Prefer this.
- **Swarm pattern** — peer agents hand off to each other without a central controller; flexible but harder to evaluate and bound. Use only with strong guardrails.

**Trade-off to state every time:** multi-agent buys modularity and specialization at the cost of latency, token spend, and far harder evaluation/observability. LangGraph models these topologies as explicit graphs, which keeps control flow inspectable — see `code-patterns.md`.

---

## 6. Memory systems

Match the memory type to the need; don't bolt a vector DB onto everything.

| Type | Holds | Typical tech | Use when |
|---|---|---|---|
| **Short-term** | Current conversation/context | In-process state, Redis | Every multi-turn agent |
| **Long-term** | Durable knowledge across sessions | Qdrant, Pinecone, Weaviate, Chroma, FAISS | Agent must recall prior facts/sessions |
| **Semantic** | Retrievable knowledge base | Vector DB + embeddings | RAG / grounding over documents |
| **Episodic** | Records of past interactions/outcomes | Vector DB or relational | Learning from prior runs, personalization |
| **Working** | Current task state / scratchpad | State object, Redis | Multi-step plans, tool loops |

**Vector store selection (quick guidance):**
- **FAISS** — in-process, no server, fastest to prototype; you manage persistence yourself.
- **Chroma** — lightweight, local-first, good DX for small/medium apps.
- **Qdrant** — open-source, production-grade filtering and payloads, self-host or managed; strong default for enterprise on-prem/Azure.
- **Pinecone / Weaviate** — managed/scalable; pick for large or multi-tenant workloads where you don't want to run the store.

State the trade-off: managed services reduce ops at the cost of data residency and lock-in — relevant when data must stay inside an enterprise boundary. Memory wiring code is in `code-patterns.md`.

---

## 7. Multimodal

Add only the modalities the use case needs. Integration pattern: a perception step converts non-text input into something the agent can reason over, then the normal tool/agent loop proceeds.

- **Images** → vision model for understanding/extraction.
- **PDFs** → layout-aware extraction (text + tables + figures), then chunk for retrieval.
- **Audio** → speech-to-text in; text-to-speech out.
- **Video** → frame sampling + vision; transcript via STT.
- **OCR** → for scanned/handwritten documents before extraction.

Treat each as a tool with validated output (e.g., OCR returns typed fields, not a wall of text). Keep the agent's reasoning core text-based and well-structured; multimodal lives at the edges.

---

## 8. Output design

Always return **both**:

1. A **human-readable report** — what a person reads to trust and act on the result.
2. **Structured JSON** — what downstream systems consume.

```json
{
  "task": "Research",
  "status": "Completed",
  "confidence": 0.94,
  "sources": [],
  "summary": "…",
  "next_actions": []
}
```

**Why dual output:** the report serves human review and auditability; the JSON serves automation and chaining. A report-only agent can't be orchestrated; a JSON-only agent can't be trusted by a person at a glance. Pydantic should own the JSON contract; the report can be a field within it or a paired render.

---

## 9 & 10. Deployment and evaluation

These are large enough to live on their own — see `production-hardening.md` for deployment (Docker, cloud, frontends, auth, rate limiting, secrets), observability (structured logging, OpenTelemetry, cost ledger), and the full evaluation approach (offline eval sets, LLM-as-judge, tool-success and hallucination metrics, CI gating, failure-mode catalog). The one rule that belongs here: **an agent is not done when it works once; it's done when it's measured, observable, bounded in cost, and safe to redeploy.**
