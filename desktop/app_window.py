#!/usr/bin/env python3
"""The app's own window (pywebview), shared by every platform.

The launcher imports this module. On Linux the bundled app has no GTK of its own (bundling GTK and WebKit does not
work: WebKit runs helper processes from fixed system paths), so the launcher runs this file with the system's Python,
which has GTK and WebKit from the distribution, and the pure-Python pywebview copied next to it:

    python3 -s app_window.py --libs <dir with pywebview> [--icon icon.png] [--check] http://127.0.0.1:<port>

Exit codes: 0 the window was shown and closed, 3 no native window could be opened (the launcher then opens the
browser), 4 --check timed out before the page loaded.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

TITLE = "Agentic Productivity Suite"
CHECK_TIMEOUT_S = 60


def keep_in_app(window, app_url: str, open_browser=webbrowser.open) -> bool:
    """The app window has no address bar or Back button: a page outside the app (a Google sign-in, a Cloud console
    link) would leave the person stuck. Open it in their browser instead and bring the window back to the app, which
    reopens the page they were on. Returns True when it sent a page to the browser."""
    current = window.get_current_url() or ""
    if not current or current == "about:blank" or current.startswith(app_url):
        return False
    open_browser(current)
    window.load_url(app_url)
    return True


def run_window(url: str, icon: str | None = None, check: bool = False) -> None:
    """Open the window on `url` and return when it is closed. Raises when no native window can be opened.
    With `check`, close it as soon as the page has loaded and print which web view was used (CI and support)."""
    import webview  # pywebview

    # Downloads are off by default in pywebview: without this, Export and Download buttons do nothing.
    webview.settings["ALLOW_DOWNLOADS"] = True
    # text_select: pywebview turns text selection off by default, so answers could not be selected and copied.
    window = webview.create_window(TITLE, url, width=1360, height=900, min_size=(420, 640), text_select=True)

    def loaded(window):  # pywebview passes the window only to a parameter named "window"
        keep_in_app(window, url)
        if check:
            renderer = getattr(getattr(webview, "guilib", None), "renderer", "unknown")
            print(f"WINDOW-LOADED {renderer} {window.get_current_url() or url}", flush=True)
            threading.Timer(0.5, window.destroy).start()

    window.events.loaded += loaded
    if check:
        def give_up():
            print(f"WINDOW-TIMEOUT the page did not load within {CHECK_TIMEOUT_S} s", flush=True)
            os._exit(4)
        timer = threading.Timer(CHECK_TIMEOUT_S, give_up)
        timer.daemon = True  # must not keep the process alive once the window has closed
        timer.start()
    webview.start(icon=icon)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Open the Agentic Productivity Suite window.")
    ap.add_argument("url")
    ap.add_argument("--libs", help="folder holding pywebview and its pure-Python dependencies")
    ap.add_argument("--icon")
    ap.add_argument("--check", action="store_true", help="close once the page has loaded (self-test)")
    args = ap.parse_args(argv)
    if args.libs:
        sys.path.insert(0, args.libs)
    try:
        run_window(args.url, args.icon, args.check)
    except Exception as e:  # noqa: BLE001 - no GTK, no WebKit, no display: the launcher opens the browser
        print(f"Native window unavailable ({type(e).__name__}: {e})", file=sys.stderr, flush=True)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
