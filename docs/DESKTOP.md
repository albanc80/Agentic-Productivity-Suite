# Desktop, offline and mobile use

## Desktop app (Windows, macOS, Linux)

The suite runs as a local desktop app: a native window around the same UI, with the server bound to `127.0.0.1` on a free port. Nothing is exposed to the network.

Run from source:

```bash
cd backend && uv sync --group desktop
```

```bash
cd backend && uv run python ../desktop/launcher.py
```

Options: `--offline` (local models and local files only), `--browser` (open the default browser instead of a native window), `--headless` (server only).

Build a standalone app on each target OS (PyInstaller does not cross-compile):

```bash
cd frontend && npm ci && npm run build
```

```bash
cd backend && uv sync --group desktop && uv run pyinstaller ../desktop/productivity-suite.spec --noconfirm
```

The result is `backend/dist/ProductivitySuite/`. Run `ProductivitySuite` (or `ProductivitySuite.exe`). A Linux build of this spec was produced and run headless in offline mode, including a Well Plan Review run with the casing calculator. Windows and macOS builds have not been tested yet.

- **Settings and data** live in `~/.productivity-suite/` (`suite.yaml`, `connectors.yaml`, `profile.yaml`, `data/`). They are created on first run and kept across upgrades. Override the location with `SUITE_USER_DIR`.
- **Windows** needs the Microsoft Edge WebView2 runtime for the native window. It ships with current Windows 10 and 11; without it the launcher opens the browser.
- **Linux** needs GTK or Qt WebKit libraries for the native window; otherwise it opens the browser.
- The app is not code-signed. macOS Gatekeeper and Windows SmartScreen will warn until you sign it.

## Offline mode

Set `offline: true` in `suite.yaml`, export `SUITE_OFFLINE=1`, or pass `--offline` to the launcher. Then:

- cloud providers (OpenAI, DeepSeek, OpenRouter, Anthropic) are unavailable, whatever keys are set;
- connectors that need the internet are switched off; `local-files` stays available (`network: false`);
- fonts and UI assets are bundled, so the UI makes no external requests.

Runs then need a local model (Ollama, LM Studio or vLLM, enabled in `suite.yaml`) or fall back to the labelled demo provider. Local models give weaker results than large cloud models, especially for long multi-step playbooks. Check output quality with `scripts/run_evals.py` on the models you plan to use.

## Installable web app

When served on `localhost` or over HTTPS, the UI can be installed from Chrome or Edge ("Install app"). A service worker caches only the UI shell; runs, approvals and settings always come from the server.

## Mobile

There is no native mobile app, and a phone cannot run the suite on its own: the server, the agents' models and the calculators run on a computer. Two workable options:

1. **Phone as a screen for a computer on the same network.** Start the server with a token and bind it to the LAN:

   ```bash
   SUITE_API_TOKEN=<long-random-token> SUITE_HOST=0.0.0.0 ./scripts/dev.sh
   ```

   Then open `http://<computer-ip>:8765` on the phone and enter the token. This needs no internet if the computer runs local models. `scripts/dev.sh` refuses to bind beyond localhost without a token. Installing it as an app on a phone requires HTTPS (for example a reverse proxy with a certificate trusted by the phone).
2. **Hosted deployment** behind your organisation's identity provider. This is out of scope for the MVP.

Fully on-device phone use (local model plus suite on the phone) is not planned. Current phone-class models are too small for these playbooks to be reliable.
