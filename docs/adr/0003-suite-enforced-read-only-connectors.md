# ADR 0003: Read-only MCP connectors enforced by the suite

Status: accepted · 2026-11-03

## Context
Live context (GitHub, Microsoft 365, Google Workspace, Databricks, Azure DevOps, Jira) is where most of the agents' value comes from. MCP servers differ: some have a read-only flag, some do not, and annotations are optional.

## Decision
- Connectors are MCP clients owned by a per-connector worker task (MCP transports must enter and exit in the same task).
- The suite decides which tools exist for agents: allow-list, else `read_only_hint` (and not destructive), else a query-like name with no write verb. Deny-list always wins. Blocked tools are never offered, and a direct call is refused.
- Server-side read-only flags are set in presets as a second layer.
- Tool results are wrapped as untrusted data, truncated to a budget and screened for injection.
- Credentials are passed only through environment variables to the connector process or headers.
- A connector that serves several accounts names the tool argument that selects the account (`accounts.param`). The suite allows only the accounts listed in settings, fills in the default when a call names none, and tells agents which accounts are connected.

## Consequences
- Write actions are impossible in the MVP. Gated writes are a later, explicit design with approval records and rollback.
- Name-based inference can block legitimate read tools with unusual names. Fix with `allow_tools` per connector.
