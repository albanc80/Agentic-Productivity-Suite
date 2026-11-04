# Connector setup

All connectors are MCP servers. The suite starts one the first time a run needs it and keeps it running.

**Set them up in the app:** Settings → Connectors. Each connector has an On/Off switch and an **Edit** panel with a field for every value it needs (secrets are write-only), and **Test** lists which tools are allowed or blocked. Values are saved in the suite's local database (unencrypted) and shared by connectors that use the same name, so the Databricks host and token are entered once. An environment variable with the same name takes precedence over a value typed in the app. **Reset to file defaults** removes the app's settings for that connector. In offline mode, connectors that need the internet are paused; Local files keeps working.

Launch commands come from each project's documentation and change between releases. Confirm the item in **Verify** before relying on a connector.

| Connector | You set | Notes | Verify |
|---|---|---|---|
| GitHub | `GITHUB_PERSONAL_ACCESS_TOKEN` (fine-grained, read-only). Optional `GITHUB_TOOLSETS` | Runs `ghcr.io/github/github-mcp-server` in Docker with `GITHUB_READ_ONLY=1` | Image name and variables in the github/github-mcp-server README |
| Microsoft 365 | `MS365_MCP_ENABLED=1` after a one-time `npx -y @softeria/ms-365-mcp-server --login`. Optional `MS365_MCP_ORG_MODE=1` (work or school account), `MS365_MCP_PRESET` (default `personal`), `MS365_ACCOUNTS` (several accounts) | Community server `@softeria/ms-365-mcp-server` via `npx` with `--read-only --preset personal`: Outlook mail and calendar, OneDrive files, contacts, To Do, OneNote, search. `MS365_MCP_PRESET=work` (with org mode) adds Teams, SharePoint and shared mailboxes. Work tenants may need admin consent | Package name, `--preset` names and `MS365_MCP_ORG_MODE` in its README and PRESETS.md |
| Google Workspace | `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `USER_GOOGLE_EMAIL`. Optional `GOOGLE_OTHER_ACCOUNTS` (several accounts), `WORKSPACE_MCP_PORT` (default 8000), `GOOGLE_WORKSPACE_TOOL_TIER` (default `core`) | Community server `workspace-mcp` via `uvx` with `--read-only --tools gmail calendar drive docs sheets slides tasks contacts`. Create an OAuth client in Google Cloud and enable those APIs; for a Web application client add `http://localhost:8000/oauth2callback` as a redirect URI. The first read opens your browser for Google sign-in; run the step again afterwards. Requires uv | Package name, flags and variable names in the taylorwilsdon/google_workspace_mcp README |
| Databricks Genie | `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_GENIE_SPACE_ID` | Managed MCP over HTTP: `/api/2.0/mcp/genie/{space_id}` | Managed MCP is in preview; URL patterns have changed before |
| Databricks UC functions | above + `DATABRICKS_UC_CATALOG`, `DATABRICKS_UC_SCHEMA` | `/api/2.0/mcp/functions/{catalog}/{schema}`; all functions allowed because you defined them | Schema-level vs function-level URL form |
| Databricks vector search | above + `DATABRICKS_VS_CATALOG`, `DATABRICKS_VS_SCHEMA` | `/api/2.0/mcp/vector-search/...` | Renamed AI Search (`/ai-search/`); the older prefix is documented as working |
| Azure DevOps | `AZURE_DEVOPS_ORG` | `npx @azure-devops/mcp <org> -d core work work-items repositories wiki`; browser sign-in. No server read-only flag, so the suite's policy is the control | Package and `-d` flag; maintainers recommend their remote server going forward |
| Jira / Confluence | `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN` (+ optional Confluence variables) | Community `ghcr.io/sooperset/mcp-atlassian` with `READ_ONLY_MODE=true` | Image tag; whether `CONFLUENCE_URL` needs `/wiki` |
| Local files | One or more folders, chosen in Settings | Built into the suite (no Node.js or other install). Tools: list, search, read and file info, all read-only. Paths are resolved, symlinks included, and must stay inside the chosen folders. Reads text, CSV, JSON, YAML, PDF, DOCX and XLSX. Works offline | Nothing external |

## Several accounts (Microsoft 365 and Google Workspace)

One connector serves every account you sign in with, for example a work and a personal mailbox. You decide which accounts agents may use:

| Connector | Sign in each account | List the accounts agents may use |
|---|---|---|
| Microsoft 365 | Run `npx -y @softeria/ms-365-mcp-server --login` once per account | `MS365_ACCOUNTS`, comma-separated, default first |
| Google Workspace | Automatic: the first read for an address opens your browser for Google sign-in | `USER_GOOGLE_EMAIL` (default) plus `GOOGLE_OTHER_ACCOUNTS`, comma-separated |

What the suite does with the list:
- Every step that uses the connector tells the agent which accounts are connected and asks it to say which account each fact came from.
- A call that names no account goes to the default account.
- A call to an account that is not listed is refused before it reaches the server, and the run shows the refusal.
- With no list, the server decides: Microsoft 365 uses its only or selected account; Google uses `USER_GOOGLE_EMAIL`.

Accounts are matched by email address, ignoring capitalisation.

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
