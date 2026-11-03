# Repository Grounding Procedure

Goal: replace assumptions with evidence before architecture or code. Mark anything not observed as `INFERRED`.

1. **Inventory:** list top-level tree, languages (file counts), build files (`pyproject.toml`, `package.json`, `Dockerfile`, CI workflows).
2. **Entry points:** app main, API routers, workers, CLIs, scheduled jobs.
3. **Dependencies:** direct dependencies and versions; flag unpinned, deprecated or vulnerable ones.
4. **Module boundaries:** packages/folders and their import direction; detect cycles.
5. **Interfaces:** HTTP routes, events/queues, DB schemas/migrations, external integrations.
6. **Security:** auth middleware, secret loading, permission checks, data classification.
7. **Observability:** logging library and format, tracing, metrics, alerting config.
8. **Tests:** frameworks, locations, how to run, current pass/fail, coverage if available.
9. **Patterns:** error handling, config, DI, naming; reuse these unless an ADR says otherwise.
10. **Debt and risk zones:** TODO/FIXME density, untested critical paths, recent churn (`git log --stat`).

Output the YAML grounding record from SKILL.md Stage 2. Refresh it after material changes.
