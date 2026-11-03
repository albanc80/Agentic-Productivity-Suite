# Enterprise AI Architecture Output Template

## 1. Executive Recommendation
- Decision:
- Business outcome:
- Why this architecture:
- Primary trade-off:

## 2. Facts, Assumptions and Constraints
### Facts
### Assumptions
### Constraints
### Open Decisions

## 3. Platform / Harness Decision
- Target harness:
- Alternatives rejected:
- Decision rationale:
- Licensing/capacity implications:

## 4. Autonomy and Action Risk
| Action | A0/A1/A2/A3 | Identity | Approval | Reversible | Audit |
|---|---|---|---|---|---|

## 5. Logical Architecture
```text
<ASCII diagram>
```

## 6. Deployment Architecture
- Environments:
- Trust boundaries:
- Network boundaries:
- Regional/data-residency constraints:

## 7. Component Mapping
| Requirement | Component | Why | Alternative | Constraint |
|---|---|---|---|---|

## 8. Identity and Authorization
- User identity:
- Agent identity:
- Tool credential model:
- Least-privilege design:

## 9. Knowledge and Memory
- Sources:
- Entitlements:
- Freshness:
- Provenance:
- Memory lifecycle:
- Injection/poisoning controls:

## 10. Tools and Integrations
| Tool | Purpose | Contract | Auth | Timeout | Retry | Idempotency | Risk | Approval |
|---|---|---|---|---|---|---|---|---|

## 11. Resilience
- Dependency failures:
- Graceful degradation:
- Recovery:
- Kill switches:

## 12. Security and Governance
- DLP / ACP:
- Data classification:
- Logging/redaction:
- Human approval:
- Audit:

## 13. Evaluation and Observability
- Baseline test set:
- Adversarial tests:
- SLOs:
- Alerts:
- Cost metrics:

## 14. ADRs
### ADR-001
- Context:
- Options:
- Decision:
- Consequences:

## 15. Risks
| Risk | Likelihood | Impact | Control | Owner | Residual |
|---|---|---|---|---|---|

## 16. Implementation Plan
### Phase 1 — Foundation
### Phase 2 — Controlled Pilot
### Phase 3 — Production
### Phase 4 — Scale

## 17. Production Acceptance Criteria
- [ ] Security gates passed
- [ ] Evaluation baseline passed
- [ ] ALM and rollback verified
- [ ] Observability verified
- [ ] Operations ownership assigned
- [ ] Cost/capacity guardrails verified
