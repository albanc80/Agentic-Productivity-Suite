# Reference Architecture Mapping

## Supplied image: useful baseline

The image models:
1. business users and triggers
2. experience and access
3. agent orchestration
4. knowledge and retrieval
5. model layer
6. tools and actions
7. enterprise data and systems

Cross-cutting elements:
- security, governance and compliance
- human approval
- observability, evaluation and feedback
- runtime and infrastructure

## Production hardening added by this skill

| Image concept | Production-grade extension |
|---|---|
| Identity & Access | Separate user identity from agent/workload identity; least privilege per action; channel-specific auth behavior |
| Session Context | Data minimization, retention, correlation IDs, privacy boundaries |
| Planner / Supervisor | Explicit action-risk policy, stop conditions, failure handling and bounded delegation |
| Workflow Engine | Deterministic agent flows for deterministic logic; idempotency and compensation |
| Multi-agent | Use only for real domain/privilege/reuse boundaries; prevent privilege bypass |
| Short-term memory | Session lifecycle and redaction |
| Long-term memory | Consent, retention, tenancy isolation, deletion and poisoning controls |
| RAG / Knowledge | Entitlement trimming, authoritative-source ranking, provenance, freshness and injection defense |
| Model router | Harness/model decision, version/change control, evaluation baseline, fallback |
| Tools | Tool registry, narrow actions, typed schemas, authorization, risk class, approval and audit |
| Enterprise systems | System-of-record ownership and explicit trust boundaries |
| Human approval | Risk-tiered policy rather than one generic approval box |
| Security | DLP, ACP, network controls, managed environments, agent inventory, audit, secrets |
| Observability | SLOs, traces, evaluation, cost, incident response, telemetry redaction |
| Runtime | Environment separation, ALM, rollback, capacity, DR and operational kill switches |

## Reference enterprise deployment view

```text
Users / Events
      |
      v
+-----------------------+
| Channel / Experience  |
+-----------+-----------+
            |
            v
+-----------------------+      +----------------------+
| Authentication        |----->| Policy / DLP / ACP   |
| User + Agent Identity |      | Approval / Guardrail |
+-----------+-----------+      +----------+-----------+
            |                             |
            v                             |
+----------------------------------------------------+
| Instructions | Orchestration | Topics | Skills     |
+------------------+-------------------+--------------+
                   |                   |
         read path |                   | action path
                   v                   v
       +------------------+   +-----------------------+
       | Knowledge Layer  |   | Tool Execution Layer  |
       +------------------+   +-----------+-----------+
                                         |
                                         v
                              +-----------------------+
                              | Enterprise Systems    |
                              | System of Record      |
                              +-----------------------+

Cross-cutting:
- Managed environments / solutions / pipelines
- Evaluation / telemetry / audit / cost
- Network / secrets / incident management
```

## Architecture decision rule

The preferred design is the least-agentic design that still achieves the business outcome.
