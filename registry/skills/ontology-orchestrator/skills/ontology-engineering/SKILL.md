---
name: ontology-engineering
description: Designs and implements domain ontologies using rigorous semantic modeling, controlled reasoning, provenance, constraints, and production-oriented artifacts.
version: 1.0.0
---

# Ontology Engineering

## Objective

Translate validated domain meaning and competency questions into a formal, maintainable ontology and related semantic artifacts.

## Architecture layers

Keep these artifacts logically separate:

1. **Ontology / TBox** — domain meaning: classes, properties, axioms.
2. **Reference concepts** — controlled vocabularies/code lists, often SKOS-like.
3. **Shapes** — data validation and structural expectations.
4. **Instance data / ABox** — actual entities/events/observations.
5. **Mappings** — source-to-ontology transformation rules.
6. **Policies/runtime rules** — access, workflow, decision/action controls.

## Design sequence

### 1. Namespace and IRI policy

Define:
- persistent base namespace,
- ontology IRI,
- version IRI,
- prefix conventions,
- entity IRI patterns,
- immutable vs mutable identifiers,
- external identifier mapping,
- deprecation strategy.

Never use mutable display names as primary semantic identifiers.

### 2. Core conceptual model

For each class specify:
- IRI,
- preferred label,
- definition,
- superclass,
- examples/non-examples,
- source/rationale,
- owner,
- lifecycle status.

For each property specify:
- semantic meaning,
- domain/range only when logically valid,
- inverse property if useful,
- characteristics only when justified (functional, transitive, symmetric, etc.),
- expected cardinality as SHACL when it is primarily a data-quality rule.

### 3. Choose reasoning profile

Use a deliberate profile:

- **none/RDF** — semantic labels and graph integration only.
- **RDFS** — lightweight hierarchy/domain/range inference.
- **OWL 2 RL** — rule-friendly reasoning at scale.
- **OWL 2 EL** — large class hierarchies and existential reasoning.
- **OWL 2 QL** — ontology-based access over large relational data.
- **OWL 2 DL** — richer formal semantics when complexity is justified.

Do not choose OWL 2 DL merely because it is more expressive.

### 4. Model relations carefully

Distinguish:
- part-of,
- member-of,
- located-at,
- participates-in,
- produces/consumes,
- observes/measures,
- caused-by/correlated-with,
- assigned-to,
- valid-during,
- derived-from.

Avoid generic properties such as `has`, `relatedTo`, or `associatedWith` when the domain requires a precise relationship.

### 5. Model time and state explicitly

If a relationship changes over time, consider representing the relationship/event as an entity rather than a timeless direct triple.

Example:

```text
Asset --hasAssignment--> Assignment
Assignment --assignedTo--> Facility
Assignment --validFrom--> timestamp
Assignment --validTo--> timestamp
```

### 6. Model measurements explicitly

Do not encode values without units/context.

Minimum pattern:
- observed property,
- numeric/categorical value,
- unit,
- time,
- source/sensor/method,
- quality/status if relevant.

### 7. Add provenance

Track where critical semantic statements originate. Use a consistent provenance vocabulary/pattern.

### 8. Build validation shapes

Use SHACL for expectations such as:
- required fields/relationships,
- cardinality,
- datatype,
- permitted values,
- patterns,
- cross-property rules.

Remember: OWL describes meaning under open-world semantics; SHACL validates data against explicit constraints.

### 9. Build competency-query tests

Every priority competency question should map to one or more executable query tests or logical tests.

### 10. Document assumptions

Create an Ontology Decision Record for:
- controversial class boundaries,
- equivalence mappings,
- imported ontology choices,
- reasoning profile,
- identity patterns,
- breaking changes.

## Modeling heuristics

Prefer:
- precise definitions over verbose definitions,
- small composable modules over a monolith,
- stable core + extension modules,
- external alignment via explicit mappings,
- reusable patterns for time, provenance, measurements, and identifiers.

Avoid:
- converting every source column into a property,
- deep class trees without competency-question value,
- excessive `owl:equivalentClass` or `owl:sameAs`,
- business workflow logic hidden as ontology axioms when an application/policy engine is more suitable,
- overconstraining data with ontology domains/ranges.

## Required implementation outputs

At minimum:
- `ontology.ttl`
- `shapes.ttl`
- `example-data.ttl`
- `competency-queries.rq`
- ontology metadata/version
- namespace/IRI policy
- modeling decision log

## Definition of done

The ontology is ready for validation when:
- all critical concepts have definitions,
- all modeled elements trace to evidence or approved decisions,
- reasoning profile is explicit,
- no known ambiguous equivalences remain,
- SHACL draft exists,
- competency-query tests exist,
- change/version metadata exists.
