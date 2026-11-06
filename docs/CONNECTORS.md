# Connector setup

All connectors are MCP servers. The suite starts one the first time a run needs it and keeps it running.

**Set them up in the app:** Settings → Connectors. Every connector starts switched off, and its switch unlocks only once it has everything it needs (or a folder, for Local files); a request to switch on an incomplete connector is refused. Each connector has an On/Off switch and an **Edit** panel with numbered setup steps, a link to the server's own guide, and a field for every value it needs, required fields first (secrets are write-only), and **Test** lists which tools are allowed or blocked. Values are saved in the suite's local database (unencrypted) and shared by connectors that use the same name, so the Databricks host and token are entered once. An environment variable with the same name takes precedence over a value typed in the app. **Reset to file defaults** removes the app's settings for that connector. In offline mode, connectors that need the internet are paused; Local files keeps working.

Launch commands come from each project's documentation and change between releases. Confirm the item in **Verify** before relying on a connector.

| Connector | You set | Notes | Verify |
|---|---|---|---|
| GitHub | `GITHUB_PERSONAL_ACCESS_TOKEN` (fine-grained, read-only). Optional `GITHUB_HOST` (GitHub Enterprise Server or `ghe.com` only; leave blank for github.com), `GITHUB_REPOS` (the repositories you work in, told to agents), `GITHUB_TOOLSETS` | GitHub's own server program `github-mcp-server stdio --read-only --toolsets …` (no Docker; [provided by the app](#runtimes-uv-nodejs-and-the-github-server) when the computer has none). For github.com the token is enough: tools take the owner and repository on each call, and the token decides which repositories can be read | The `stdio` command, `--read-only`/`--toolsets` flags and variables in the github/github-mcp-server README |
| Microsoft 365 | Nothing to type: press **Sign in with Microsoft** in Edit (see [Sign in from the app](#sign-in-from-the-app-microsoft-365)). Optional `MS365_MCP_ORG_MODE=1` (work or school account, set before signing in), `MS365_MCP_PRESET` (default `personal`). `MS365_ACCOUNTS` is filled in by each sign-in | Community server `@softeria/ms-365-mcp-server` via `npx` with `--read-only --preset personal`: Outlook mail and calendar, OneDrive files, contacts, To Do, OneNote, search. `MS365_MCP_PRESET=work` (with org mode) adds Teams, SharePoint and shared mailboxes. Work tenants may need admin consent | Package name, `--preset` names and `MS365_MCP_ORG_MODE` in its README and PRESETS.md |
| Google Workspace | Nothing to type when the app has a [built-in Google client](#built-in-google-client): enter your address and press **Sign in with Google** in Edit (see [Sign in from the app](#sign-in-from-the-app-google-workspace)). Without one: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` from your own client. `USER_GOOGLE_EMAIL` and `GOOGLE_OTHER_ACCOUNTS` are filled in by each sign-in. Optional `WORKSPACE_MCP_PORT` (default 8000), `GOOGLE_WORKSPACE_TOOL_TIER` (default `core`) | Community server `workspace-mcp` via `uvx` with `--read-only --tools gmail calendar drive docs sheets slides tasks contacts`. uv is [provided by the app](#runtimes-uv-nodejs-and-the-github-server) when the computer has none | Package name, flags, variable names, the `start_google_auth` tool and the credentials folder in the taylorwilsdon/google_workspace_mcp README and source |
| Databricks (one connector) | `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, then any of: `DATABRICKS_GENIE_SPACE_ID` (Genie space); `DATABRICKS_UC_CATALOG` + `DATABRICKS_UC_SCHEMA` (Unity Catalog functions); `DATABRICKS_VS_CATALOG` + `DATABRICKS_VS_SCHEMA` (Vector Search) | Managed MCP over HTTP, one endpoint per service: `/api/2.0/mcp/genie/{space_id}`, `/api/2.0/mcp/functions/{catalog}/{schema}` (all functions allowed because you defined them), `/api/2.0/mcp/vector-search/{catalog}/{schema}`. Each service turns on when its fields are filled in; tools are listed as `<service>.<tool>`. Replaces the three separate Databricks connectors of earlier versions (their values and switch carry over) | Managed MCP is in preview; URL patterns have changed before, and Vector Search is also called AI Search (`/ai-search/`) |
| Azure DevOps | `AZURE_DEVOPS_ORG` | `npx @azure-devops/mcp <org> -d core work work-items repositories wiki`; browser sign-in. No server read-only flag, so the suite's policy is the control | Package and `-d` flag; maintainers recommend their remote server going forward |
| Jira / Confluence | `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN` (+ optional Confluence variables) | Community server `mcp-atlassian` from PyPI via `uvx` with `--read-only` (no Docker; uv comes from the computer or the app) | Package name and variables in the sooperset/mcp-atlassian README; whether `CONFLUENCE_URL` needs `/wiki` |
| Local files | One or more folders, chosen in Settings | Built into the suite (no Node.js or other install). Used by playbook steps and by chat agents (on models with tool calling). Tools: list, search, read and file info, all read-only. Paths are resolved, symlinks included, and must stay inside the chosen folders. Reads text, CSV, JSON, YAML, PDF, DOCX and XLSX. Works offline | Nothing external |

## Several accounts (Microsoft 365 and Google Workspace)

One connector serves every account you sign in with, for example a work and a personal mailbox. You decide which accounts agents may use:

| Connector | Sign in each account | List the accounts agents may use |
|---|---|---|
| Microsoft 365 | Press **Add another account** in Edit for each account (or run `npx -y @softeria/ms-365-mcp-server --login` in a terminal) | `MS365_ACCOUNTS`, comma-separated, default first. Each sign-in from the app adds its account; **Sign out** removes it |
| Google Workspace | Enter the next address and press **Add another account** in Edit | `USER_GOOGLE_EMAIL` (default) plus `GOOGLE_OTHER_ACCOUNTS`, comma-separated. Each sign-in from the app adds its account; **Sign out** removes it |

What the suite does with the list:
- Every step that uses the connector tells the agent which accounts are connected and asks it to say which account each fact came from.
- A call that names no account goes to the default account.
- A call to an account that is not listed is refused before it reaches the server, and the run shows the refusal.
- With no list, the server decides: Microsoft 365 uses its only or selected account; Google uses `USER_GOOGLE_EMAIL`.

Accounts are matched by email address, ignoring capitalisation.

## Sign in from the app (Microsoft 365)

Microsoft 365 no longer needs a terminal. In Settings → Connectors → Microsoft 365 → Edit:

1. Press **Sign in with Microsoft**. The first time, the app downloads the connector, which can take a minute. Node.js comes from the computer or the app (see [Runtimes](#runtimes-uv-nodejs-and-the-github-server)).
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

## Sign in from the app (Google Workspace)

In Settings → Connectors → Google Workspace → Edit, enter your Google address under **Sign-in** and press **Sign in with Google**:

1. The app starts the connector (the first run downloads it, which can take a minute; uv comes from the computer or the app) and a Google page opens in the browser on this computer. If it does not, use the link the app shows.
2. Sign in and allow read-only access. With a client that Google has not verified, Google shows a warning first: choose **Advanced**, then continue.
3. Google sends you back to the connector on this computer (`http://localhost:8000/oauth2callback`). The app notices the new sign-in, fills in the address, and switches the connector on.

Sign in on the computer running the app: the return address is that computer, so a phone cannot finish a Google sign-in. **Add another account**, **Sign out** and **Use them** (accounts signed in earlier) work as for Microsoft 365. Google may sign in a different account than the address you typed; the app records the one Google signed in.

How it works:
- The Google server has no sign-in command, so the suite starts it and calls its own `start_google_auth` tool. Agents cannot: the tool is not read-only, so the suite's policy hides it from them; only the sign-in code calls it, directly.
- While signing in, the server runs with `--tool-tier complete` added (it lists its sign-in tool only in that tier). The permissions Google is asked for come from `--tools` and `--read-only`, so they are the same read-only scopes the connector uses: checked against the real server, they are `gmail.readonly`, `calendar.readonly`, `drive.readonly`, `documents.readonly`, `spreadsheets.readonly`, `presentations.readonly`, `tasks.readonly`, `contacts.readonly` and the basic profile.
- The server's callback saves the account's credentials as one file per address in `~/.google_workspace_mcp/credentials` (or `WORKSPACE_MCP_CREDENTIALS_DIR`). The suite sees the file appear; it never opens it. **Sign out** deletes that file. It does not revoke the app's access at Google: do that at https://myaccount.google.com/permissions if you want it gone there too.
- A sign-in waits up to 10 minutes. Offline mode blocks it.

## Built-in Google client

Every Google user normally needs their own OAuth client from Google Cloud. A built-in client removes that: the app reads `google-oauth-client.json`, the file Google Cloud downloads for an OAuth client (Credentials → your client → **Download JSON**), and uses its ID and secret when none is typed in Settings or set in the environment. The Client ID and secret fields then say **Built into this app**.

**Upload it in the app:** Settings → Connectors → Google Workspace → Edit → **Upload client file**. The app checks it is an OAuth client file, saves it in its data folder readable only by you, and uses it from then on (**Replace** and **Remove** are next to it). The upload is audited with the client ID; the secret is never shown or logged.

Where the app looks, first match wins: a file uploaded in Settings (the data folder), the folder of `connectors.yaml` (`~/.productivity-suite` for the desktop app), then `config/` in the app folder (where installers put a built-in one). The file is git-ignored; never commit it.

Installers: add the file's contents as the repository secret `GOOGLE_OAUTH_CLIENT_JSON` (GitHub → Settings → Secrets and variables → Actions). The installer build writes it into `config/` before packaging (`desktop/bundle_oauth_client.py`), so everyone who installs that build signs in without any Google Cloud setup. Without the secret the build still succeeds, with no built-in client. A malformed secret fails the build.

What to know about sharing a client:
- A Desktop app client's secret is not confidential by Google's own design for installed apps: anyone with the installer can read it. It lets them sign in to *their own* Google account through your client; it gives no access to yours.
- Google's limits for an unverified client: in **Testing**, only the test users you list can sign in and each sign-in expires after 7 days; **In production** without verification, people see the "not verified" warning and the number of users is capped (100, at the time of writing). Check Google's current rules for both.
- Everyone who signs in through the client counts against its quota, and you can see and revoke its use in your Google Cloud project.

## Runtimes (uv, Node.js and the GitHub server)

Connectors run their servers with `uvx` (Google Workspace, Jira and Confluence), `npx` (Microsoft 365, Azure DevOps) or GitHub's own `github-mcp-server` program (GitHub). No connector needs Docker. Nobody has to install any of these, and the installers do not ship them:

1. **The computer's own copy is used** when it is new enough (Node.js 20 or newer, uv 0.5 or newer, github-mcp-server 2.0 or newer). Nothing is duplicated, and a copy newer than the app's always wins.
2. **Otherwise the installer gets it.** At the end of the install, the `.msi` and the `.deb` run the app once with `--install-tools`: it checks the computer and downloads what is missing or too old into the app's folder (`_internal/tools`), and writes what it did to `install.log` there. A failed download (offline, a proxy) never fails the install. Uninstalling deletes these copies; an upgrade keeps them.
3. **Otherwise the app downloads it** the first time a connector needs it, into the data folder (`~/.productivity-suite/data/tools`), with no administrator rights. Opening Settings never triggers a download.

Every download is a pinned release from the project's own site (uv 0.11.32 and github-mcp-server 2.0.3 from their GitHub releases, Node.js v24.22.2 LTS from nodejs.org), checked against the SHA-256 in `backend/app/runtimes.py` before anything is unpacked, and unpacked only inside its own folder. To move to newer releases, change the versions and checksums there. uv fetches the Python it needs by itself.

Earlier versions ran GitHub and Jira/Confluence in Docker. A `connectors.yaml` that still launches them the shipped Docker way is upgraded when the app loads it (values typed in the app and environment variables are untouched); one whose launch you changed is left alone.

Limits: the install step runs as the installer (SYSTEM on Windows, root on Linux), so it sees machine-wide installs (for example the Node.js installer) but not a copy installed for one user only (nvm, uv's own installer). In that case it downloads a copy anyway; the app still prefers yours, because it checks your PATH first.

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
