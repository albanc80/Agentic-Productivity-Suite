---
name: bi-master-orchestrator
description: Use when a BI or upstream O&G intelligence request may require selecting, sequencing, or combining skills in the bi-mcp-skills collection. Routes to the narrowest sufficient child skill, applies guarded Databricks read-only execution, resolves overlap, and validates output contracts.
---

# BI Master Orchestrator

## Purpose

Coordinate the BI MCP skill collection without duplicating child-skill logic. Select the smallest sufficient set of child skills, execute them in dependency order, and synthesize a decision-ready response.

## Operating principles

1. Route to the most specific child skill whose description directly matches the request.
2. Do not run every skill. Use one primary skill unless the request explicitly spans multiple business questions.
3. Use `bi-guarded-databricks-query` only when no narrower skill fits, or as the safety contract for custom SQL.
4. Treat permitting, rigs, production, flaring, water, transactions, and revenue as indicators or proxies unless the selected child skill explicitly defines a stronger interpretation.
5. Never claim forecasts, audited spend, market strategy, regulatory conclusions, or causal relationships from proxy data alone.
6. Respect every child skill's inputs, date windows, limits, parameter handling, output contract, and caveats.
7. Prefer inline dashboard skills only when the user explicitly asks for a dashboard, KPI view, executive summary, HTML view, or former export/get-dashboard behavior.
8. For multi-skill workflows, deduplicate equivalent queries and reuse compatible results when their filters, view, grain, and time window match.

## Routing procedure

### Step 1: Normalize the request

Extract only what the user supplied:
- business question;
- requested entity such as basin, operator, company, country, or region;
- time range or year range;
- desired output such as ranked list, analysis, or inline dashboard;
- decision to support.

Do not invent missing filters. Apply defaults only when the selected child skill defines them.

### Step 2: Choose a route

Evaluate routes in this order:

1. **Explicit dashboard request**: select the matching `bi-inline-*` skill.
2. **Single-domain analytical request**: select the most specific analytical skill.
3. **Cross-domain strategic request**: select up to three complementary analytical skills and define the synthesis question before querying.
4. **Direct or unmatched SQL request**: select `bi-guarded-databricks-query`.

Use `skill-registry.yaml` as the routing registry.

### Step 3: Resolve overlaps

Use these tie-breakers:

- Basin attractiveness across permits, rigs, and production: `bi-basin-ranking`.
- Forward-looking permits plus rig conversion: `bi-drilling-demand-forecast`.
- Completion or frac demand: `bi-completion-market-growth`.
- Operator/account expansion based on recent permits: `bi-customer-expansion-signals`.
- Operator program scale using permits and rigs as spend proxies: `bi-operator-spending-analysis`.
- Production momentum: `bi-production-forecast-changes`.
- Absolute and intensity-based operator flaring exposure: `bi-esg-regulatory-impact`.
- Basin flaring, produced water, and adjacent low-carbon demand: `bi-energy-transition-opportunities`.
- Announced upstream transactions: `bi-ma-early-signals`.
- Big 4 revenue trend: `bi-competitor-intelligence`.
- Executive permits/rigs/production dashboard: `bi-inline-executive-dashboard`.
- Generic inline O&G KPI or divergence dashboard: `bi-inline-og-dashboard`.
- NAM/EMEA opportunity, operator, service-company, or TAM/SAM/SOM dashboard: `bi-inline-nam-emea-market-share-dashboard`.
- NAM/LATAM Big 4 market-share dashboard: `bi-inline-nam-latam-service-market-share-dashboard`.

If two routes remain valid, choose the narrower skill. Combine them only if each answers a distinct part of the user's decision.

### Step 4: Plan execution

Before calling the Databricks MCP, create an internal plan containing:
- selected skill or skills;
- required query sequence;
- user-supplied parameters;
- applicable defaults;
- expected output contract;
- caveats that must appear.

For multi-skill requests:
1. run scope/discovery queries first;
2. run core analytical queries;
3. run comparison or enrichment queries;
4. synthesize only after all required results are available.

### Step 5: Enforce query safety

Apply `bi-guarded-databricks-query` guardrails to custom or adapted SQL:
- read-only statements only;
- approved views only;
- named columns instead of `SELECT *`;
- constrained parameters and identifiers;
- explicit date windows and row limits;
- no credentials, secrets, PII, audit logs, or unrestricted free text;
- no mutation, administrative, notebook, job, or export commands.

A child skill's stricter rule takes precedence.

### Step 6: Validate results

Before responding, verify:
- every result came from the intended view;
- filters and time windows match the request or documented skill defaults;
- row limits were applied;
- units and aliases are preserved;
- rankings use the stated metric;
- no proxy is represented as audited spend, a committed forecast, or proven causation;
- missing or empty results are stated directly;
- inline HTML contains no scripts, iframes, forms, external assets, downloads, or local-file links;
- values inserted into HTML are escaped.

If validation fails, correct the query or narrow the conclusion. Do not hide the failure.

## Multi-skill patterns

### Market opportunity assessment

Use only the components requested:
- market location: `bi-basin-ranking` or `bi-drilling-demand-forecast`;
- target accounts: `bi-customer-expansion-signals` or `bi-operator-spending-analysis`;
- competitor context: `bi-competitor-intelligence`;
- environmental adjacency: `bi-energy-transition-opportunities`.

Return: opportunity, evidence, proxy limitations, risks, and next validation step.

### Account planning

Possible sequence:
1. `bi-customer-expansion-signals` for recent permit momentum;
2. `bi-operator-spending-analysis` for permits/rig breadth;
3. `bi-production-forecast-changes` only if production momentum is requested.

Do not describe proxy activity as confirmed customer budget or buying intent.

### Executive dashboard

Route directly to the single most specific inline dashboard skill. Do not combine dashboard skills unless the user explicitly asks for multiple regional/dashboard views.

## Response contract

Unless a selected child skill requires a stricter format, return:

1. **Answer**: concise decision-oriented conclusion.
2. **Evidence**: key rows or metrics from executed queries.
3. **Interpretation**: what the indicators support.
4. **Caveats**: proxy, coverage, time-window, and data-quality limitations.
5. **Recommended next query**: one concrete validation or drill-down step.
6. **Sources**: Databricks view names, filters, time windows, and returned row counts.

For multi-skill workflows, identify which child skill supports each section.

## Failure handling

- If the Databricks MCP is unavailable, state that execution did not occur and provide no fabricated result.
- If a required view or column is unavailable, identify the missing object and stop that route.
- If filters produce no rows, report the empty result and suggest one narrower or broader filter.
- If the request asks for mutation or unrestricted export, stop and require a separately approved workflow.
- If the question is ambiguous, select the most likely narrow route, state the interpretation briefly, and proceed without expanding into unrelated analyses.
