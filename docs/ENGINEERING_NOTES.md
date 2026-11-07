# Engineering notes

What we learned building connector sign-in, zero-setup installers and connectors in chat (v0.7.0 to v0.7.3), and what broke on a real install although CI was green. Read this before changing connectors, sign-in, installers or chat. The rules that follow from it are in `CLAUDE.md`.

## How the pieces fit

| Area | Where | What to know |
|---|---|---|
| Connector config | `config/connectors.example.yaml`, `backend/app/connectors.py` | Shipped presets; the desktop app copies the file to `~/.productivity-suite/connectors.yaml` once. `ConnectorManager.from_file` merges presets with that file and upgrades old entries (`_with_shipped_signin`, `legacy:` launches). |
| Values | app database (`connector_values`), environment | Precedence: environment, then typed in the app, then a built-in client file. Nothing personal lives in a connector entry. |
| Read-only | `tool_allowed` in `connectors.py` | Allow-list, `read_only_hint`, or a query-like name. Sign-in tools are hidden from agents; only `signin.py` calls them. |
| Sign-in | `backend/app/signin.py` | `command` kind (Microsoft: `--login` device code, `--list-accounts`, `--remove-account`) and `tool` kind (Google: starts the server with `--tool-tier complete`, calls `start_google_auth`, watches the credentials folder and the server's log in `data/logs/<connector>-signin.log`). |
| Google OAuth client | `client_file:` in the Google entry | `google-oauth-client.json`: uploaded in Settings (data folder, wins), next to `connectors.yaml`, or in `config/` (installers write it from the `GOOGLE_OAUTH_CLIENT_JSON` repository secret via `desktop/bundle_oauth_client.py`). |
| Runtimes | `backend/app/runtimes.py` | uv, Node.js, GitHub's `github-mcp-server`, pinned with SHA-256. Order: the computer's copy if new enough, then `<app>/_internal/tools` (installer, `--install-tools`), then `<data>/tools` (first use). |
| Installers | `desktop/launcher.py`, `desktop/windows/productivity-suite.wxs`, `desktop/linux/build_deb.sh`, `.github/workflows/desktop-build.yml` | `--install-tools` / `--remove-tools` run hidden at install and uninstall and never fail the install. CI installs, upgrades and uninstalls both packages and checks `install.log`. |
| Chat tools | `backend/app/chat.py` | Every connector that is on (`ConnectorManager.tools_for_agent`), max 128 tools, accounts told to the agent. Started in the background at launch (`warm`); chat waits at most `CHAT_CONNECTOR_WAIT` (10 s) and answers without connectors still starting or failed, telling the agent. |
| Playbook tools | `backend/app/engine.py` `_tool_specs` | Only the connectors the step lists (`tools_for_agent(..., only=True)`). |
| UI rules | `frontend/src/connectors.ts`, `pages/SettingsPanels.tsx`, `Chat.tsx`, `Playbooks.tsx`, `RunForm.tsx` | One helper for "on", names, "used by", accounts. |
| Releases | `scripts/version.py`, `version-bump` CI job | Every PR raises the version; a merge to `main` with a new version publishes the release. |

## What broke on a real install, and why the tests missed it

Each of these passed CI and reached the owner.

### 1. Old `connectors.yaml` never got the new sign-in (v0.7.0)
- **Seen:** Microsoft 365 still showed the first release's panel ("Microsoft 365 (Graph)", a "one-time sign-in" checkbox, no Sign in button). GitHub still ran through Docker.
- **Cause:** the upgrade only recognised the launch from the release just before. The owner's file came from the first release.
- **Missed because:** the tests built "old" files by editing today's file, not from real shipped files.
- **Now:** every shipped `connectors.example.yaml` is in `backend/tests/fixtures/old-connectors/` and must load as today's. `legacy:` lists every launch ever shipped.

### 2. Chat agents could not see Gmail (v0.7.0)
- **Seen:** the Chief of Staff said only Local files tools existed.
- **Cause:** chat was hard-wired to Local files; only playbooks offered other connectors.
- **Missed because:** connector work was tested through Settings and playbooks, never by asking a chat agent to use a newly set-up connector.
- **Now:** chat offers every connector that is on. A test uses a connector no playbook names.

### 3. Google sign-in said "failed" (v0.7.0)
- **Seen:** "The sign-in was not finished within 10 minutes" although Test worked. The typed address did not become the default account.
- **Cause:** the app decided "done" only from the credentials file appearing, and stopped listening after 10 minutes. Test only lists tools, so it worked without a sign-in. The default account was only filled after a detected sign-in.
- **Missed because:** the end-to-end test simulated Google by writing the file into a folder the test chose.
- **Now:** the server's own log is read while waiting, so success counts even if the file lands elsewhere, and Google's error shows at once. The log's colour codes are stripped (found only by running the real server). The wait is 15 minutes. The typed address becomes the default when Sign in is pressed, and is replaced if Google signs in another account.

### 4. GitHub: `MCPError: duplicate "initialize" received` (v0.7.0)
- **Cause:** the MCP SDK client probes `server/discover` before `initialize`. GitHub's server (Go SDK, the newest Docker image, slow on first start) took the probe as its session start and refused the `initialize`.
- **Missed because:** the binary was tested, but not the Docker path or a slow start.
- **Now:** connectors use `mode="legacy"`. `tests/fake_strict_server.py` reproduces the exact error with the SDK default.

### 5. The UI did not show the new rules (v0.7.1)
- **Cause:** backend behaviour changed and the screens were not revisited.
- **Now:** v0.7.2 shows the rules in Settings, on playbook cards, on the start form and in chat. Definition of done step 4 (walk every touched screen in a browser).

### 6. GitHub Test and every chat: "Internal Server Error" (v0.7.2, Windows)
- **Seen:** GitHub's Test, and every chat message with GitHub on, answered "Internal Server Error". Microsoft and Google worked. Each failed send also left an empty "New chat" in the list.
- **Cause:** the installer's `--install-tools` runs as SYSTEM and unpacked into a folder made by `tempfile.mkdtemp`. Since Python 3.12.4 (CVE-2024-4030), `mkdtemp` on Windows gives the folder an access list for its maker only, so the person's account could not even check `.complete`: `PermissionError: [WinError 5] Access is denied`. `chmod` does not change Windows access lists. Microsoft and Google used Node and uv already on the computer; GitHub's server had no copy there, so it hit that folder. The `PermissionError` was not a `ConnectorError`, so Test, chat's tool gathering and the chat endpoint all let it escape. Chat also started every connector before answering, so one bad connector stopped every chat. The page then forgot the chat a failed send had made, so the next send made another.
- **Missed because:** CI installs and smoke-tests as the same administrator that installed, and the runner has Node and uv, so only the GitHub folder was made by the install step, and nobody opened it as another user. The tests only raised `ConnectorError` from connectors.
- **Now:** tool folders are made with plain `mkdir` (inheriting the app folder's permissions); the install step resets permissions on folders older installers left (`icacls /reset`); a folder the app cannot open counts as absent and the app downloads its own copy. Any connector failure is a readable 409 on Test, a warning in chat, and a tool error for the agent; unexpected errors anywhere show their type and message and are logged with the trace. Connectors start in the background at launch; chat waits at most 10 s, then answers without the ones still starting and tells the agent. A failed send reuses its chat, and empty chats are not listed. CI checks that the built-in Users group can open every tool folder after the upgrade over the last release. Reproduced on Linux by running the app as `nobody` with a root-only installer folder and the real `github-mcp-server`: v0.7.2 gave 500, the fix lists 22 tools and answers chats.

### 7. Google set-up errors one at a time, and a window with no way back (v0.7.3)
- **Seen:** Google sign-in showed `policy_enforced` (Advanced Protection), then `org_internal` (client audience Internal), then every lookup said the API was not enabled. Clicking the agent's "Enable Gmail API" link opened Google's sign-in inside the app window, which has no address bar or Back button: the app had to be restarted.
- **Cause:** the owner's one-time client setup (External, test users, eight APIs) was not written down. Google stops on its own page for sign-in errors and never calls back, so the app waited silently. Markdown links in answers had no `target`, so pywebview navigated the app window itself (pywebview sends only new-window requests to the browser, `OPEN_EXTERNAL_LINKS_IN_BROWSER`).
- **Now:** the setup steps and an error table are in `docs/CONNECTORS.md`, the sign-in panel lists the errors, and `setup_hints` turns workspace-mcp's "API is not enabled" (and Google's own `accessNotConfigured` text, for People) into a warning with the enable link for the right project, in chat and in run notes. Answer links open in a new window, the page sends every external link to the browser, and the launcher's `keep_in_app` sends any stray outside page to the browser and reloads the app, which reopens the last page (`sessionStorage`).
- **Not testable here:** pywebview itself (no GUI); `keep_in_app` is tested with a fake window, the links in a browser.

### 8. A Google sign-in page on every Gmail lookup (v0.7.4)
- **Seen:** Gmail answers worked, but each query also opened Google's sign-in in the browser.
- **Cause:** the first address typed (an Advanced Protection account Google refused) had become the default account and stayed listed. Calls without an account went to it; workspace-mcp opens a sign-in page (`webbrowser.open`) on every call for an account without credentials. Seen with the real server: `**ACTION REQUIRED: Google Authentication Needed for Google Gmail for '<address>'**`.
- **Missed because:** the sign-in tests covered success and Google's errors, not a listed address that never signed in.
- **Now:** `usable_accounts` keeps only signed-in accounts (credentials files) for tool-kind sign-ins; `_with_account` refuses the others before the server; agents are told which listed accounts are not signed in; Settings names them; `setup_hints` names an account Google asks to sign in again. Verified with the real workspace-mcp and a recording `$BROWSER`: nothing opens.

### Bugs caught before release by running the real thing
These are why "run the real thing" is in the definition of done:
- `start_google_auth` exists only in workspace-mcp's `complete` tier: "Unknown tool" until the sign-in launch added `--tool-tier complete`.
- Downloaded tool folders were `0700` (from `mkdtemp`), so other users could not run tools the installer put there.
- `app/tools.py` was shadowed by the existing `app/tools/` package.
- The sandbox proxy is needed for `uvx` and `npx`; without it, failures look like server crashes ("Connection closed").

## Facts worth keeping

- **Microsoft:** `@softeria/ms-365-mcp-server` prints `To sign in, use a web browser to open the page https://login.microsoft.com/device and enter the code XXXXXXXX to authenticate.` Then it prints a JSON line (`{"success": true, "userData": {...}}`). `--list-accounts` prints `{"accounts": [...]}`. Sign in with the same `--read-only --preset` arguments as the connector, so the scopes match.
- **Google client owner:** audience External, test users listed, and Gmail, Calendar, Drive, People, Docs, Sheets, Slides and Tasks APIs enabled in the client's project. Advanced Protection accounts cannot use an unverified client at all.
- **Google:** `workspace-mcp` saves one credentials file per address in `~/.google_workspace_mcp/credentials` (or `WORKSPACE_MCP_CREDENTIALS_DIR`). Its callback is `http://localhost:8000/oauth2callback`. It logs `OAuth callback: Successfully authenticated user: <address>.` or `Authentication failed: ...`, with ANSI colours. Scopes come from `--tools` and `--read-only`, not the tier.
- **Unverified Google client:** people see a warning. In Testing mode, only listed test users can sign in and sign-ins expire after 7 days.
- **Jira/Confluence:** `uvx mcp-atlassian --read-only`, reading the `JIRA_*` and `CONFLUENCE_*` variables.
- **GitHub:** the `github-mcp-server stdio --read-only --toolsets ...` binary, reading `GITHUB_PERSONAL_ACCESS_TOKEN` and `GITHUB_HOST`. Releases carry a `github-mcp-server_<version>_checksums.txt` file.
- **Install step limits:** it runs as SYSTEM or root, so it cannot see per-user installs (nvm, uv's own installer) and may download a duplicate. The app still prefers the user's copy.
- **Proxies:** stdio connectors do not inherit proxy or certificate variables (open issue). Behind a TLS-inspecting proxy, add them to the connector's `env`.
- **The log:** `~/.productivity-suite/suite.log` (`%USERPROFILE%\.productivity-suite\suite.log`), not the install folder. Windowed builds send stdout and stderr there. Ask for its tail first when a real install fails.

## How to test a connector change for real

1. **Point the app at a test config:** `SUITE_CONNECTORS=<test connectors.yaml>`, `SUITE_DATA_DIR=<scratch>`, `SUITE_OUTPUTS_DIR=off`, then `uv run uvicorn app.main:app --port 8766`. In this sandbox, add the proxy variables to the connector's `env`.
2. **Load the oldest fixture** from `backend/tests/fixtures/old-connectors/` as the config, to check the upgrade.
3. **Drive the screens with Playwright:** Settings → Connectors → Edit → Sign in. Read the panel text, take screenshots, and check the API state (`/api/connectors`, `/api/connectors/<id>/signin`, `/api/audit`).
4. **Exercise the server's real failure path:** for Google, send `http://localhost:8000/oauth2callback?error=access_denied` and expect Google's error in the panel within seconds.
5. **Ask a chat agent** something that needs the connector. Confirm the tool is offered, called, audited and named in the answer's meta line.
