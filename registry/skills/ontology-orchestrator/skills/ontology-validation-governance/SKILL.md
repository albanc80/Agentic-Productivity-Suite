---
name: ontology-validation-governance
description: Validates semantic correctness, data constraints, reasoning behavior, compatibility, documentation, security, and governance before ontology release.
version: 1.0.0
---

# Ontology Validation and Governance

## Objective

Treat ontology releases like production software: testable, reviewable, versioned, observable, and reversible.

## Validation layers

### L1 — Syntax and serialization

Validate:
- RDF parser success,
- namespace resolution,
- malformed literals,
- invalid IRIs,
- duplicate prefixes,
- import resolution.

### L2 — Logical quality

Check:
- ontology consistency,
- unsatisfiable classes,
- unintended equivalence,
- contradictory disjointness,
- unsafe property characteristics,
- problematic domain/range inference,
- cycles that create unexpected classification.

### L3 — Structural/data constraints

Run SHACL against:
- golden valid data,
- known-invalid data,
- representative production samples,
- boundary cases.

A shape is not validated until it has both positive and negative test cases.

### L4 — Competency tests

For every critical competency question:
- execute query/reasoning test,
- compare to expected result,
- fail release on critical regression.

### L5 — Mapping regression

When source mappings exist:
- compare row/entity counts,
- detect unmapped fields/concepts,
- validate units and datatypes,
- verify identity resolution,
- inspect mapping collisions,
- measure SHACL violations after transformation.

### L6 — Performance

Measure:
- ontology load time,
- reasoning materialization time,
- query P50/P95 latency,
- memory footprint,
- incremental update cost.

Set target SLOs appropriate to the use case.

### L7 — Governance/security

Verify:
- accountable owner,
- reviewer/approver,
- data classification implications,
- sensitive concept handling,
- least-privilege graph access if required,
- legal/license constraints on reused vocabularies,
- change log,
- deprecation notices,
- rollback plan.

## Semantic versioning policy

Use `MAJOR.MINOR.PATCH`:
- **MAJOR** — breaking semantic or identifier change.
- **MINOR** — backward-compatible new classes/properties/constraints.
- **PATCH** — labels, definitions, metadata, non-semantic corrections.

Treat tighter SHACL constraints as potentially breaking even if ontology axioms do not change.

## Change classification

Every change must be tagged:
- additive,
- behavioral/inference-changing,
- constraint-tightening,
- constraint-relaxing,
- identifier-changing,
- mapping-changing,
- deprecation,
- removal.

## CI/CD release gates

Recommended pipeline:

```text
lint -> parse -> reason -> SHACL -> CQ tests -> mapping tests -> security/license -> performance -> package -> approve -> deploy
```

Block release when:
- parser or reasoner fails,
- critical SHACL test fails,
- critical competency question regresses,
- breaking change lacks migration plan,
- owner/approver is missing,
- unresolved high-risk equivalence exists,
- external imported dependency changed unexpectedly.

## Governance roles

At minimum:
- Domain Owner
- Ontology Steward
- Technical/Semantic Architect
- Data Mapping Owner
- Consumer/Application Owner
- Release Approver

For regulated or safety-critical domains add required compliance/safety reviewers.

## Drift management

Monitor for:
- new source values not in controlled concepts,
- repeated unmapped attributes,
- frequent shape violations,
- emerging synonyms,
- changed business rules,
- deprecated term use,
- query patterns the ontology cannot answer.

Open a change request when drift exceeds configured thresholds.

## Release report

```yaml
release:
  version: 1.2.0
  quality_score: 91
  parser: pass
  reasoning: pass
  shacl: pass
  competency_tests: 24/24
  mapping_tests: pass
  performance: pass
  security_review: pass
  breaking_changes: []
  known_issues: []
  approval: approved
```
