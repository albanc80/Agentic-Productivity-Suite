---
name: design-governed-ai-agent
description: Design, review, or improve an AI agent using a gated harness workflow covering purpose, instructions, context, skills, memory, permissions, tools, evaluation, and lifecycle operations. Use when a user asks to create an agent, convert a use case into an agent design, assess agent readiness, define governance, or diagnose why an agent is unreliable. Produces specifications and reviews, not code. For implementation hand off to ai-agent-engineer; for non-agent software lifecycle use ai-engineering-operating-system. Do not use for simple one-off prompts, deterministic tasks that do not need an agent, or requests to bypass security, approval, safety, or compliance controls.
---

# Design a Governed AI Agent

## Outcome
Turn an agent idea into an implementation-ready, testable, governed agent specification. Apply the principle:

**Agent = Model + Harness**

The model proposes. The harness controls what the agent sees, remembers, can do, must verify, and how it changes after failure.

## Operating rules

1. Use the smallest implementation that can meet the verified need. Compare the proposed agent with search, analytics, a deterministic workflow, a rule engine, a form, or conventional automation.
2. Do not begin with model selection. Begin with the job, user, value, risk, owner, and evidence of success.
3. Treat instructions, context, skills, memory, permissions, tools, checks, and operations as separate design components.
4. Put critical controls in code, identity, permissions, schemas, policy, or runtime enforcement. Never rely only on prompt wording for an irreversible or high-impact action.
5. Use least privilege. Expose only the context, memory, permissions, and tools needed for the current job.
6. Require human approval for material, external, irreversible, safety-relevant, financial, legal, regulatory, or reputational actions unless explicit authorization and enforceable policy cover them.
7. Never claim readiness, certification, publication, or successful execution without evidence.
8. Mark missing facts as assumptions or open questions. Do not invent owners, thresholds, data sources, tool capabilities, or test results.
9. Prefer reusable skills for stable procedures. Create a separate agent only for a distinct autonomous goal loop, owner, risk envelope, or lifecycle.
10. Preserve traceability between requirements, controls, versions, tests, approvals, and runtime evidence.

## Workflow

Run Steps 0 through 8 in order. Scale depth to risk. For low-risk design work, keep the output concise. For material autonomy, production, safety, sensitive data, spending, contracts, or external commitments, apply every relevant gate.

### Step 0: Frame the agent

Capture:
- User/actor, domain, expertise, geography, and entitlement boundary.
- Job-to-be-done: "When [situation], I want to [job], so I can [outcome]."
- Required output or action.
- Accountable business owner, service owner, technical owner, and escalation path.
- Intended and forbidden outcomes.
- Highest-harm possible action.
- Baseline, target metric, and acceptance evidence.
- Why an agent is preferable to a simpler implementation.
- Proposed harness scope: personal, team, company, or customer feature.

**Gate 0:** Continue only if there is a specific job, named accountable owner, measurable outcome, and at least one explicit forbidden outcome. If an owner is unknown, label it `TBD` and block publication.

Define the first hard limit around the highest-harm action. Examples: approved destination systems, data classifications, transaction amount, record count, prohibited operational recommendation, or required approval before sending, deleting, committing, or executing.

### Step 1: Design instructions

Create the smallest stable instruction set containing:
- Role and purpose.
- Target user and job.
- Ordered operating procedure.
- Decision rules for continue, clarify, refuse, escalate, and stop.
- Allowed and forbidden actions.
- Output contract.
- Behavior for missing, stale, ambiguous, or conflicting evidence.
- Tool-use rules.
- Human checkpoints.
- Completion definition.

For every critical rule, identify its enforcement layer: prompt, policy, code, permission, schema, or runtime control.

**Gate 1:** Instructions are concise, testable, internally consistent, versioned, and do not depend on model goodwill where stronger enforcement is possible.

### Step 2: Design context

Use this hierarchy:
Organization > domain/business unit > product/project > workflow/page > conversation/task > current request.

For each context source record:
- Name and owner.
- Source type and authoritative status.
- Retrieval method and filters.
- User entitlement rule and sensitivity.
- Freshness requirement and timestamp behavior.
- Maximum context budget.
- Conflict precedence.
- Citation/provenance requirement.
- Failure behavior when unavailable.

Retrieve the minimum sufficient context. Filter access before retrieval. Prefer structured, authoritative facts. Preserve source IDs and timestamps. Separate known, inferred, missing, and prohibited information.

**Gate 2:** Every critical decision has an authoritative source, entitlement rule, freshness rule, and missing-source behavior.

### Step 3: Select or define skills

For each reusable procedure define:
- Unique ID, name, version, purpose, and trigger.
- Inputs and validation schema.
- Ordered procedure.
- Required tools and permissions.
- Output schema.
- Dependencies and relationships.
- Examples, failure modes, owner, tests, and source repository.

Search for an existing canonical skill first. Combine skills only through declared relationships: `parent`, `routes_to`, `triggers`, `related_skills`, and `depends_on`. Prevent cycles, uncontrolled delegation, and permission expansion. Record exact versions used.

**Gate 3:** Every claimed behavior maps to a skill procedure and at least one runnable test. Dependencies resolve without cycles or broader permissions.

### Step 4: Design memory

Classify proposed memory as:
- Working: current plan and intermediate results; short-lived.
- Episodic: prior interaction summaries and decisions.
- Semantic: durable facts, preferences, definitions, and relationships.
- Procedural: normally belongs in skills or instructions.
- External state: authoritative business records referenced rather than copied.

Before writing memory, check usefulness, stability, authority elsewhere, sensitivity, legal storage, expiry, correction, and deletion.

Store one fact per record with provenance, timestamp, subject, scope, confidence/status, owner, expiry/review date, links, and correction history. Retrieve mutable operational values from their source instead of long-term memory.

**Gate 4:** Every memory field has a purpose, source, scope, retention period, and deletion behavior.

### Step 5: Design permissions

For every action specify:
- Action ID, description, resource, and environment.
- Read/write/delete/execute classification.
- Side-effect severity and reversibility.
- Data sensitivity.
- Maximum amount, count, duration, or scope.
- Allowed identities and audiences.
- Approval rule and authorization expiry.
- Logging/evidence requirement.
- Rollback, containment, and emergency disable path.

Use the continuum: suggestions > approved subset actions > full autonomy.

For side effects, the agent proposes the exact action and evidence; policy evaluates hard rules; the human sees target, impact, cost, and rollback; execution uses short-lived authorization bound to the approved action; the result is verified and recorded.

**Gate 5:** Every write or external action has enforceable least privilege, explicit scope, evidence, and rollback or containment.

### Step 6: Design tools

For each tool record:
- ID, version, owner, purpose, and usage guidance.
- Input/output schema.
- Authentication reference, scopes, and data classification.
- Side effects and reversibility.
- Timeout, retry, idempotency, rate/cost limits, and errors.
- Logging, redaction, dependency health, and denial behavior.

Expose the minimum tool set for the current skill and task. Validate arguments before execution. Reauthorize side effects. Verify the result rather than trusting a success string. Hide tools when not needed. Flag overlapping tools or multiple equivalent execution paths.

**Gate 6:** Every tool is necessary, versioned, least-privileged, schema-validated, observable, and tested for success, timeout, malformed output, partial failure, denial, and duplicate execution.

### Step 7: Define checks and publication evidence

Build an evaluation plan containing:
- Deterministic schema, calculation, policy, and format checks.
- Golden tasks with accepted outcomes.
- Negative cases for prohibited actions.
- Ambiguous cases for clarification and escalation.
- Missing-data cases.
- Repeated runs for nondeterministic behavior.
- Adversarial tests for injection, exfiltration, excessive agency, and permission abuse.
- Human domain review against a predefined rubric.
- Production measures for retained use, complaints, overrides, incidents, latency, and cost.

Record the exact model, instructions, skill, tool, data, memory, policy, and runtime versions used in testing. Do not treat an unchecked model judge as a human baseline.

**Gate 7:** Publication requires approved thresholds, no critical unsafe action, adequate human/rubric quality, evidence bound to the exact version, visible limitations, and ready monitoring/recall controls.

### Step 8: Define the improvement and retirement loop

Use this loop:
Observe failure or drift > reproduce > classify root cause > change the smallest harness component > run targeted tests > run regression tests > compare quality, safety, latency, and cost > release progressively > monitor > keep, revise, remove, restrict, recall, deprecate, or retire.

Classify root cause as instruction, context, skill selection, memory, permission, tool/recovery, evaluation/rubric, model behavior, data/dependency drift, or UX/expectation mismatch.

Do not patch every failure with more prompt text. Prefer the strongest appropriate layer and remove obsolete harness pieces. Use feature flags, progressive rollout, and retained rollback artifacts.

**Gate 8:** Keep a change only when evidence shows system-level improvement without unacceptable regression.

## Required output

Produce the following sections. Omit no section; use `TBD` when evidence is missing.

1. **Recommendation**: agent, simpler alternative, or staged combination.
2. **Agent charter**: user, job, outcome, owners, scope, and metric.
3. **Highest-harm action and hard control**.
4. **Harness specification**:
   - Instructions
   - Context
   - Skills
   - Memory
   - Permissions
   - Tools
5. **Evaluation and publication plan**.
6. **Operations and lifecycle plan**.
7. **Readiness matrix** with each gate marked `PASS`, `FAIL`, or `TBD`, plus required evidence.
8. **Risks and mitigations**.
9. **Open decisions** with proposed owner.
10. **Next action**: the smallest concrete step that reduces the most uncertainty or risk.

## Readiness matrix criteria

- Business: owner, user, job, outcome, harm, metric.
- Instructions: version, tests, digest, hard-rule mapping.
- Context: authority, freshness, entitlement, missing-data behavior.
- Skills: canonical playbooks, dependencies, tests, routing integrity.
- Memory: purpose, provenance, scope, retention, deletion.
- Permissions: least privilege, hard limits, approval, kill switch.
- Tools: schemas, identity, errors, retry, idempotency, tests.
- Checks: golden, negative, repeated, adversarial, human baseline.
- Operations: monitoring, incident, recall, rollback, owner/on-call.

## Review mode

When reviewing an existing agent:
1. Preserve the supplied facts.
2. Map present evidence to each gate.
3. Identify contradictions, missing controls, permission expansion, unverified claims, and stale context.
4. Separate design defects from implementation defects and missing evidence.
5. Prioritize findings with the canonical severity (alias in brackets):
   - Critical [P0]: active safety, security, production, or critical customer incident.
   - High [P1]: material near-term delivery or control failure.
   - Medium [P2]: important design or maintainability gap.
   - Low [P3]: useful optimization.
6. Recommend the smallest effective corrective action and the exact evidence that will close each finding.

## Skill relationships

Declared per Step 3 vocabulary:
- `parent`: `ai-engineering-operating-system` (when an agent is built under its STANDARD/ENTERPRISE route, this skill fills its Specify and Architect stages).
- `routes_to`: `ai-agent-engineer` (implementation, code review, teaching). Hand off only when Gates 0-6 are PASS, or the user explicitly chooses a labeled prototype.
- Handoff payload to `ai-agent-engineer`: charter, harness spec, tool and permission tables, eval plan, readiness matrix, open decisions.

## Completion rule

The work is complete only when the requested specification or review is delivered, every applicable gate has a status, missing evidence is explicit, and the next action has an owner or is marked `TBD`. Do not equate a completed design with deployment, adoption, certification, or realized business value.

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
