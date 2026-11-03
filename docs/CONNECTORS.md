# Connector setup

All connectors are MCP servers. The suite starts one the first time a run needs it and keeps it running.

**Set them up in the app:** Settings → Connectors. Each connector has an On/Off switch and an **Edit** panel with a field for every value it needs (secrets are write-only), and **Test** lists which tools are allowed or blocked. Values are saved in the suite's local database (unencrypted) and shared by connectors that use the same name, so the Databricks host and token are entered once. An environment variable with the same name takes precedence over a value typed in the app. **Reset to file defaults** removes the app's settings for that connector. In offline mode, connectors that need the internet are paused; Local files keeps working.

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
| Local files | One or more folders, chosen in Settings | Built into the suite (no Node.js or other install). Tools: list, search, read and file info, all read-only. Paths are resolved, symlinks included, and must stay inside the chosen folders. Reads text, CSV, JSON, YAML, PDF, DOCX and XLSX. Works offline | Nothing external |

## Adding a connector

Adding a brand-new connector stays a file edit on purpose: a connector entry can start a program on your computer, so it should not be one click away in a browser. Add an entry to `connectors.yaml` (in `.productivity-suite` in your home folder for the desktop app), then fill in its values in Settings:

```yaml
- id: my-server
  name: My server
  transport: http            # or stdio with command/args/env
  url: https://example.internal/mcp
  headers: {Authorization: "Bearer ${MY_TOKEN}"}
  allow_tools: [search_docs, get_doc]   # optional; otherwise read-only is inferred
```

Then list it under `connectors:` on the playbook steps that may use it. Agents use connector tools only on models with tool calling (`tools: true` in the model config). Other models work from pasted or uploaded inputs, and the run notes say so.
