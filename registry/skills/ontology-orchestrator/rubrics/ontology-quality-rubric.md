# Ontology Production Quality Rubric

Score each dimension from 0 to 5, multiply by its configured weight, and normalize to 100.

| Score | Meaning |
|---|---|
| 0 | Missing or unusable |
| 1 | Ad hoc / high risk |
| 2 | Partial / material gaps |
| 3 | Adequate for controlled pilot |
| 4 | Production capable |
| 5 | Strong, measured, governed, and reusable |

## Dimensions

### 1. Competency coverage
- 0: no competency questions
- 3: most priority questions answerable
- 5: all critical questions executable as regression tests

### 2. Semantic clarity
- 0: labels only
- 3: definitions exist with some ambiguity
- 5: source-backed definitions, examples/non-examples, conflicts resolved

### 3. Logical quality
- 0: unparsed/inconsistent
- 3: consistent but lightly tested
- 5: consistency, satisfiability, inference regression, profile suitability verified

### 4. Validation quality
- 0: no executable constraints
- 3: core SHACL constraints exist
- 5: positive/negative/boundary tests and production validation metrics exist

### 5. Reuse/interoperability
- 0: invented in isolation
- 3: reuse candidates reviewed
- 5: explicit reuse/alignment choices with compatibility and license review

### 6. Identity and IRI governance
- 0: labels or mutable IDs used
- 3: stable namespace policy
- 5: persistent identity, crosswalk, merge/split, equivalence governance

### 7. Provenance/traceability
- 0: model decisions cannot be traced
- 3: source notes exist
- 5: critical claims trace to authoritative source or approved decision record

### 8. Mapping readiness
- 0: no source mapping path
- 3: primary mappings documented
- 5: mappings are versioned, executable/tested, and lineage-preserving

### 9. Versioning/change control
- 0: overwrite-in-place
- 3: versions/changelog exist
- 5: semantic versioning, deprecation, compatibility testing, rollback implemented

### 10. Performance/scalability
- 0: no scale assumptions
- 3: reasoning/query profile chosen
- 5: representative load tests with SLOs and regression thresholds

### 11. Security/compliance
- 0: ignored
- 3: sensitivity/licensing reviewed
- 5: access implications, regulatory constraints, license and audit controls integrated

### 12. Documentation
- 0: machine artifact only
- 3: definitions and examples
- 5: generated documentation, diagrams, consumer guidance, decision records

### 13. Operational observability
- 0: no metrics
- 3: basic mapping/validation metrics
- 5: drift, version skew, mapping, SHACL, identity and performance telemetry with alert thresholds

## Release bands

- **90-100:** production-ready with strong governance
- **85-89:** production-ready if no critical gates fail
- **70-84:** pilot/limited production; remediation required
- **50-69:** prototype only
- **<50:** redesign recommended
