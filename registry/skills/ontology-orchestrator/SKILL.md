---
name: ontology-orchestrator
description: End-to-end orchestration skill for identifying, assessing, designing, validating, mapping, deploying, and governing domain ontologies in production environments.
---

# Ontology Orchestrator

## Mission

Convert a domain problem into a production-governed semantic model and deployment package. Orchestrate discovery, assessment, engineering, validation, mapping, and release governance without inventing unsupported domain facts.

## Operating modes

- **IDENTIFY** — determine whether an ontology is needed and what scope it should cover.
- **ASSESS** — evaluate an existing ontology, taxonomy, schema, canonical model, or knowledge graph.
- **BUILD** — create a new ontology from evidence and competency questions.
- **EXTEND** — add concepts while maintaining compatibility.
- **MIGRATE** — move from legacy ontology/schema to a governed target model.
- **PRODUCTIONIZE** — add validation, mappings, CI/CD, governance, observability, and release controls.

## Non-negotiable rules

1. Start with business/operational outcomes and competency questions.
2. Keep four layers distinct:
   - semantic meaning/ontology,
   - validation constraints,
   - source-system mappings,
   - runtime/deployment policy.
3. Separate evidence from inference. Label each modeling decision as:
   - sourced,
   - derived,
   - proposed,
   - unresolved.
4. Reuse existing vocabularies before creating new terms.
5. Never treat a database schema as an ontology without semantic analysis.
6. Never claim production readiness if a critical quality gate fails.
7. Prefer stable standards unless preview mode is explicitly authorized.
8. Use the least expressive reasoning profile that satisfies required inferences.
9. Avoid closed-world assumptions inside OWL semantics unless the intended logic is explicitly modeled; use SHACL or application rules for data constraints.
10. Every breaking change requires migration and rollback planning.

## Phase model

### Phase 0 — Intake and decision to model

Determine:
- business outcome,
- target users/agents,
- decisions the ontology must support,
- source systems,
- regulatory/security constraints,
- expected graph/data scale,
- latency and reasoning requirements,
- ontology ownership,
- required interoperability.

**Gate G0: Ontology Justification**
Pass only when an ontology provides value beyond a simple schema/taxonomy, such as cross-source semantic integration, inference, reusable domain meaning, agent grounding, policy/constraint modeling, or durable interoperability.

### Phase 1 — Domain discovery

Invoke `domain-ontology-discovery`.

Minimum outputs:
- scope and exclusions,
- stakeholder/source register,
- competency questions,
- candidate concepts/relations,
- terminology conflicts,
- reuse candidates,
- evidence/confidence map.

**Gate G1: Discovery Completeness**
No engineering until critical competency questions and primary evidence sources are identified.

### Phase 2 — Existing-model assessment

Invoke `ontology-assessment` when any prior ontology, taxonomy, canonical schema, industry standard, or vendor model exists.

Decision options:
- REUSE,
- REUSE + EXTEND,
- ALIGN/FEDERATE,
- WRAP/MAP,
- REPLACE,
- BUILD NEW.

**Gate G2: Reuse Decision**
A new ontology may not be created until reuse candidates have been evaluated or the absence of viable candidates is documented.

### Phase 3 — Ontology engineering

Invoke `ontology-engineering`.

Produce:
- namespace/IRI policy,
- conceptual model,
- classes,
- object/data properties,
- labels/definitions,
- axioms,
- controlled vocabularies,
- provenance annotations,
- ontology metadata/version,
- example instances,
- SHACL draft,
- competency-query draft.

**Gate G3: Semantic Design**
No term without definition, ownership/rationale, and placement in the model.

### Phase 4 — Validation and governance

Invoke `ontology-validation-governance`.

Tests:
- syntax/parse,
- ontology consistency,
- unsatisfiable classes,
- SHACL validation,
- competency-query acceptance,
- naming/IRI checks,
- documentation completeness,
- circular/dead concepts,
- duplicate semantics,
- regression compatibility,
- security/privacy review,
- performance reasoning test.

**Gate G4: Release Candidate**
Score >= configured threshold and no critical defects.

### Phase 5 — Mapping and deployment

Invoke `semantic-mapping-deployment`.

Produce:
- source-to-ontology mappings,
- transformation rules,
- identity resolution rules,
- incremental-load semantics,
- data lineage/provenance,
- deployment topology,
- observability/KPIs,
- migration/rollback plan.

**Gate G5: Production Readiness**
Requires tested mappings, monitored deployment, documented owners, version policy, rollback procedure, and approved release.

### Phase 6 — Operate and evolve

Monitor:
- mapping failures,
- SHACL violations,
- unresolved entities,
- semantic drift,
- query performance,
- reasoning cost,
- usage by consumers/agents,
- change requests,
- deprecated concepts.

Trigger review when:
- domain regulation changes,
- new source system added,
- >5% mapping failure rate,
- repeated unknown concepts appear,
- competency questions fail,
- agent errors trace to semantic ambiguity,
- breaking model change is proposed.

## Standard output contract

Return a status block:

```yaml
ontology_program:
  mode: BUILD
  domain: <domain>
  phase: <0-6>
  standard_profile: stable|preview
  reasoning_profile: none|rdfs|owl2-rl|owl2-el|owl2-ql|owl2-dl
  evidence_confidence: 0.00-1.00
  quality_score: 0-100
  release_status: not_started|discovery|design|candidate|approved|blocked
  critical_issues: []
  unresolved_items: []
  artifacts: []
  next_action: <single next action>
```

## Escalation rules

Escalate to a human/domain SME when:
- two authoritative sources conflict,
- a rule affects safety, legal, financial, clinical, or regulatory decisions,
- a proposed equivalence could merge distinct real-world entities,
- cardinality/identity rules are uncertain,
- ontology changes would break production consumers,
- evidence confidence is below 0.70 for a critical concept.

## Completion definition

An ontology is complete enough for production only when:
- competency questions pass,
- semantics are documented,
- data constraints are executable,
- mappings are tested,
- versioning/governance is assigned,
- quality gates pass,
- deployment is observable,
- rollback is possible.
