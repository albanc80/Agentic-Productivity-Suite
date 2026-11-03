# Standards Baseline and Adoption Policy

This file records the intended standards posture for this skill suite as of 2026-08.

## Stable production baseline

Prefer standards with Recommendation status and broad implementation support:

- RDF 1.1
- RDFS 1.1
- OWL 2
- SHACL (2017 Recommendation)
- SPARQL 1.1
- SKOS
- PROV-O
- JSON-LD 1.1 where JSON-based interchange is useful

## Emerging 1.2 line

RDF 1.2, SPARQL 1.2, and SHACL 1.2 contain useful capabilities, but production use must be feature-gated by actual implementation support and standards status.

The suite therefore uses:

```yaml
standards_mode: stable   # default
# or
standards_mode: preview  # explicit opt-in
```

### Preview-mode controls

Before adopting a 1.2-only feature:
1. Verify the exact W3C status of the specification.
2. Verify support in every runtime that must parse/query/validate it.
3. Provide a compatibility/fallback path.
4. Add regression tests.
5. Record the decision in an Ontology Decision Record.

## Reasoning profile guidance

Use the minimum expressivity required:

| Profile | Typical fit |
|---|---|
| RDF only | graph integration, metadata, explicit semantics |
| RDFS | simple class/property hierarchies |
| OWL 2 RL | scalable rule-style reasoning over triples |
| OWL 2 EL | large class hierarchies and existential modeling |
| OWL 2 QL | ontology-mediated access over relational sources |
| OWL 2 DL | richer formal reasoning when justified |

## Validation principle

Do not confuse OWL reasoning with data validation. OWL uses open-world semantics; SHACL is the primary constraint layer in this suite for validating expected graph structure and values.
