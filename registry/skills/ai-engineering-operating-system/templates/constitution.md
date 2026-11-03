# Engineering Constitution — <repo/product>

Non-negotiable principles every spec, task and review is checked against. Keep it to 10 or fewer items; each must be testable.

1. Language/runtime versions: <e.g. Python 3.12, Node 20>
2. Architecture style and module boundaries: <...>
3. Contract style: typed schemas (Pydantic/OpenAPI/Zod); no free-form inter-service payloads.
4. Security: secrets only via <secret manager>; least privilege; no secrets in code, prompts or logs.
5. Testing: <coverage floor>, required test types per change risk.
6. Observability: structured logs + trace_id on every request; <metrics standard>.
7. Data: owner per entity; migrations are reversible; PII handling rules.
8. AI-specific: model/provider behind an adapter; prompts versioned; tool permissions allowlisted; human approval for high-impact actions.
9. Dependencies: approval rule for new third-party packages.
10. Definition of done: link to `rubrics/release-readiness.md`.

Changes to this file require an ADR.
