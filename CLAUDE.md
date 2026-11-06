# Working in this repository

## Every pull request raises the app version

A merge to `main` publishes a GitHub Release with the installers only when it raises the version, so every PR bumps it:

- **Patch** (0.7.0 → 0.7.1) for fixes and docs; **minor** (0.7.0 → 0.8.0) for features; major only when asked.
- One command writes all five places (`backend/app/__init__.py`, `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json`):

  ```bash
  python scripts/version.py set 0.8.0
  ```

- CI's `version-bump` check fails a PR whose version is not higher than the base branch's or whose files disagree. If a PR is already open when another one merges first, raise the version again.
- If the branch's earlier PR was merged, start again from the latest `main` before bumping.

## Before pushing

```bash
cd backend && uv run --group dev pytest -q && uv run --group dev ruff check .
```

```bash
cd frontend && npm run typecheck && npm run build
```
