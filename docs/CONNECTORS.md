# Connector setup

All connectors are MCP servers. The suite starts one lazily the first time a run needs it and keeps it running. Settings → Connectors shows status, the missing variables, and, after **Connect and list tools**, which tools are allowed or blocked.

Launch commands come from each project's documentation and change between releases. Confirm the item in **Verify** before relying on a connector.

| Connector | You set | Notes | Verify |
|---|---|---|---|
| GitHub | `GITHUB_PERSONAL_ACCESS_TOKEN` (fine-grained, read-only). Optional `GITHUB_TOOLSETS` | Runs `ghcr.io/github/github-mcp-server` in Docker with `GITHUB_READ_ONLY=1` | Image name and variables in the github/github-mcp-server README |
| Microsoft 365 | `MS365_MCP_ENABLED=1` after first sign-in | Community server `@softeria/ms-365-mcp-server` via `npx` with `--read-only --org-mode`. Device-code sign-in; work tenants may need admin consent for `Mail.Read` and `Calendars.Read` | Package name and flags in its README |
| Databricks Genie | `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_GENIE_SPACE_ID` | Managed MCP over HTTP: `/api/2.0/mcp/genie/{space_id}` | Managed MCP is in preview; URL patterns have changed before |
| Databricks UC functions | above + `DATABRICKS_UC_CATALOG`, `DATABRICKS_UC_SCHEMA` | `/api/2.0/mcp/functions/{catalog}/{schema}`; all functions allowed because you defined them | Schema-level vs function-level URL form |
| Databricks vector search | above + `DATABRICKS_VS_CATALOG`, `DATABRICKS_VS_SCHEMA` | `/api/2.0/mcp/vector-search/...` | Renamed AI Search (`/ai-search/`); the older prefix is documented as working |
| Azure DevOps | `AZURE_DEVOPS_ORG` | `npx @azure-devops/mcp <org> -d core work work-items repositories wiki`; browser sign-in. No server read-only flag, so the suite's policy is the control | Package and `-d` flag; maintainers recommend their remote server going forward |
| Jira / Confluence | `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN` (+ optional Confluence variables) | Community `ghcr.io/sooperset/mcp-atlassian` with `READ_ONLY_MODE=true` | Image tag; whether `CONFLUENCE_URL` needs `/wiki` |
| Local files | `SUITE_FILES_DIR` | `@modelcontextprotocol/server-filesystem` limited to that folder; only read tools are allow-listed | Tool names in its README |

## Adding a connector

Add an entry to `config/connectors.yaml`:

```yaml
- id: my-server
  name: My server
  transport: http            # or stdio with command/args/env
  url: https://example.internal/mcp
  headers: {Authorization: "Bearer ${MY_TOKEN}"}
  allow_tools: [search_docs, get_doc]   # optional; otherwise read-only is inferred
```

Then list it under `connectors:` on the playbook steps that may use it. Agents use connector tools only on models with tool calling (`tools: true` in the model config). Other models work from pasted or uploaded inputs, and the run notes say so.
