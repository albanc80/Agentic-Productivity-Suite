# Desktop, offline and mobile use

## Install

Installers are built by GitHub Actions (`.github/workflows/desktop-build.yml`). Binaries are not stored in the repository.

- **Pull requests and manual runs:** open the workflow run under the repository's **Actions** tab and download the `productivity-suite-windows-msi` or `productivity-suite-linux-deb` artifact (a zip containing the installer).
- **Releases:** both installers are attached to a GitHub Release. Releases are automatic: merge a pull request that raises the version in `backend/app/__init__.py` (and the four other version fields), and the merge to `main` builds, tests and publishes `v<version>`. Merges that keep the version are not released. You can still publish by hand by pushing a tag such as `v0.1.0`, or by running the *Desktop installers* workflow manually on `main` (Actions → Desktop installers → Run workflow) with `release_tag` set to `v<version>`; the tag must match `backend/app/__init__.py`.

Every build is checked before upload. The packaged app is started headless and offline and must serve the UI and complete a Well Plan Review casing calculation (`desktop/smoke_test.py`). The installer is then installed, the installed app is smoke-tested the same way, and it is uninstalled again.

| OS | File | Install | Remove |
|---|---|---|---|
| Windows 10/11 (x64) | `ProductivitySuite-<version>-x64.msi` | Double-click, or `msiexec /i ProductivitySuite-<version>-x64.msi`. Installs to *Program Files\Agentic Productivity Suite* with a Start menu shortcut. Installing over an installed copy replaces it (see Upgrading). | Settings → Apps |
| Ubuntu 22.04+ / Debian 12+ (amd64) | `productivity-suite_<version>_amd64.deb` | `sudo apt install ./productivity-suite_<version>_amd64.deb`, then run `productivity-suite` or use the app menu. A newer version upgrades in place (see Upgrading). | `sudo apt remove productivity-suite` |

Settings and data stay in your home folder (`.productivity-suite`) and survive uninstalling and upgrading.

### Upgrading

Never uninstall first: install the new file over the old one.

- **Windows:** double-click the new `.msi`. It replaces the installed copy, including a build with the same version number (for example a build from a pull request before the version is raised), so Apps always shows one entry. If the app is open, the installer asks it to close and ends it after 10 seconds; start it again from the Start menu. Installing an older version over a newer one is refused.
- **Linux:** `sudo apt install ./productivity-suite_<version>_amd64.deb` upgrades a lower version in place. For a rebuild with the same version, add `--reinstall` (apt otherwise reports it as already installed). If the app is running, restart it after the upgrade.
- Your settings, keys, chats, runs and the outputs folder are kept.

Every build checks this: CI installs the last published release, installs the new build over it, and then a second build of the same version over that. It passes only if exactly one installed copy of the new version remains, the installed app passes its smoke test, and uninstalling leaves nothing behind.

- **Windows:** the installer is not code-signed yet, so SmartScreen may warn ("More info" → "Run anyway"). See [CODE_SIGNING.md](CODE_SIGNING.md). The native window uses the Edge WebView2 runtime, which ships with current Windows 10 and 11.
- **Linux:** the `.deb` opens the suite in its own window, using the GTK WebKit your distribution provides. The package does not carry GTK or WebKit (it stays about 35 MB): installing it with the App Center or `sudo apt install ./productivity-suite_<version>_amd64.deb` looks for `python3-gi`, `gir1.2-gtk-3.0` and `gir1.2-webkit2-4.1` and downloads only what is missing (a normal Ubuntu desktop has most of them). With plain `dpkg -i`, run `sudo apt-get install -f` afterwards to fetch them. If no window can be opened, it opens your browser and `~/.productivity-suite/suite.log` says why. CI installs the package on Ubuntu 22.04 and checks that the window opens (`productivity-suite --check-window`).

## Desktop app (Windows, macOS, Linux)

The suite runs as a local desktop app: a native window around the same UI, with the server bound to `127.0.0.1` on a free port. Nothing is exposed to the network.

Run from source:

```bash
cd backend && uv sync --group desktop
```

```bash
cd backend && uv run python ../desktop/launcher.py
```

Options: `--offline` (local models and local files only), `--browser` (open the default browser instead of a native window), `--headless` (server only), `--check-window` (open the window, close it once the app has loaded, exit 0; 1 if no window could open).

Build a standalone app on each target OS (PyInstaller does not cross-compile):

```bash
cd frontend && npm ci && npm run build
```

```bash
cd backend && uv sync --group desktop && uv run pyinstaller ../desktop/productivity-suite.spec --noconfirm
```

The result is `backend/dist/ProductivitySuite/`. To package it, use `desktop/linux/build_deb.sh` (Linux) or `wix build desktop\windows\productivity-suite.wxs` (Windows; see the workflow for the exact arguments). Run `ProductivitySuite` (or `ProductivitySuite.exe`). A Linux build of this spec was produced and run headless in offline mode, including a Well Plan Review run with the casing calculator. Windows and macOS builds have not been tested yet.

- **Everything you change day to day is set up in the app:** Settings → Models, Connectors (including Local files folders), Profile, and Policies & budgets. The files in `~/.productivity-suite/` only set the starting defaults.
- **Settings and data** live in `~/.productivity-suite/` (`suite.yaml`, `connectors.yaml`, `profile.yaml`, `data/`). They are created on first run and kept across upgrades. Override the location with `SUITE_USER_DIR`.
- **Windows** needs the Microsoft Edge WebView2 runtime for the native window. It ships with current Windows 10 and 11; without it the launcher opens the browser.
- **Linux** uses the distribution's GTK WebKit for the native window, run by the system's own Python (the app's bundled Python cannot load the distribution's GTK). The `.deb` depends on those packages; when run from source, install `python3-gi` and `gir1.2-webkit2-4.1`. To test: `productivity-suite --check-window`.
- The app is not code-signed. macOS Gatekeeper and Windows SmartScreen will warn until you sign it.

## Outputs folder

On first start the app creates **Agentic-Suite-Outputs** in your Documents folder (on Windows, wherever Windows says Documents is, including a folder redirected to OneDrive). It keeps readable copies of your work there:

- `Chats/`: one Markdown transcript per chat, updated after every message. Deleting a chat in the app deletes its copy.
- `Runs/`: every finished playbook deliverable, as `.md` and `.html`.
- `Files/`: files you ask for in chat ("as an HTML file", "export to markdown", "save the previous answer as notes.md") or save with **Save to folder** under an answer.

Chats and runs marked **Restricted** are not copied, because Documents may be synced to a cloud drive. The app's database, with your settings, keys and full history, stays in `~/.productivity-suite`. Choose the folder in **Settings → Policies & budgets → Outputs folder**: paste a full path, go back to the default, or switch it off; it applies at once, without a restart. `outputs_dir` in `suite.yaml` or `SUITE_OUTPUTS_DIR` only set the starting default. Exports from runs and chat answers are written here, and the app shows each file's location.

## Agent instructions (agent pack)

The installers carry the agents' full instructions, personas and lineage encrypted
(`registry/agent-pack.enc`), with the key the build took from the `AGENT_PACK_KEY` repository secret.
The app decrypts them in memory and never shows them; **Settings → System → Agent instructions** says
**Built in**. Nothing to do.

**Your own version:** **Import my own version** on that card takes a `.zip` (files under its `agents/`
folder are used) or the agents' `.yaml` files. Each file is checked against the catalog before anything is
written, saved to `~/.productivity-suite/private-registry/agents`
(`%USERPROFILE%\.productivity-suite\private-registry\agents` on Windows) readable only by you, and used at
once. An imported file replaces the built-in instructions for that agent only. **Remove imported pack** deletes the imported
files and goes back to the built-in instructions at once (do this after an update that ships new ones,
or an older import keeps overriding them).

A build made without the secret (or the app run from source) has no key: agents work from their public
capability summary and Settings shows a notice.

**For the owner** (from `backend/`): `uv run python ../scripts/agent_pack.py genkey --key-file <path>` makes a
key; `encrypt <pack.zip> --key-file <path>` rewrites `registry/agent-pack.enc` (commit it, raise the version);
`check` and `decrypt` open it again. Put the key in the `AGENT_PACK_KEY` repository secret (Settings → Secrets
and variables → Actions) and keep it and the plain pack backed up privately. The build fails if the secret
does not open the committed pack. This hides the text from the public repository and the app's screens; it
does not stop someone who unpacks an installer and extracts the key (ADR 0007).

## Offline mode

Switch it from the app: the **Online / Offline** switch in the top bar, or Settings → Connection mode. The choice is saved and survives restarts; **Use config default** returns to the file setting. You can also set the default with `offline: true` in `suite.yaml`, `SUITE_OFFLINE=1`, or `--offline` on the launcher. When offline:

- cloud providers (OpenAI, DeepSeek, OpenRouter, Anthropic) are unavailable, whatever keys are set;
- connectors that need the internet are switched off; `local-files` stays available (`network: false`);
- fonts and UI assets are bundled, so the UI makes no external requests.

Runs then need a local model: switch on Ollama, LM Studio or vLLM in Settings → Model providers (Edit sets the address, key and models), or add an endpoint on your network. Without one, agent steps stop with "No model configured". Local models give weaker results than large cloud models, especially for long multi-step playbooks. Check output quality with `scripts/run_evals.py` on the models you plan to use.

## Installable web app

When served on `localhost` or over HTTPS, the UI can be installed from Chrome or Edge ("Install app"). A service worker caches only the UI shell; runs, approvals and settings always come from the server.

## Models served from a phone or another device

Some phones can serve a small model (roughly 2B–4B parameters) through an app or tool that exposes an OpenAI-compatible API, for example llama.cpp's `llama-server`, or Ollama under Termux on Android. Check what your device and app support; this has not been tested on real phones here. The suite does not load or configure these models. It only connects to them:

1. On the phone, start the model server and make it listen on the network (not only on `127.0.0.1`). Note the phone's IP address and port.
2. In the suite: Settings → Model endpoints → enter the address (e.g. `192.168.1.42:8080`) → **Find models** → pick the model, set its context window to what the server uses, tick the tiers it should serve first → **Add endpoint**.
3. **Test** checks the connection. The endpoint is then tried first for the ticked tiers, and kept as a fallback for every other tier.

The same works for a laptop or workstation running Ollama, LM Studio or vLLM on your network.

- **Locality is decided by the address.** Only localhost, private-network ranges (10.x, 172.16–31.x, 192.168.x, link-local, IPv6 unique-local) and `.local` names count as local. Only local endpoints can receive `restricted` data, or be used in offline mode. Any other address is treated as cloud.
- **Small models are weak on long playbooks.** By default nothing is cut, so a model too small for an agent's whole prompt is skipped (the step says why); switch on **Shorten prompts for small models** in Settings → Policies & budgets to trim prompts to fit them (the run notes list every cut). Tool calling is off unless you tick it. Use them for quick asks, routing and short steps, and check quality with `scripts/run_evals.py`.

## Mobile

There is no native mobile app, and a phone cannot run the whole suite on its own: the orchestration server and the calculators run on a computer. The phone can be the screen, the model, or both. Ways to use it:

1. **Phone as a screen for a computer on the same network.** Start the server with a token and bind it to the LAN:

   ```bash
   SUITE_API_TOKEN=<long-random-token> SUITE_HOST=0.0.0.0 ./scripts/dev.sh
   ```

   Then open `http://<computer-ip>:8765` on the phone and enter the token. This needs no internet if the computer runs local models. `scripts/dev.sh` refuses to bind beyond localhost without a token. Installing it as an app on a phone requires HTTPS (for example a reverse proxy with a certificate trusted by the phone).

2. **Phone as the model.** Add the phone's model server as an endpoint (above). The suite on your computer sends it the work, and the phone can also be the screen.

3. **Hosted deployment** behind your organisation's identity provider. This is out of scope for the MVP.

Running the orchestration server itself on the phone is not supported. Small phone models handle short steps; long playbooks such as Well Plan Review need a larger model.
