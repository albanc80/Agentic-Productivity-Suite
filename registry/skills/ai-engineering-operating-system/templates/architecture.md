# Architecture — <system> (v<0.1>)

1. **Context:** actors, external systems, trust boundaries (Mermaid diagram).
2. **Components:** table of component / responsibility / owner / tech.
3. **Interfaces:** sync vs async, contracts, versioning.
4. **Data:** ownership, persistence, consistency, retention.
5. **Failure modes:** per dependency: timeout, retry, idempotency, fallback.
6. **Concurrency and scale assumptions** (numbers).
7. **Security:** identity, secrets, authorization, network boundaries.
8. **Observability:** logs, metrics, traces, SLIs/SLOs and alert thresholds.
9. **Deployment:** environments, promotion, rollback, migrations.
10. **Build vs buy** and **technical-debt** implications.
11. **AI-specific (if applicable):** model/provider abstraction, prompt and policy ownership, tool permissions, memory boundaries, retrieval sources and grounding, eval framework, HITL gates, autonomy limits, fallback, model drift, cost/latency budget, privacy, prompt-injection defenses, auditability. For agents, link the `design-governed-ai-agent` harness spec instead of duplicating it.
12. **Decisions:** list of ADR IDs.
