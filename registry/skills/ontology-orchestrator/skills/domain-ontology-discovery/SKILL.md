---
name: domain-ontology-discovery
description: Discovers the domain scope, competency questions, terminology, source evidence, semantic conflicts, and reusable vocabularies required to design an ontology.
version: 1.0.0
---

# Domain Ontology Discovery

## Objective

Identify the meaning the ontology must encode before designing the ontology itself.

## Inputs

Use any available combination of:
- business requirements,
- process documentation,
- SOPs/policies,
- data dictionaries,
- APIs/schemas,
- database DDL,
- event schemas,
- reports/dashboards,
- industry standards,
- existing taxonomies/ontologies,
- SME interviews,
- sample operational data.

## Workflow

### 1. Define outcome and boundaries

Capture:
- domain,
- business outcome,
- in-scope processes,
- excluded subdomains,
- geographic/regulatory scope,
- consumers,
- decisions/actions supported,
- temporal scope,
- expected scale.

Reject vague scopes such as "model the enterprise". Decompose into bounded domain modules.

### 2. Generate competency questions

Competency questions are natural-language questions the ontology must make answerable or logically support.

Classify each as:
- descriptive,
- relational,
- temporal,
- classification,
- inference,
- compliance/constraint,
- lineage/provenance,
- operational/actionability.

For each question capture:
- priority,
- expected answer shape,
- required concepts,
- evidence source,
- acceptance test.

Example:

> Which assets are currently assigned to a facility, are certified for the planned operation, and have an inspection expiring within 30 days?

This forces modeling of Asset, Facility, Assignment, Certification, Operation, Inspection, expiration time, and eligibility rules.

### 3. Extract a terminology register

For every candidate term:
- preferred label,
- aliases/acronyms,
- definition,
- source,
- source authority,
- example,
- likely type: class/property/value/rule/event,
- ambiguity notes,
- confidence.

Do not convert every noun into a class.

### 4. Identify semantic collisions

Find:
- same term/different meaning,
- different term/same meaning,
- local vs industry definitions,
- unit/measurement ambiguity,
- granularity mismatch,
- temporal interpretation differences,
- status/state inconsistencies,
- identifier conflicts.

Create explicit resolution candidates instead of silently normalizing them.

### 5. Discover reusable vocabularies

Evaluate candidates by:
- domain coverage,
- authority/adoption,
- license,
- maintenance activity,
- semantic fit,
- identifier stability,
- reasoning complexity,
- mapping cost,
- overlap/conflict with other standards.

Never reuse solely because a vocabulary is popular. Record fit-for-purpose evidence.

### 6. Build concept clusters

Group candidate terms into bounded modules such as:
- core entities,
- activities/processes,
- observations/measurements,
- actors/organizations,
- locations,
- products/resources,
- events/states,
- documents/evidence,
- rules/policies,
- provenance.

### 7. Build an evidence graph

For each proposed semantic statement record:

```text
claim -> source -> source location -> authority -> confidence -> reviewer
```

Critical domain rules require authoritative evidence or SME approval.

## Discovery quality checks

Fail discovery if:
- no competency questions exist,
- scope is unbounded,
- key terms lack definitions,
- source authority is unknown,
- conflicts are hidden rather than documented,
- reuse was not investigated,
- implementation schemas are being copied without semantic interpretation.

## Deliverables

- Domain intake
- Competency-question catalog
- Term register
- Semantic-conflict register
- Reuse-candidate matrix
- Evidence/confidence register
- Initial concept clusters
- Discovery gaps and SME questions

## Handoff criteria

Ready for ontology assessment/engineering when:
- critical competency questions are testable,
- at least 80% of critical terms have source-backed definitions,
- semantic conflicts are either resolved or explicitly open,
- reusable ontology/vocabulary options are documented.
