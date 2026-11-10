#!/usr/bin/env python3
"""Desktop launcher: runs the Agentic Productivity Suite locally in its own window.

    python desktop/launcher.py              # native window (pywebview), falls back to the browser
    python desktop/launcher.py --check-window  # open the window, close it once the app has loaded (self-test)
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
import subprocess
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


def install_tools(root: Path, remove: bool = False) -> int:
    """Installer and uninstaller step: uv and Node.js for connectors, in <app>/tools (see app/runtimes.py).
    Runs with administrator rights and no window, before anyone opened the app: it touches no user folder.
    Always exits 0 so a failed download never fails the install; the app retries the first time it is needed."""
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(root / "backend"))
    from app import runtimes

    dest = root / "tools"
    if remove:
        runtimes.remove_for_app(dest)
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    lines = runtimes.install_for_app(dest)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(dest / "install.log", "a", encoding="utf-8") as log:
        log.writelines(f"{stamp} {line}\n" for line in lines)
    for line in lines:
        print(line, flush=True)
    return 0


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
    ap.add_argument("--check-window", action="store_true",
                    help="open the native window, close it once the app has loaded, and exit 0 (1 if no window)")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--install-tools", action="store_true",
                    help="(run by the installer) get uv and Node.js for connectors if this computer lacks them, then exit")
    ap.add_argument("--remove-tools", action="store_true", help="(run by the uninstaller) delete them, then exit")
    args = ap.parse_args()

    if args.install_tools or args.remove_tools:
        return install_tools(bundle_root(), remove=args.remove_tools)

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
    # The private agent layer is never bundled; it is read from the user folder when present.
    os.environ.setdefault("SUITE_PRIVATE_REGISTRY", str(udir / "private-registry"))
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

    if args.check_window:
        ok = _open_window(url, check=True)
        server.should_exit = True
        thread.join(timeout=10)
        print("Native window: " + ("OK" if ok else "unavailable (the app would open in the browser)"), flush=True)
        return 0 if ok else 1

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


def _app_window():
    """desktop/app_window.py: the window itself, shared with the system-Python helper on Linux."""
    try:
        import app_window
    except ImportError:  # loaded by path (tests), not run as a script
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import app_window
    return app_window


def keep_in_app(window, app_url: str, open_browser=webbrowser.open) -> bool:
    return _app_window().keep_in_app(window, app_url, open_browser)


def _icon() -> Path:
    return bundle_root() / "desktop" / "assets" / ("icon.ico" if sys.platform == "win32" else "icon.png")


def _open_window(url: str, check: bool = False) -> bool:
    """Show the app in its own window until it is closed. False when no native window could be opened."""
    icon = _icon()
    if sys.platform == "win32":
        # Own taskbar identity, so Windows shows the app's icon rather than a generic or Python one.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ProductivitySuite.Desktop")
        except Exception:  # noqa: BLE001 - cosmetic only
            pass
    if not (sys.platform.startswith("linux") and not _has_linux_toolkit()):
        try:
            _app_window().run_window(url, str(icon) if icon.is_file() else None, check)
            return True
        except Exception as e:  # noqa: BLE001 - pywebview missing, or no GUI toolkit in this process
            print(f"Native window unavailable in the app itself ({type(e).__name__}: {e}).", flush=True)
    if sys.platform.startswith("linux"):
        return _system_window(url, icon, check)
    return False


def _has_linux_toolkit() -> bool:
    """GTK (gi) or Qt (qtpy) importable in this process: true when run from source on a desktop with them installed,
    false in the packaged app, which then goes straight to the system Python (and logs no pywebview traceback)."""
    import importlib.util
    return any(importlib.util.find_spec(m) is not None for m in ("gi", "qtpy"))


# Linux: the bundled app carries pywebview (pure Python) but not GTK or WebKit. The distribution provides those for
# its own Python (python3-gi, gir1.2-webkit2-4.1: dependencies of the .deb), so the window runs in that Python.
GTK_PROBE = ("import gi; gi.require_version('Gtk', '3.0')\n"
             "try:\n    gi.require_version('WebKit2', '4.1')\nexcept ValueError:\n    gi.require_version('WebKit2', '4.0')\n"
             "from gi.repository import Gtk, WebKit2")


def _system_env() -> dict[str, str]:
    """The environment for a system program started from the bundled app. PyInstaller points LD_LIBRARY_PATH at the
    bundle's own libraries (saving the person's value in LD_LIBRARY_PATH_ORIG); a system Python must not load them."""
    env = dict(os.environ)
    for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "GI_TYPELIB_PATH", "GIO_MODULE_DIR", "GDK_PIXBUF_MODULE_FILE"):
        env.pop(k, None)
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if getattr(sys, "frozen", False) or orig is not None:
        if orig:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def _system_pythons(bindir: str = "/usr/bin") -> list[str]:
    """python3 first, then each installed python3.N, newest first: python3 may point at a version the distribution's
    GTK bindings were not built for (seen on Ubuntu 24.04 with python3 switched to 3.13)."""
    found = [f"{bindir}/python3"] if os.path.exists(f"{bindir}/python3") else []
    versions = []
    for p in Path(bindir).glob("python3.*"):
        tail = p.name[len("python3."):]
        if tail.isdigit():
            versions.append((int(tail), str(p)))
    return found + [p for _v, p in sorted(versions, reverse=True)]


def _system_python(env: dict[str, str], run=subprocess.run) -> str | None:
    for py in _system_pythons():
        try:
            if run([py, "-s", "-c", GTK_PROBE], env=env, capture_output=True, timeout=30).returncode == 0:
                return py
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def _system_window(url: str, icon: Path, check: bool, run=subprocess.run) -> bool:
    root = bundle_root()
    script, libs = root / "desktop" / "app_window.py", root / "desktop" / "pyweb"
    if not script.is_file() or not libs.is_dir():
        return False  # not a packaged build: run from source with a GUI toolkit installed instead
    env = _system_env()
    py = _system_python(env, run)
    if not py:
        print("No system Python with GTK and WebKit (packages python3-gi and gir1.2-webkit2-4.1); "
              "opening the browser instead.", flush=True)
        return False
    cmd = [py, "-s", str(script), "--libs", str(libs), url]
    if icon.is_file():
        cmd += ["--icon", str(icon)]
    if check:
        cmd.append("--check")
    print(f"Opening the window with {py} (GTK).", flush=True)
    return run(cmd, env=env, stdout=_fileno(sys.stdout), stderr=_fileno(sys.stderr)).returncode == 0


def _fileno(stream):
    """The windowed app writes to suite.log: hand the helper the same file, so its messages land there too."""
    try:
        return stream.fileno()
    except (AttributeError, OSError, ValueError):
        return None


if __name__ == "__main__":
    sys.exit(main())
