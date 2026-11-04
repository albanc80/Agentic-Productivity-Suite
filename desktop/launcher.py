#!/usr/bin/env python3
"""Desktop launcher: runs the Agentic Productivity Suite locally in its own window.

    python desktop/launcher.py              # native window (pywebview), falls back to the browser
    python desktop/launcher.py --offline    # local models and local files only
    python desktop/launcher.py --headless   # server only; prints the URL

Everything runs on this computer: the server binds to 127.0.0.1 on a free port.
Your settings and data live in ~/.productivity-suite (override with
SUITE_USER_DIR) and survive upgrades of the app.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def user_dir() -> Path:
    return Path(os.environ.get("SUITE_USER_DIR") or Path.home() / ".productivity-suite")


def first_run(udir: Path, root: Path) -> None:
    """Copy editable configuration into the user folder once; never overwrite."""
    udir.mkdir(parents=True, exist_ok=True)
    (udir / "data").mkdir(exist_ok=True)
    for src, dst in [("suite.example.yaml", "suite.yaml"), ("connectors.example.yaml", "connectors.yaml"),
                     ("profile.example.yaml", "profile.yaml")]:
        target = udir / dst
        if not target.exists():
            shutil.copyfile(root / "config" / src, target)


def _ensure_streams(udir: Path) -> None:
    """Windowed builds (no console) have no stdout/stderr; send output to a log file instead."""
    if sys.stdout is None or sys.stderr is None:
        log = open(udir / "suite.log", "a", buffering=1, encoding="utf-8")  # noqa: SIM115 - lives for the process
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_healthy(url: str, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise SystemExit(f"The suite did not start within {timeout:.0f} seconds.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the Agentic Productivity Suite locally.")
    ap.add_argument("--offline", action="store_true", help="local models and local files only")
    ap.add_argument("--headless", action="store_true", help="run the server without opening a window")
    ap.add_argument("--browser", action="store_true", help="open the default browser instead of a native window")
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()

    root, udir = bundle_root(), user_dir()
    first_run(udir, root)
    _ensure_streams(udir)
    os.environ.update({
        "SUITE_HOME": str(root),
        "SUITE_CONFIG": str(udir / "suite.yaml"),
        "SUITE_CONNECTORS": str(udir / "connectors.yaml"),
        "SUITE_PROFILE": str(udir / "profile.yaml"),
        "SUITE_DATA_DIR": str(udir / "data"),
        "SUITE_UI_DIR": str(root / "frontend" / "dist"),
        "SUITE_NO_AUTOAPP": "1",
    })
    if args.offline:
        os.environ["SUITE_OFFLINE"] = "1"
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(root / "backend"))

    import uvicorn

    from app.main import create_app

    port = args.port or free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, name="suite-server", daemon=True)
    thread.start()
    wait_healthy(url)
    print(f"Agentic Productivity Suite running at {url}  (data: {udir})", flush=True)

    try:
        if args.headless:
            while thread.is_alive():
                time.sleep(0.5)
        elif not args.browser and _open_window(url):
            pass  # returns when the window is closed
        else:
            webbrowser.open(url)
            print("Press Ctrl+C to stop.", flush=True)
            while thread.is_alive():
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    return 0


def _open_window(url: str) -> bool:
    try:
        import webview  # pywebview
    except ImportError:
        print("pywebview is not installed; opening your browser instead.", flush=True)
        return False
    icon = bundle_root() / "desktop" / "assets" / ("icon.ico" if sys.platform == "win32" else "icon.png")
    if sys.platform == "win32":
        # Own taskbar identity, so Windows shows the app's icon rather than a generic or Python one.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ProductivitySuite.Desktop")
        except Exception:  # noqa: BLE001 - cosmetic only
            pass
    try:
        webview.create_window("Agentic Productivity Suite", url, width=1360, height=900, min_size=(420, 640))
        webview.start(icon=str(icon) if icon.is_file() else None)
        return True
    except Exception as e:  # noqa: BLE001 - no GUI backend available
        print(f"Native window unavailable ({e}); opening your browser instead.", flush=True)
        return False


if __name__ == "__main__":
    sys.exit(main())
