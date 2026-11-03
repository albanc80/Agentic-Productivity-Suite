# Productivity Suite: plan and decisions

Status: **MVP implemented** (this branch). Last updated 2026-11-03.

## Decisions

| # | Decision | Outcome |
|---|---|---|
| D1 | Runtime | Standalone, platform-agnostic app. Agents run on any mix of local models (Ollama, LM Studio, vLLM), OpenAI-compatible clouds (OpenAI, DeepSeek, OpenRouter) and Anthropic, with per-tier fallback chains. No dependency on the platform the agents were first built in. |
| D2 | Data clearance | The end user is responsible for the credentials and data they use. The app enforces a data-class → provider-locality policy so sensitive runs can be kept local. |
| D3 | MVP scope | PB-01, 03, 04, 05, 08, 10, 13, plus PB-00 Quick Ask. |
| D4 | Personas | On in chat-style playbooks, off in document playbooks and exports. Can be switched per run. Persona text is a separate layer, never mixed into instructions. |
| D5 | Stack | Python 3.12 / FastAPI / Pydantic, React + Vite + TypeScript, SQLite. One process serves UI and API. |
| + | Connectors in MVP | GitHub, Microsoft 365 (Graph), Databricks (Genie, UC functions, vector search), Azure DevOps, Jira/Confluence, local files, all read-only. |

## Agent consolidation

38 source agents became 34 suite agents in 8 desks (`registry/desks.yaml`):

- Platform-specific skills (Copilot exercise builders, Copilot Studio hardening and readiness) and branding skills were dropped. `registry/INGEST_REPORT.md` lists every change.

## Risk mitigation map

| Risk | Control | Where | Verified by |
|---|---|---|---|
| Sensitive data sent to a cloud model | Data-class → locality policy; candidates filtered before any call; run form shows which providers a run can reach | `providers/__init__.py`, `RunForm.tsx` | `test_restricted_data_stays_local`, `test_blocked_when_no_allowed_model`, `test_router_availability_and_locality` |
| Low value without live data | Read-only MCP connectors in MVP; playbooks degrade to pasted or uploaded inputs and say so | `connectors.py`, playbooks | `test_mcp_tool_loop_read_only_and_injection_flag`, `test_stdio_transport_round_trip` |
| Agent writes to external systems | Suite-side read-only policy; write tools hidden and refused; no send/publish tool exists | `connectors.tool_allowed`, `ConnectorManager.call` | `test_policy_rules`, `test_in_process_read_only_enforcement` |
| Prompt injection via pasted text, files or tool output | Untrusted-data envelope, envelope-escape neutralised, pattern screening surfaced as step warnings, operating rule 2 | `guards.py`, `prompts.SUITE_RULES` | `test_injection_and_redaction`, MCP tool-loop test |
| Unsafe engineering advice trusted | Safety rules injected for safety-critical agents; deterministic calculators with planning-grade notice; safety-critical playbooks require a gate | `prompts.SAFETY_RULES`, `tools/`, `playbooks.validate` | `test_casing_checker_matches_hand_calculation`, `test_tool_wrapper_adds_safety_notice_and_validates_args` |
| Fabricated facts or evidence | FACT without trace downgraded; "EXECUTED" without a tool call corrected; evidence validator tool | `engine._converse`, `tools.evidence_validator` | `test_fact_without_trace_downgraded_and_false_evidence_corrected`, `test_evidence_validator` |
| Author approves own work | Validation rejects a review by the same agent; revise-once on FAIL | `playbooks.validate`, `engine._maybe_revise` | `test_reviewer_cannot_review_own_work`, `test_scope_change_parallel_review_revise_and_gate` |
| Unauthorised commitments | Named human gates; approval records name, time and edits; runs stop on rejection | `engine._gate`, `engine.decide` | scope-change and rejected-gate tests |
| Cost or runaway loops | Per-run cost and token budget with a continue/stop gate; tool-call limit per step; kill switch | `engine._budget_gate`, `Budgets` | `test_budget_gate`, `test_kill_switch_blocks_new_runs` |
| Small local model context overflow | Context fitting shrinks persona, skills and priors in a fixed order and reports cuts | `prompts.fit` | `test_fit_cuts_low_priority_first_and_never_rules` |
| Model returns malformed output | Tolerant parser, one repair round, then PARTIAL | `contracts.parse_handoff`, engine | `test_parse_*`, `test_contract_repair_path` |
| Provider outage or refusal | Ordered fallback chain; Anthropic server-side refusal fallback on supported models | `engine._agent`, `anthropic_provider.py` | `test_fallback_to_next_model_on_provider_error`, `test_anthropic_*` |
| People evaluated in reports | Operating rule 4; deliverable screening flags evaluative language | `guards.scan_people_eval` | `test_injection_and_redaction` |
| Secrets in logs | Credentials only via env; audit and stored prompts redacted; prompts hashed by default | `guards.redact`, `store.py` | `test_injection_and_redaction` |
| Exposure on a network | Binds to localhost; optional bearer token | `main.py` | `test_api_token` |
| Brand or personal data in code | Ingest strips them; residue test fails the build | `scripts/ingest_agents.py` | `test_registry_is_platform_neutral` |
| Persona degrading documents | Persona is a separate prompt layer, off for documents by default | `prompts.build_system`, `engine.start` | `test_conditional_parallel_steps_and_persona_off_for_documents` |

## Roadmap

**Now (this MVP).** Exit criteria:
1. All 7 playbooks pass your review of the benchmark cases (`scripts/run_evals.py`, graded in the report).
2. Cost and latency per run measured on your provider mix.
3. No outbound path exists. Done: the suite has no write tools.

**Next**
- PB-02 Meeting Prep & Debrief, PB-06 Program Risk Review, PB-07 Idea to Validated Opportunity, PB-09 AI Opportunity to Governed Agent, PB-11 Spec to Engineering Delivery Plan, PB-12 Data Product Design.
- PB-15 Well Plan Review, after the calculators pass a validation suite against reference cases reviewed by a qualified engineer.
- Streaming output in the UI; per-message cost display.
- SSO for multi-user deployments.

**Later**
- Gated write actions (send email, update work items), each with an approval record, audit trail and rollback.
- Scheduled runs (morning brief).
- PB-14 Market Growth Thesis (needs licensed market data), PB-16 NPT Event Review, PB-17 Training & Agent Blueprint, PB-18 Invention Disclosure Check.
- Live drilling data (WITSML/ETP), only with written latency requirements and a safety case.

## Success metrics

Set baselines before MVP exit: time to first usable draft per playbook, share of deliverables accepted with minor edits, issues caught by the review step, cost per completed run, runs per week.
