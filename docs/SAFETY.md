# Safety and risk controls

How the suite limits the main risks of running AI agents on real work, where each control lives in
the code, and which test proves it. Decisions behind these controls are in `docs/adr/`.

## Risk controls

| Risk | Control | Where | Verified by |
|---|---|---|---|
| Sensitive data sent to a cloud model | Data-class → locality policy; candidates filtered before any call; run form shows which providers a run can reach | `providers/__init__.py`, `RunForm.tsx` | `test_restricted_data_stays_local`, `test_blocked_when_no_allowed_model`, `test_router_availability_and_locality` |
| Low value without live data | Read-only MCP connectors in MVP; playbooks degrade to pasted or uploaded inputs and say so | `connectors.py`, playbooks | `test_mcp_tool_loop_read_only_and_injection_flag`, `test_stdio_transport_round_trip` |
| Agent writes to external systems | Suite-side read-only policy; write tools hidden and refused; no send/publish tool exists | `connectors.tool_allowed`, `ConnectorManager.call` | `test_policy_rules`, `test_in_process_read_only_enforcement` |
| Prompt injection via pasted text, files or tool output | Untrusted-data envelope, envelope-escape neutralised, pattern screening surfaced as step warnings, operating rule 2 | `guards.py`, `prompts.SUITE_RULES` | `test_injection_and_redaction`, MCP tool-loop test |
| Data sent to an arbitrary endpoint marked "local" | Locality derived from the address (loopback, private, link-local, unique-local, `.local`); offline mode refuses non-local endpoints; every change audited | `endpoints.py`, `main.py` | `test_locality_is_decided_by_address`, `test_public_endpoint_is_cloud_and_blocked_for_restricted`, `test_offline_toggle_persists_and_limits_endpoints` |
| Calculation fed bad input | JSON inputs parsed strictly; invalid JSON or wrong fields block that calculation and lower the run outcome; T&D operation is an enum | `engine._tool`, `tools/__init__.py` | `test_invalid_json_blocks_only_that_calculation`, `test_wrong_calculator_fields_are_reported` |
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
| Brand or personal data in code | Ingest strips them; residue test fails the build; vendor names are blocked in every tracked file | private ingest tool, `backend/tests/test_registry.py` | `test_registry_is_platform_neutral`, `test_no_vendor_brand_anywhere` |
| Agent design exposed in the UI | The API sends only a capability summary, skills, tools and mode summaries; instructions, persona and lineage stay server-side | `Agent.public`, `/api/agents/{id}` | `test_overview_and_catalog` |
| Agent design exposed in the repository or installers | Instructions, personas and lineage are a private layer outside the repository, loaded at runtime; installers never bundle it | `Registry`, `settings.private_registry_dir`, `.gitignore` | `test_private_agent_layer_is_never_committed`, `test_private_layer_overlays_the_catalog` |
| Persona degrading documents | Persona is a separate prompt layer, off for documents by default | `prompts.build_system`, `engine.start` | `test_conditional_parallel_steps_and_persona_off_for_documents` |
