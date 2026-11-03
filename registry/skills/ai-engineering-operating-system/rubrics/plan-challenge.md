# Plan Challenge Rubric

Score each item PASS / CONCERN / FAIL with evidence. Any FAIL on items 1, 4, 7 or 9 means the plan is not approved.

| # | Check | Perspective |
|---|---|---|
| 1 | Three plausible failure modes identified, each with mitigation | Architecture |
| 2 | Assumptions listed and the unsupported ones flagged with owner | Architecture |
| 3 | Requirements complete: errors, security, observability, migration | Architecture |
| 4 | Threats covered: authz, data exposure, injection, abuse, excessive agency | Security/Ops |
| 5 | No unnecessary complexity or speculative abstraction | Architecture |
| 6 | Simpler alternative considered and rejected for a stated reason | Architecture |
| 7 | Compatible with grounded repository patterns or deviation has an ADR | Architecture |
| 8 | Every acceptance criterion has a verification method | Security/Ops |
| 9 | Rollback and observability defined | Security/Ops |
| 10 | Cost/latency budget stated (AI systems) | Security/Ops |

**Decision:** Approved / Approved with conditions (list) / Rejected (reason).
