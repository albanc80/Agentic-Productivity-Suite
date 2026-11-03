---
name: ontology-assessment
description: Evaluates an existing ontology, semantic model, taxonomy, knowledge-graph schema, or candidate standard for semantic quality, fitness, operational risk, and reuse.
version: 1.0.0
---

# Ontology Assessment

## Objective

Determine whether an existing semantic asset is trustworthy, reusable, extensible, alignable, or should be replaced.

## Assessment dimensions

Score each 0-5 and provide evidence.

1. **Domain coverage** — supports required competency questions.
2. **Semantic clarity** — definitions are precise and non-overlapping.
3. **Logical soundness** — consistency and satisfiability.
4. **Modeling discipline** — appropriate class/property/individual distinctions.
5. **Reuse/interoperability** — alignment to standards and external vocabularies.
6. **Constraint quality** — executable data-quality rules exist where needed.
7. **Identity strategy** — stable identifiers and equivalence policy.
8. **Provenance** — source, authorship, and change traceability.
9. **Versioning** — release history and deprecation policy.
10. **Documentation** — human-readable definitions and examples.
11. **Performance** — reasoning/query complexity is appropriate for scale.
12. **Governance** — owners, review process, release authority.
13. **Security/privacy** — sensitive semantics and access implications handled.
14. **Mapping readiness** — source systems can be mapped deterministically.
15. **Agent readiness** — supports grounded retrieval/action semantics without ambiguous labels.

## Mandatory tests

Where tooling is available:
- parse ontology,
- run reasoner/consistency check,
- detect unsatisfiable classes,
- detect duplicate labels and suspicious equivalence,
- inspect orphan classes/properties,
- validate ontology metadata,
- execute SHACL over representative data,
- execute competency SPARQL tests,
- evaluate import dependencies,
- measure key query latency,
- check deprecated-term usage.

## High-risk anti-patterns

Flag as severe:
- `owl:sameAs` used for approximate matching,
- concepts defined only by labels,
- mixing class and instance semantics,
- ontology used as a dumping ground for source schema fields,
- no namespace governance,
- mandatory relationships encoded only as comments,
- data validation incorrectly assumed from OWL open-world semantics,
- broad domains/ranges causing unintended inference,
- uncontrolled imports,
- recursive or highly expressive axioms with no runtime need,
- identifiers tied to mutable business labels,
- hidden business rules in ETL with no semantic traceability.

## Decision framework

### REUSE
Use as-is when coverage is high, semantics fit, governance is acceptable, and integration cost is low.

### REUSE + EXTEND
Use when core semantics fit but bounded local concepts are missing.

### ALIGN/FEDERATE
Use when multiple authoritative models must coexist. Create explicit mappings; do not force premature unification.

### WRAP/MAP
Use when an external or vendor model cannot be changed but can be semantically mapped.

### REPLACE
Use when semantics are materially incorrect, ungoverned, logically unsafe, or migration cost is lower than remediation.

### BUILD NEW
Use only after reuse options fail on documented criteria.

## Output

```yaml
assessment:
  asset: <name>
  version: <version>
  overall_score: 0-100
  recommendation: REUSE|EXTEND|ALIGN|WRAP|REPLACE|BUILD_NEW
  critical_findings: []
  breaking_risks: []
  competency_coverage_percent: 0
  remediation_actions: []
  evidence: []
```

## Minimum pass criteria

- No unresolved critical logical defects
- >=80% critical competency-question coverage or a documented extension plan
- Stable identity/namespace strategy
- Explicit governance owner
- Executable validation path
- No unsafe equivalence mappings
