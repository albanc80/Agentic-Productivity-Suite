# Release Readiness Rubric

All items PASS, or an exception accepted by a named authorized human, before release.

| # | Item | Evidence |
|---|---|---|
| 1 | Required tests pass in CI | run link |
| 2 | Acceptance matrix all PASS | matrix |
| 3 | No open Critical/High findings (or accepted with name + date) | review log |
| 4 | Migration tested forward and back | log |
| 5 | Rollback procedure defined and rehearsed for ENTERPRISE | runbook |
| 6 | Dashboards and alerts live for key SLIs | links |
| 7 | Runbook and on-call owner named | doc |
| 8 | Config and secrets validated per environment | check output |
| 9 | Feature flag / progressive rollout plan | plan |
| 10 | User/business communication done if needed | note |
| 11 | AI systems: eval suite passed on exact release versions (model, prompt, tools); DGA Gate 7 PASS; kill switch tested | report |

Final status: COMPLETE / COMPLETE WITH ACCEPTED RISK / BLOCKED / PARTIAL / REJECTED.
