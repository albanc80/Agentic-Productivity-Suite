---
name: ai-engineering-operating-system
description: Risk-calibrated engineering orchestration for designing, building, reviewing, refactoring, or releasing software, AI agents, data products, APIs, and enterprise digital platforms. Use for material engineering work that benefits from repository grounding, explicit specifications, architecture, adversarial review, testing, security, and release gates; do not use the full workflow for trivial edits. For agent work, this skill is the outer lifecycle - delegate agent specification/governance to design-governed-ai-agent and agent code to ai-agent-engineer; do not use it alone for teaching agent concepts.
---

# AI Engineering Operating System

## Purpose

Use this skill to frame, specify, architect, decompose, implement, review, verify, and release software or AI-enabled products with a risk-calibrated workflow.

The core principle is simple:

> Architecture and specification precede autonomous implementation.

The coding agent is the execution runtime, not the product manager, architect, specification authority, security authority, or final evaluator.

---

## Activation

Activate automatically when the user asks to:

- design, build, review, modernize, or refactor a software product;
- create or evaluate an AI agent or multi-agent system **as the outer lifecycle only** (Specify/Architect delegated to `design-governed-ai-agent`, Implement to `ai-agent-engineer`);
- design a digital platform, API, data product, workflow, or enterprise application;
- turn a rough idea into an implementation-ready engineering plan;
- review an existing repository before making material changes;
- evaluate architecture, security, testability, or release readiness;
- orchestrate implementation through multiple coding agents;
- create a PRD, specification, architecture, ADR, implementation plan, or engineering roadmap that will lead to code.

Do not invoke the full workflow for trivial edits. Route work using the risk model below.

---

## Operating Model

The canonical lifecycle is:

1. **Frame** — establish the problem, outcomes, users, constraints, risks, and success criteria.
2. **Ground** — inspect the actual repository, dependencies, architecture, standards, interfaces, data model, and known constraints.
3. **Specify** — convert intent into an explicit engineering contract.
4. **Architect** — determine system boundaries, responsibilities, trade-offs, interfaces, data flows, security model, and deployment model.
5. **Challenge** — attack the plan before implementation.
6. **Decompose** — split the approved architecture into independently verifiable units of work.
7. **Implement** — execute against the approved specification and task contract.
8. **Review** — use an independent reviewer or agent to assess correctness, maintainability, security, and architectural alignment.
9. **Verify** — prove acceptance criteria using tests and objective evidence.
10. **Release** — validate operational readiness, rollback, observability, ownership, and post-release controls.

Never collapse these into “prompt → code” for material work.

---

## Risk-Based Routing

Classify every task before deciding process depth.

### FAST

Use when all are true:

- localized change;
- low blast radius;
- no material data-model or security change;
- no new external integration;
- reversible;
- acceptance criteria are obvious.

Workflow:

`Understand → Ground → Implement → Test → Review`

Examples:

- bug fix;
- small UI change;
- typo or copy change;
- small refactor with existing tests;
- minor configuration update.

### STANDARD

Use when any are true:

- new feature;
- moderate refactor;
- new API or integration;
- changes affect multiple modules;
- design choices exist;
- acceptance criteria need definition.

Workflow:

`Frame → Ground → Specify → Architect → Challenge → Decompose → Implement → Review → Verify`

### ENTERPRISE

Use when any are true:

- platform or system-of-record change;
- agentic or autonomous workflow;
- safety-, security-, compliance-, or financially material behavior;
- sensitive data;
- critical production workflow;
- major architecture or migration;
- multiple teams or business domains;
- irreversible or high-blast-radius change.

Workflow:

`Frame → Ground → Specify → Architecture → Threat Model → Challenge → ADRs → Decompose → Implement → Independent Review → Security Review → QA → Acceptance → Release Readiness`

For ENTERPRISE work, default to human approval at architecture, security, and release gates.

---

## Mandatory Pre-Code Questions

No implementation agent receives write permission until the workflow can answer:

1. What problem are we solving?
2. Why does it matter?
3. Who is affected?
4. What are the acceptance criteria?
5. What constraints apply?
6. What already exists?
7. What architecture or integration points are affected?
8. How will the change be implemented?
9. How will we prove it works?
10. What can go wrong?
11. What is the rollback path?

For FAST work, concise answers are sufficient. For STANDARD and ENTERPRISE work, these answers must be represented in durable artifacts.

---

## Stage 1 — Frame

Use `templates/project-brief.md`.

Required outputs:

- problem statement;
- target users / actors;
- desired outcomes;
- measurable success criteria;
- in-scope / out-of-scope;
- constraints;
- business and operational risks;
- dependencies;
- assumptions requiring validation;
- open decisions.

Do not accept solution language as a substitute for a problem statement.

If the user gives a solution first, reverse-engineer the underlying problem and validate whether the solution is necessary.

---

## Stage 2 — Repository and Environment Grounding

Before architecture or implementation, inspect the actual environment when available.

Use `references/repository-grounding.md`.

Produce a concise grounding record containing:

```yaml
existing_architecture:
primary_languages:
frameworks:
dependencies:
entry_points:
module_boundaries:
external_integrations:
data_models:
security_constraints:
authentication_authorization:
deployment_model:
observability:
test_patterns:
coding_patterns:
known_debt:
risk_zones:
unknowns:
```

Rules:

- Prefer repository evidence over assumptions.
- Reuse existing architectural patterns unless there is a documented reason not to.
- Identify existing abstractions before creating new ones.
- Identify tests before changing behavior.
- Identify ownership and deployment path before changing production-critical code.
- Mark inferred information explicitly as inference.

---

## Stage 3 — Specify

Use `templates/spec.md` and `templates/constitution.md`.

The specification is the engineering contract.

It must contain:

- functional requirements;
- non-functional requirements;
- acceptance criteria;
- user / system flows;
- interfaces and contracts;
- data requirements;
- error handling;
- security requirements;
- observability requirements;
- performance expectations;
- operational constraints;
- migration / compatibility constraints;
- exclusions.

Write requirements so they can be tested.

Avoid requirements such as “fast,” “scalable,” “secure,” or “user friendly” without measurable interpretation.

---

## Stage 4 — Architect

Use `templates/architecture.md` and `templates/adr.md`.

Architecture must address:

- system context;
- component boundaries;
- responsibilities;
- interfaces;
- synchronous vs asynchronous interactions;
- data ownership;
- persistence;
- failure modes;
- retries / idempotency where relevant;
- concurrency;
- security boundaries;
- secrets and identity;
- observability;
- deployment;
- scale assumptions;
- resiliency;
- upgrade / migration strategy;
- build-vs-buy decisions;
- technical debt implications.

For AI systems additionally address:

- model / provider abstraction;
- prompt and policy ownership;
- tool permissions;
- memory boundaries;
- retrieval sources;
- grounding strategy;
- evaluation framework;
- human-in-the-loop gates;
- autonomy boundaries;
- fallback behavior;
- model/version drift;
- cost and latency controls;
- data privacy;
- prompt injection / tool abuse risk;
- auditability.

Every material architectural decision should have an ADR when the decision has meaningful alternatives or long-term consequences.

---

## Stage 5 — Challenge the Plan

Do not let the authoring agent be the only evaluator.

Use `rubrics/plan-challenge.md` (architecture/security perspectives) and, for code, `rubrics/code-review.md`.

Minimum challenge sequence:

1. identify three plausible failure modes;
2. identify unsupported assumptions;
3. identify missing requirements;
4. identify security and operational risks;
5. identify unnecessary complexity;
6. identify simpler alternatives;
7. check repository compatibility;
8. check testability;
9. check rollback and observability;
10. decide whether the plan is approved, approved with conditions, or rejected.

For ENTERPRISE mode, use at least two independent perspectives:

- architecture reviewer;
- security / operational reviewer.

---

## Stage 6 — Decompose

Use `templates/task.md`.

Decompose by independently verifiable outcome, not by vague activity.

Bad:

- “work on backend”;
- “implement frontend”;
- “update database.”

Good:

- “Add POST /v1/orders with idempotency enforcement and tests for duplicate submission.”
- “Implement token refresh with 401 retry behavior and integration tests.”

Each task must contain:

- objective;
- scope;
- files / modules likely affected;
- dependencies;
- explicit non-goals;
- acceptance criteria;
- verification command or method;
- risk level;
- rollback consideration;
- context package.

The implementation agent receives only the context needed for the task plus the authoritative specification and relevant architecture decisions.

---

## Stage 7 — Implement

Implementation rules:

1. No implementation without acceptance criteria.
2. No behavioral change without a verification path.
3. Reproduce defects before fixing them when practical.
4. Prefer the smallest change that satisfies the specification.
5. Do not silently change architecture.
6. Do not create abstractions without demonstrated reuse or complexity reduction.
7. Preserve backward compatibility unless explicitly approved otherwise.
8. Keep secrets out of source and prompts.
9. Record material deviations from the plan.
10. Stop and escalate if repository evidence contradicts the approved specification or architecture.

### Test discipline

Use a red/green or equivalent evidence-driven loop when practical:

`failing evidence → implementation → passing evidence → regression suite`

Do not claim completion from code inspection alone when executable verification is available.

---

## Stage 8 — Independent Review

The reviewer must not simply restate the implementation agent's reasoning.

Use `agents/adversarial-reviewer.md` and the appropriate rubric.

Review in this order:

1. specification compliance;
2. correctness;
3. architecture alignment;
4. security;
5. data integrity;
6. failure behavior;
7. maintainability;
8. test sufficiency;
9. observability;
10. performance;
11. unnecessary complexity.

Classify findings (canonical name first; see interop contract):

- **Critical / BLOCKER** — must fix before merge/release;
- **High / HIGH** — likely failure or material risk;
- **Medium / MEDIUM** — meaningful defect or debt;
- **Low / LOW** — improvement, cleanup, or minor concern;
- **Note / NOTE** — informational.

A reviewer should provide evidence and location for every blocker/high finding.

---

## Stage 9 — Verify

Verification must map directly to acceptance criteria.

Create an acceptance matrix:

| Acceptance criterion | Evidence | Result |
|---|---|---|
| AC-1 | test / command / observation | PASS/FAIL |

Minimum checks when applicable:

- unit tests;
- integration tests;
- contract/API tests;
- UI / workflow tests;
- security checks;
- lint/static analysis;
- type checking;
- migration verification;
- performance checks;
- failure-path tests;
- rollback validation.

Never replace missing evidence with confidence language.

---

## Stage 10 — Release

Use `rubrics/release-readiness.md`.

Release is allowed only when:

- required tests pass;
- acceptance criteria pass;
- blocker/high findings are resolved or explicitly accepted by an authorized human;
- migration path is understood;
- rollback is defined;
- observability is sufficient;
- runbook / operational ownership exists where needed;
- configuration and secrets are validated;
- user or business communication is addressed when needed.

For ENTERPRISE work, require explicit human approval for production release unless policy says otherwise.

---

## Agent Topology

Use specialized agents when separation of concerns materially improves quality.

Recommended topology:

- **Product Framing Agent** — problem, outcomes, users, requirements.
- **Repository Analyst** — evidence-based system grounding.
- **Architecture Agent** — architecture and ADRs.
- **Research Agent** — external technical research when required.
- **Implementation Agent** — bounded code changes.
- **Test Agent** — verification strategy and execution.
- **Security Reviewer** — threat model, permissions, data risk.
- **Adversarial Reviewer** — independent challenge and code review.
- **Release Reviewer** — readiness, rollback, observability, operations.

Do not create agents merely to create an agent hierarchy. A single agent with explicit role switching is acceptable for FAST and small STANDARD work.

---

## Human Approval Gates

### Gate A — Problem / scope

Required when the problem is ambiguous or business impact is material.

### Gate B — Architecture

Required for ENTERPRISE mode and major architectural changes.

### Gate C — Security / autonomy

Required before expanding agent permissions, sensitive-data access, external side effects, or production-control authority.

### Gate D — Release

Required for high-risk production changes.

Approval means the specific artifact/version is approved. Material changes invalidate prior approval.

---

## Agentic AI Guardrails

For systems that can take actions:

- default to least privilege;
- isolate credentials;
- explicitly enumerate allowed tools/actions;
- require confirmation for destructive or irreversible actions;
- log tool calls and decisions;
- separate read and write capabilities when possible;
- validate tool inputs;
- treat retrieved content as untrusted data;
- prevent external content from overriding system policy;
- define financial / operational action limits;
- define escalation thresholds;
- define timeout and retry behavior;
- require human approval when confidence is insufficient for high-impact action;
- maintain a kill switch or disable path;
- test abuse cases before production.

---

## Context Engineering Rules

1. Preserve authoritative artifacts; summarize transient discussion.
2. Give execution agents the smallest sufficient context.
3. Do not repeatedly paste the entire repository or conversation.
4. Separate facts, decisions, assumptions, and unresolved questions.
5. Reference artifact IDs or filenames when possible.
6. Refresh repository evidence after material changes.
7. Do not allow stale plans to overrule current code reality.
8. Maintain a decision log for material scope or architecture changes.

---

## Completion Contract

A task is not complete because code was written.

Completion requires:

- specified outcome achieved;
- acceptance criteria evidenced;
- tests executed where available;
- material review findings resolved;
- architecture deviations documented;
- operational implications addressed;
- remaining risks stated explicitly.

Final status must be one of:

- **COMPLETE**
- **COMPLETE WITH ACCEPTED RISK**
- **BLOCKED**
- **PARTIAL**
- **REJECTED**

Never use “done” when verification is incomplete.

---

## Default Response Pattern

When this skill activates, lead with:

1. **Route:** FAST / STANDARD / ENTERPRISE
2. **Current gate:** the next decision or artifact required
3. **Plan:** bounded execution stages
4. **Evidence / assumptions:** what is known vs inferred
5. **Next action:** what should happen now

During multi-step work, keep state visible:

```text
STATUS
[x] Frame
[x] Ground
[x] Specify
[ ] Architect
[ ] Challenge
[ ] Implement
[ ] Verify
```

Do not produce process theater. Omit artifacts that do not reduce risk or improve execution.

---

## Anti-Patterns

Reject or challenge:

- prompt → code for material systems;
- architecture invented without repository inspection;
- vague acceptance criteria;
- one agent authoring and approving its own work without independent challenge;
- excessive framework stacking;
- documentation with no decision value;
- tests added only after implementation to match the code;
- silent scope expansion;
- security reviews after release;
- “future scalability” abstractions with no current requirement;
- completion claims without executable evidence;
- agents with broad write access by default.

---

## Agent-work delegation

When the work is an AI agent or multi-agent system:

| AEOS stage | Delegate to | Artifact |
|---|---|---|
| Frame | `design-governed-ai-agent` Step 0 | Agent charter (replaces project brief) |
| Specify / Architect / Threat model | `design-governed-ai-agent` Steps 1-6 | Harness spec + permission/tool tables |
| Challenge | AEOS `rubrics/plan-challenge.md` + DGA gates | Gate statuses |
| Implement | `ai-agent-engineer` Mode B | Code + tests |
| Review | AEOS adversarial reviewer + `ai-agent-engineer` Mode C | One merged findings list (canonical severity) |
| Verify / Release | AEOS Stages 9-10 + DGA Gate 7 | Acceptance matrix + readiness matrix |

Do not produce the same artifact twice under two names.

## Source Methodologies Incorporated

This skill borrows operating concepts from:

- product/architecture-first development patterns associated with BMAD;
- specification-driven development associated with GitHub Spec Kit;
- context decomposition and execution planning associated with GSD-style workflows;
- role-based and adversarial engineering review associated with gstack-style workflows;
- test-first and disciplined implementation patterns associated with Superpowers-style workflows;
- agentic coding runtimes such as Claude Code and Codex.

The skill is a synthesis. It does not require any of those projects to be installed unless the user explicitly wants native integration.

## Skill interop contract (shared by the three agent/engineering skills)

This block is identical in `ai-engineering-operating-system` (AEOS), `design-governed-ai-agent` (DGA) and `ai-agent-engineer` (AAE). Change all three together.

**Roles (layers, not alternatives)**

| Layer | Skill | Owns | Does not own |
|---|---|---|---|
| Lifecycle & risk routing | AEOS | FAST/STANDARD/ENTERPRISE route, repo grounding, decomposition, independent review, verification, release | Agent harness design, agent code templates |
| Agent specification & governance | DGA | Charter, highest-harm control, harness spec (instructions, context, skills, memory, permissions, tools), gates 0-8, readiness matrix | Writing code |
| Agent build & teach | AAE | Code (Pydantic, tool calling, LangGraph, RAG, memory, FastAPI), hardening, teaching | Deciding whether an agent should exist or is ready to publish |

**Routing**

| Request | Primary | Then |
|---|---|---|
| Explain/teach an agent concept | AAE (Mode A) | - |
| Throwaway prototype, no side effects, no sensitive data | AAE (Mode B, prototype) | Label output `PROTOTYPE - not production` |
| New or changed agent intended for real users/data/actions | DGA | AAE builds once DGA Gates 0-6 are PASS |
| Review an existing agent | DGA review mode (governance) + AAE Mode C (code) | One merged findings list |
| Non-agent software, API, data product, refactor, release | AEOS | - |
| Agent work at STANDARD/ENTERPRISE route | AEOS frames | Specify/Architect = DGA; Implement = AAE; Review/Verify/Release = AEOS |

**Canonical severity** (use the first column; others are aliases)

| Canonical | AEOS alias | DGA alias | Meaning |
|---|---|---|---|
| Critical | BLOCKER | P0 | Must fix before merge/release; active safety, security or data-loss risk |
| High | HIGH | P1 | Likely failure or material control gap |
| Medium | MEDIUM | P2 | Meaningful defect or design gap |
| Low | LOW | P3 | Optimization or cleanup |
| Note | NOTE | - | Informational |

**Canonical status**

| Final status (AEOS) | Gate view (DGA) | Runtime outcome |
|---|---|---|
| COMPLETE | All applicable gates PASS | SUCCEEDED |
| COMPLETE WITH ACCEPTED RISK | PASS with an exception approved by a named human | PARTIALLY_SUCCEEDED |
| PARTIAL | One or more non-blocking gates TBD | NEEDS_USER_INPUT |
| BLOCKED | Any blocking gate FAIL or TBD (Gate 0, 5, 6, 7) | NEEDS_HUMAN_APPROVAL / ESCALATED |
| REJECTED | Recommendation is "simpler alternative" or "do not build" | CANCELLED |

**Output format precedence:** exactly one outer frame per response.
1. If the host agent's instructions define a response format, that is the outer frame.
2. Otherwise the outermost active skill's format is the frame (AEOS > DGA > AAE).
3. Inner skills' mandatory sections/checklists go in an appendix inside the frame. Reference, never duplicate, an artifact another skill already produced (e.g. AAE cites the DGA charter instead of redoing Problem Definition).
