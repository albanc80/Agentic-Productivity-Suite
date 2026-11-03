# Production Hardening: Deployment, Observability & Evaluation

Stages 9 and 10 of the design workflow, plus the cross-cutting concerns that separate a demo from a production agent. Read this for any deployment, hardening (Mode C), or evaluation task.

## Table of contents
1. Deployment
2. Security
3. Observability & cost control
4. Evaluation
5. Failure-mode catalog
6. Production-readiness checklist

---

## 1. Deployment

| Concern | Options | Default guidance |
|---|---|---|
| **API layer** | FastAPI | FastAPI for typed JSON services; Pydantic models double as validation. |
| **Packaging** | Docker | Containerize for reproducibility and parity across environments. |
| **UI (if needed)** | Streamlit, Gradio, React | Streamlit/Gradio for internal tools and demos; React when it's a real product surface. |
| **Cloud** | Azure, AWS, GCP, Railway, Render, Vercel | Match the org's existing platform — for an Azure shop, prefer Azure-native (Container Apps / App Service, Key Vault, Azure OpenAI) for identity, networking, and data-residency alignment. |

**Dockerfile shape (multi-stage, non-root):**

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Pin dependencies, run as non-root, expose a `/health` endpoint for orchestrators, and externalize all config.

---

## 2. Security

- **Authentication & authorization.** Put the agent behind auth (API keys for service-to-service, OAuth/OIDC for users). Enforce per-user/tenant authorization on every tool that touches data.
- **Rate limiting.** Cap requests per principal to contain cost and abuse. Apply at the gateway and as a backstop in-app.
- **Secrets management.** Never hardcode keys. Use a secrets manager / Key Vault and inject at runtime; rotate regularly. Keep keys out of logs, prompts, and error messages.
- **Input handling & prompt injection.** Treat all retrieved/tool content as untrusted data, not instructions. Don't let a document's contents redirect the agent's actions; validate and bound what tools can do regardless of what text the model "decides."
- **Tenant isolation.** In multi-tenant retrieval, filter the vector store by tenant at query time — never rely on the prompt to keep tenants apart.
- **Least privilege for tools.** Each tool gets only the scope it needs (read-only where possible; no broad DB or filesystem access "just in case").

---

## 3. Observability & cost control

You cannot operate what you cannot see. Instrument from day one.

- **Structured logging.** JSON logs with request id, user/tenant, model, tool calls, latency, token counts, and outcome. Queryable beats grep-able.
- **Distributed tracing (OpenTelemetry).** Trace a request across nodes/agents/tools so you can find where latency and failures originate.

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

def research(state):
    with tracer.start_as_current_span("research") as span:
        span.set_attribute("agent.node", "research")
        result = do_research(state["query"])
        span.set_attribute("findings.count", len(result))
        return {"findings": result}
```

- **Cost / token ledger.** Record tokens and estimated cost per request and per tenant; alert on anomalies. Token usage is both a cost signal and an early warning that an agent is looping.
- **Bounded execution.** Enforce max steps and a per-task cost ceiling so a confused agent fails cheaply instead of running up a bill.
- **Latency budget.** Track p50/p95/p99; agents with tool loops have long tails — watch the tail, not the mean.

---

## 4. Evaluation

**Never assume an agent is production-ready.** Evaluate before launch and continuously after.

### What to measure
| Metric | What it catches |
|---|---|
| **Accuracy / task success** | Does it produce the right answer/action? |
| **Hallucination rate** | Unsupported claims, invented sources/IDs. |
| **Tool success rate** | Wrong-tool, bad-args, and tool-error handling. |
| **Latency** (p50/p95/p99) | User-facing responsiveness; tail behavior. |
| **Cost / token usage** | Economic viability; loop detection. |
| **Reliability** | Crash rate, validation-failure rate, recovery. |
| **User satisfaction** | Real-world fitness (thumbs, surveys, acceptance). |

### How to evaluate
1. **Build an offline eval set.** Curate representative inputs with known-good expectations (gold answers, required fields, must-cite sources). Version it.
2. **Assert on the structured output.** Because outputs are typed (Stage 2/8), many checks are deterministic: field presence, value ranges, schema validity, required citations present.
3. **LLM-as-judge for subjective quality.** For answer quality/groundedness, use a separate model with a rubric to grade outputs. Calibrate the judge against human labels on a sample before trusting it.
4. **Tool and hallucination checks.** Verify every factual claim maps to a real retrieved source; flag claims with no source. Log tool-call success/failure explicitly.
5. **Gate in CI.** Run the eval set in CI (GitHub Actions) on prompt, model, or tool changes; block merges that regress key metrics. This is what makes redeployment safe.
6. **Monitor in production.** Sample live traffic, track the same metrics, and feed failures back into the eval set — the set should grow from real failures.

This section is the engineering-side baseline. Publication thresholds, human-baseline rubrics and version-bound evidence are owned by `design-governed-ai-agent` Step 7 (Gate 7); release gating is owned by `ai-engineering-operating-system` Stage 10.

---

## 5. Failure-mode catalog

Design tests and guardrails against these common agent failures:

- **Silent fabrication** — invents sources, IDs, or facts. → Require source-mapped claims; assert in eval.
- **Tool misuse** — wrong tool, malformed args, ignores tool errors. → Validate tool I/O; add reflection step.
- **Infinite/expensive loops** — never finalizes. → Hard cap on steps and cost; `needs_review` fallback.
- **Context loss** — forgets earlier turns or task state. → Correct memory design (Stage 6).
- **Validation bypass** — malformed output reaches downstream. → Pydantic at the boundary; fail loud.
- **Prompt injection via retrieved content** — document text hijacks behavior. → Treat tool/retrieval output as data; bound tool privileges.
- **Tenant/data leakage** — returns another tenant's data. → Filter retrieval by tenant; isolation tests.
- **Cost blowout** — token spend spikes unnoticed. → Cost ledger + alerts.

---

## 6. Production-readiness checklist

Before declaring an agent done, confirm:

- [ ] Typed input/output contracts with validation at the boundary
- [ ] Prompt contains role, context, objective, constraints, rules, tools, examples, output format
- [ ] Tools have model-facing descriptions, validated I/O, least privilege
- [ ] Tool/agent loop is bounded by max steps and a cost ceiling
- [ ] Memory type matches the need; TTLs and isolation in place
- [ ] Auth, rate limiting, and secrets management configured
- [ ] Retrieved/tool content treated as untrusted (injection-aware)
- [ ] Structured logging + tracing + token/cost ledger live
- [ ] Offline eval set exists and is gated in CI
- [ ] Hallucination and tool-success checks pass thresholds
- [ ] Failure modes have tests and graceful fallbacks
- [ ] Human-readable report **and** structured JSON both produced
- [ ] Runbook: how to build, run, test, deploy, and roll back

An agent that clears this list is observable, bounded, measured, and safe to redeploy — the actual definition of production-ready.
