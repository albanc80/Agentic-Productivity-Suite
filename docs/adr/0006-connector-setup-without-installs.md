# ADR 0006: Connector setup without installs or terminals

Status: accepted · 2026-11-06

## Context
Setting up connectors took a terminal (Microsoft 365 sign-in), a Google Cloud project (Google Workspace), and separate installs of Node.js, uv and Docker. The installers should not grow by shipping those tools, and the suite should not become the holder of mailbox tokens.

## Decision
- **Sign-in from Settings, run by the connector's own server.** The suite runs the server's own sign-in (Microsoft: `--login` device code; Google: its `start_google_auth` tool and local callback) with the connector's own launch command, so the sign-in asks for the connector's read-only permissions and lands in the server's own token store. The suite reads only the printed prompt, results, account lists, and whether a credentials file exists; it never reads a token. Agents cannot call sign-in tools (not read-only).
- **OAuth client as a file.** Google's client comes from a JSON file: uploaded in Settings (wins), next to `connectors.yaml`, or built into installers from a CI secret. Values typed in the app or set in the environment still override it.
- **Runtimes: the computer's copy, then the installer, then first use.** uv, Node.js and the GitHub server program are used from the computer when new enough. Otherwise the installer runs the app with `--install-tools` (never failing the install), and the app downloads on first use as a fallback. Downloads are pinned and checked against SHA-256 values committed in `backend/app/runtimes.py`.
- **No Docker.** GitHub runs GitHub's own server binary; Jira/Confluence runs the same server from PyPI through uv. Configurations still using the shipped Docker launch are upgraded on load.

## Consequences
- A fresh install needs no prerequisites; the installers stay the same size.
- The suite depends on how each server signs in and stores sign-ins (listed in each connector's `verify:`). Server packages stay unpinned, as before; the runtimes are pinned and must be bumped deliberately (new version and checksum).
- The install step runs with administrator rights and cannot see per-user installs (nvm, uv's own installer), so it may download a duplicate; the app still prefers the user's copy at run time.
- Sign-out deletes the local sign-in; revoking access at Microsoft or Google stays with the person.
