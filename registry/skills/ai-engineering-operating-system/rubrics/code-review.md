# Code Review Rubric

Review in order; each finding gets canonical severity (Critical/High/Medium/Low/Note), file:line, failure scenario and fix.

1. Spec compliance (each AC traceable to code + test)
2. Correctness and edge cases
3. Architecture alignment (boundaries, patterns, ADRs)
4. Security (input validation, authz, secrets, injection, dependency risk)
5. Data integrity (transactions, idempotency, migrations)
6. Failure behavior (timeouts, retries, partial failure, user-visible errors)
7. Maintainability (naming, size, duplication)
8. Test sufficiency (failure paths, not just happy path; tests not written to fit code)
9. Observability (logs, trace ids, metrics, no sensitive data in logs)
10. Performance and cost (N+1, unbounded loops, token budget)
11. Unnecessary complexity

AI-specific: schema-validated model output, allowlisted tools, approval gates on side effects, prompt/version identifiers logged, retrieved content treated as untrusted.
