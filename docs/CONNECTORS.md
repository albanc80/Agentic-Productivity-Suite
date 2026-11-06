# Connector setup

All connectors are MCP servers. The suite starts one the first time a run needs it and keeps it running.

**Set them up in the app:** Settings → Connectors. Every connector starts switched off, and its switch unlocks only once it has everything it needs (or a folder, for Local files); a request to switch on an incomplete connector is refused. Each connector has an On/Off switch and an **Edit** panel with numbered setup steps, a link to the server's own guide, and a field for every value it needs, required fields first (secrets are write-only), and **Test** lists which tools are allowed or blocked. Values are saved in the suite's local database (unencrypted) and shared by connectors that use the same name, so the Databricks host and token are entered once. An environment variable with the same name takes precedence over a value typed in the app. **Reset to file defaults** removes the app's settings for that connector. In offline mode, connectors that need the internet are paused; Local files keeps working.

Launch commands come from each project's documentation and change between releases. Confirm the item in **Verify** before relying on a connector.

| Connector | You set | Notes | Verify |
|---|---|---|---|
| GitHub | `GITHUB_PERSONAL_ACCESS_TOKEN` (fine-grained, read-only). Optional `GITHUB_HOST` (GitHub Enterprise Server or `ghe.com` only; leave blank for github.com), `GITHUB_REPOS` (the repositories you work in, told to agents), `GITHUB_TOOLSETS` | Runs `ghcr.io/github/github-mcp-server` in Docker with `GITHUB_READ_ONLY=1`. For github.com the token is enough: tools take the owner and repository on each call, and the token decides which repositories can be read | Image name and variables in the github/github-mcp-server README |
| Microsoft 365 | Nothing to type: press **Sign in with Microsoft** in Edit (see [Sign in from the app](#sign-in-from-the-app-microsoft-365)). Optional `MS365_MCP_ORG_MODE=1` (work or school account, set before signing in), `MS365_MCP_PRESET` (default `personal`). `MS365_ACCOUNTS` is filled in by each sign-in | Community server `@softeria/ms-365-mcp-server` via `npx` with `--read-only --preset personal`: Outlook mail and calendar, OneDrive files, contacts, To Do, OneNote, search. `MS365_MCP_PRESET=work` (with org mode) adds Teams, SharePoint and shared mailboxes. Work tenants may need admin consent | Package name, `--preset` names and `MS365_MCP_ORG_MODE` in its README and PRESETS.md |
| Google Workspace | `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `USER_GOOGLE_EMAIL`. Optional `GOOGLE_OTHER_ACCOUNTS` (several accounts), `WORKSPACE_MCP_PORT` (default 8000), `GOOGLE_WORKSPACE_TOOL_TIER` (default `core`) | Community server `workspace-mcp` via `uvx` with `--read-only --tools gmail calendar drive docs sheets slides tasks contacts`. Create an OAuth client in Google Cloud and enable those APIs; for a Web application client add `http://localhost:8000/oauth2callback` as a redirect URI. The first read opens your browser for Google sign-in; run the step again afterwards. Requires uv | Package name, flags and variable names in the taylorwilsdon/google_workspace_mcp README |
| Databricks (one connector) | `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, then any of: `DATABRICKS_GENIE_SPACE_ID` (Genie space); `DATABRICKS_UC_CATALOG` + `DATABRICKS_UC_SCHEMA` (Unity Catalog functions); `DATABRICKS_VS_CATALOG` + `DATABRICKS_VS_SCHEMA` (Vector Search) | Managed MCP over HTTP, one endpoint per service: `/api/2.0/mcp/genie/{space_id}`, `/api/2.0/mcp/functions/{catalog}/{schema}` (all functions allowed because you defined them), `/api/2.0/mcp/vector-search/{catalog}/{schema}`. Each service turns on when its fields are filled in; tools are listed as `<service>.<tool>`. Replaces the three separate Databricks connectors of earlier versions (their values and switch carry over) | Managed MCP is in preview; URL patterns have changed before, and Vector Search is also called AI Search (`/ai-search/`) |
| Azure DevOps | `AZURE_DEVOPS_ORG` | `npx @azure-devops/mcp <org> -d core work work-items repositories wiki`; browser sign-in. No server read-only flag, so the suite's policy is the control | Package and `-d` flag; maintainers recommend their remote server going forward |
| Jira / Confluence | `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN` (+ optional Confluence variables) | Community `ghcr.io/sooperset/mcp-atlassian` with `READ_ONLY_MODE=true` | Image tag; whether `CONFLUENCE_URL` needs `/wiki` |
| Local files | One or more folders, chosen in Settings | Built into the suite (no Node.js or other install). Used by playbook steps and by chat agents (on models with tool calling). Tools: list, search, read and file info, all read-only. Paths are resolved, symlinks included, and must stay inside the chosen folders. Reads text, CSV, JSON, YAML, PDF, DOCX and XLSX. Works offline | Nothing external |

## Several accounts (Microsoft 365 and Google Workspace)

One connector serves every account you sign in with, for example a work and a personal mailbox. You decide which accounts agents may use:

| Connector | Sign in each account | List the accounts agents may use |
|---|---|---|
| Microsoft 365 | Press **Add another account** in Edit for each account (or run `npx -y @softeria/ms-365-mcp-server --login` in a terminal) | `MS365_ACCOUNTS`, comma-separated, default first. Each sign-in from the app adds its account; **Sign out** removes it |
| Google Workspace | Automatic: the first read for an address opens your browser for Google sign-in | `USER_GOOGLE_EMAIL` (default) plus `GOOGLE_OTHER_ACCOUNTS`, comma-separated |

What the suite does with the list:
- Every step that uses the connector tells the agent which accounts are connected and asks it to say which account each fact came from.
- A call that names no account goes to the default account.
- A call to an account that is not listed is refused before it reaches the server, and the run shows the refusal.
- With no list, the server decides: Microsoft 365 uses its only or selected account; Google uses `USER_GOOGLE_EMAIL`.

Accounts are matched by email address, ignoring capitalisation.

## Sign in from the app (Microsoft 365)

Microsoft 365 no longer needs a terminal. In Settings → Connectors → Microsoft 365 → Edit:

1. Press **Sign in with Microsoft**. The first time, the app downloads the connector (Node.js 20+ must be installed), which can take a minute.
2. The app shows a code. Press **Open the Microsoft sign-in page** (this also copies the code), paste the code, sign in and accept the read-only permissions. The page can be opened on any device, a phone included.
3. The app notices when you are done: it adds the account to the accounts agents may use, records the sign-in and switches the connector on.

**Add another account** signs in the next one; the first stays the default. **Sign out** next to an account deletes its sign-in from the connector and stops agents using it; signing out the last account switches the connector off. Accounts signed in earlier from a terminal are listed too, with **Use them** to allow them.

How it works and what it does not do:
- The suite runs the connector's own launch command with `--login` added, with the same arguments and environment. So the sign-in asks for exactly the permissions the connector uses (`--read-only` and the preset) and lands in the token cache the connector reads.
- The connector's server keeps the tokens in its own cache (the system keychain when available). The suite reads only the printed code, the JSON result and the account list; it never sees, stores or logs a token, and the code is not written to the audit log. The audit log records `connector_signin_started`, `connector_signed_in` and `connector_signed_out`.
- The code lasts 15 minutes; after that the sign-in stops and **Sign in** gives a new code. Offline mode blocks sign-in.
- A `connectors.yaml` copied by an earlier version gets the sign-in automatically as long as its Microsoft 365 launch command and arguments are unchanged; a changed launch is left alone.
- Behind a proxy that inspects TLS, the connector (and so the sign-in) needs the proxy and certificate variables, which stdio connectors do not inherit today. Add them to the connector's `env` in `connectors.yaml`, for example `NODE_EXTRA_CA_CERTS: ${NODE_EXTRA_CA_CERTS:-}`.
- Other connectors can use the same mechanism with a `signin:` block (`provider`, `login`, `accounts`, `remove`, `confirms`) if their server signs in with a device code and prints JSON results like this one.

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
