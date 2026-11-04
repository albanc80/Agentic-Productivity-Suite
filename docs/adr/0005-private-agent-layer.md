# ADR 0005: Keep the agent design in a private layer

Status: accepted · 2026-11-04

## Context
The repository is public. Committed agent files exposed each agent's full instructions, its persona
and how each agent was composed. That design is the suite's main differentiator. The
installers bundled the same files.

## Decision
Split every agent into two layers:

- **Public catalog** (`registry/catalog.yaml`, committed): id, name, desk, summary,
  capabilities, default tier, safety flag, skills, tools and mode summaries. This is what the UI shows.
- **Private layer** (`<private>/agents/<agent-id>.yaml`, never committed or bundled): instructions,
  persona, mode instructions, source and merge lineage. The ingest tool and its report live there too.

`Registry` loads the catalog and merges the private layer at startup. The folder is the first one
found of `SUITE_PRIVATE_REGISTRY`, `private_registry` in `suite.yaml`, `<data_dir>/private-registry`
and `./private-registry` (git-ignored). The desktop launcher points it at
`~/.productivity-suite/private-registry`.

If the private layer is missing, the app still starts. Each agent runs on a short prompt built from
its public card, and a warning says so. Tests use a small fake private layer in
`backend/tests/fixtures/private-registry`.

## Consequences
- Agent quality depends on installing the private layer on each machine; without it agents are generic.
- The private layer needs its own backup and access control (for example a private repository).
- `/api/agents` and `/api/overview` never return instructions, persona or lineage
  (`Agent.public`), so the UI cannot leak them even when the layer is installed.
- A test fails if a private file, the old `registry/agents/` folder or a private key appears in a
  tracked file.
