---
name: semantic-mapping-deployment
description: Maps heterogeneous source systems into a governed ontology and deploys the semantic layer with lineage, identity resolution, observability, and rollback controls.
version: 1.0.0
---

# Semantic Mapping and Deployment

## Objective

Operationalize the ontology by connecting real data sources to semantic concepts without losing lineage, identity, units, temporal meaning, or source-system nuance.

## Mapping workflow

### 1. Inventory source contracts

For each source capture:
- system/API/topic/table/file,
- owner,
- schema/version,
- refresh/stream cadence,
- identifiers,
- timestamps/time zones,
- units,
- null semantics,
- enumerations,
- quality issues,
- security classification.

### 2. Create mapping specification

Map each source field or structure to:
- target class/property,
- transform,
- datatype,
- unit conversion,
- identifier rule,
- default/null behavior,
- provenance,
- confidence,
- validation shape.

Never map by label similarity alone for critical fields.

### 3. Identity resolution

Define:
- canonical identity key,
- source-specific keys,
- crosswalk tables,
- deterministic matching rules,
- probabilistic matching threshold if used,
- collision handling,
- merge/split policy.

Do not use semantic equivalence (`owl:sameAs`) as a substitute for entity-resolution uncertainty.

### 4. Preserve temporal semantics

Explicitly distinguish:
- event time,
- observation time,
- source ingestion time,
- effective/valid time,
- processing time.

### 5. Preserve provenance

Every transformed entity/statement should be traceable to its source and transformation version where operationally required.

### 6. Select deployment pattern

Possible patterns:
- native RDF/graph store,
- virtual knowledge graph over relational/lakehouse sources,
- materialized semantic graph,
- hybrid materialized + federated,
- semantic API layer,
- ontology-backed agent/RAG retrieval layer.

Choose based on:
- data volume,
- freshness,
- query latency,
- reasoning need,
- governance boundaries,
- source autonomy,
- cost.

### 7. Agent integration controls

For agentic consumers expose:
- concept definitions,
- allowed relation paths,
- provenance/source confidence,
- action eligibility rules,
- semantic query templates,
- entity resolution status.

An agent must not convert an ambiguous match into a confirmed identity without policy authorization.

## Production observability

Monitor:
- mapping success rate,
- unmapped records/fields,
- SHACL violation rate,
- identity-collision rate,
- stale-source age,
- semantic query P95,
- reasoner latency,
- graph growth,
- failed imports,
- ontology-version skew across consumers.

## Release strategy

Use:
- immutable versioned ontology packages,
- blue/green or side-by-side semantic versions for major changes,
- migration scripts/crosswalks,
- compatibility tests,
- rollback to prior ontology + mapping bundle.

## Deliverables

- source inventory
- mapping specification
- identity resolution policy
- transformation implementation contract
- lineage/provenance design
- deployment architecture
- monitoring/SLO definition
- migration/rollback plan
- production runbook
