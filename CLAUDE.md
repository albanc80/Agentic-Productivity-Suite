# Working in this repository

Read `docs/ENGINEERING_NOTES.md` before changing connectors, sign-in, installers or chat. It records what broke on real installs and why the tests missed it.

## Product rules the owner set (do not change without asking)

- **Least work for the person.** Install the app, press Sign in, done. No terminals, no Docker, no prerequisites to install, no Google Cloud steps for people the app is shared with.
- **Chat: every connector that is on** is available to every agent. **Playbooks: only the connectors the playbook lists** (`connectors:` on its steps).
- Connectors are **read-only**, enforced by the suite (ADR 0003). Sign-in tokens stay with each connector's own server; the app never reads them (ADR 0006).
- **Every pull request raises the version** (below). The owner merges, often with auto-merge; never merge yourself.

## Every pull request raises the app version

A merge to `main` publishes a GitHub Release with the installers only when it raises the version, so every PR bumps it:

- **Patch** (0.7.0 → 0.7.1) for fixes and docs; **minor** (0.7.0 → 0.8.0) for features; major only when asked.
- One command writes all five places (`backend/app/__init__.py`, `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json`):

  ```bash
  python scripts/version.py set 0.8.0
  ```

- CI's `version-bump` check fails a PR whose version is not higher than the base branch's or whose files disagree. If a PR is already open when another one merges first, raise the version again.
- If the branch's earlier PR was merged, start again from the latest `main` before bumping.

## Definition of done (all of it, before saying "done")

Passing unit tests has not been enough here: four bugs in a row reached the owner with green CI. A change is done only when:

1. **Fast checks pass:**

   ```bash
   cd backend && uv run --group dev pytest -q && uv run --group dev ruff check .
   ```

   ```bash
   cd frontend && npm run typecheck && npm run build
   ```

2. **The upgrade path works, not only a fresh install.** The desktop app copies `connectors.yaml` into `~/.productivity-suite/` once and keeps it, and keeps its database. Anything that changes a connector entry must load correctly from **every** file in `backend/tests/fixtures/old-connectors/` (the test does this). When a shipped launch changes, add the old launch to that connector's `legacy:` and add the new `connectors.example.yaml` as a fixture.
3. **The real thing was run**, not only a fake: the real MCP server through the suite (`uvx`, `npx` or the binary), the real CLI output, the real log format. Fakes must copy real behaviour seen in the real server's source or output, including failures (colour codes in logs, slow first start, handshake quirks).
4. **The person's path was walked in a browser** (Playwright, `require('playwright')`), on every screen the change touches, with realistic state: an old config file, connectors on and off, nothing signed in. Check the UI says what the backend now does.
5. **New tests fail without the change** (break the code on purpose once and see the test fail).
6. **Docs and UI text match** (README, `docs/CONNECTORS.md`, setup steps in `config/connectors.example.yaml`, Settings text).
7. Report what was **not** verified (real accounts, Windows-only behaviour) plainly.

## Traps that cost time here

- **"Test" on a connector only starts the server and lists tools.** It works without signing in; it is not proof of a sign-in.
- **MCP clients use `mode="legacy"`** (the classic `initialize` handshake). The SDK default probes `server/discover` first, which broke GitHub's server: `duplicate "initialize" received`.
- **The repo has an `app/tools/` package** (calculators): never add a module named `app/tools.py`.
- **This sandbox needs proxy and CA variables** for `uvx`, `npx` and Node: stdio connectors get a minimal environment, so add `HTTPS_PROXY`, `SSL_CERT_FILE`, `NODE_EXTRA_CA_CERTS`, `UV_NATIVE_TLS` to a test `connectors.yaml` when running real servers here. Anonymous GitHub API calls get 403; use `github.com/.../releases/download/...` URLs.
- **The installer runs as SYSTEM or root; the app runs as the person.** Never `tempfile.mkdtemp` for anything another user must open (on Windows it sets an owner-only access list; `chmod` does not undo it). Test file access as a different user (`su nobody`), not only as the one who installed.
- **Nothing a connector does may escape as a 500.** Catch every exception at the connector boundary (Test, chat, playbooks) and show its type and message. Chat never waits long for, or fails because of, one connector.
- **The real error is in `~/.productivity-suite/suite.log`** on the person's computer (`%USERPROFILE%` on Windows). Ask for its tail before guessing.
- **Force-push is refused by the tool runner.** After a merge, reset the branch to `origin/main`; the next push is a fast-forward.
