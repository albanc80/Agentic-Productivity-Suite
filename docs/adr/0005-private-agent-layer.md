# ADR 0005: Keep the agent design in a private layer

Status: accepted · 2026-11-04 · amended by ADR 0007 (the installers now carry the pack, encrypted)

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

## Amendment (0.9.0): install from Settings

The notice used to ask people to set `SUITE_PRIVATE_REGISTRY` or edit `suite.yaml`, which breaks the
"no terminals" rule. Settings → System → Agent instructions now imports the pack (`POST /api/agent-pack`,
a `.zip` or `.yaml` files) into the private layer folder in use, or `<data_dir>/private-registry` when none is
set, and reloads the registry in place. Every file is parsed and matched to a catalog agent before
anything is written; zip paths are reduced to file names; files are written `0600` with a plain
`mkdir`. The audit records counts only, never content. Bundling the pack into the installers was
rejected: the installers are public downloads, so anything inside them is public.
