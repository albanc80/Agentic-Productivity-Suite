# PyInstaller spec: builds a standalone desktop app for the OS it runs on.
#
#   cd frontend && npm ci && npm run build
#   cd ../backend && uv sync --group desktop
#   uv run pyinstaller ../desktop/productivity-suite.spec --noconfirm
#
# Output: backend/dist/ProductivitySuite/ (run ProductivitySuite or ProductivitySuite.exe).
# Build on each target OS; PyInstaller does not cross-compile.
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # repo root
BACKEND = ROOT / "backend"

datas = [
    (str(ROOT / "registry"), "registry"),
    (str(ROOT / "playbooks"), "playbooks"),
    (str(ROOT / "config"), "config"),
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "desktop" / "assets"), "desktop/assets"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE"), "."),
]
for pkg in ("anthropic", "openai", "mcp", "markdown_it"):
    datas += collect_data_files(pkg)

import sys as _sys

if _sys.platform.startswith("linux"):
    # The window runs in the system's Python, which has GTK and WebKit from the distribution (bundling those does
    # not work). It needs the window script and pywebview with its pure-Python dependencies as plain source files.
    import importlib

    # Only what the GTK window needs: pywebview's Windows DLLs, Android jar and other platforms stay out (~1.7 MB).
    # GTK and WebKit themselves are never bundled: the .deb depends on them and apt installs what is missing.
    datas.append((str(ROOT / "desktop" / "app_window.py"), "desktop"))

    def _keep(rel):
        parts = rel.parts
        if "__pycache__" in parts or parts[0] in ("lib", "__pyinstaller"):
            return False
        return parts[0] != "platforms" or (len(parts) == 2 and parts[1] in ("__init__.py", "gtk.py"))

    for mod in ("webview", "proxy_tools", "bottle", "typing_extensions"):
        path = Path(importlib.import_module(mod).__file__)
        if path.name != "__init__.py":
            datas.append((str(path), "desktop/pyweb"))
            continue
        for f in sorted(path.parent.rglob("*")):
            rel = f.relative_to(path.parent)
            if f.is_file() and _keep(rel):
                datas.append((str(f), str(Path("desktop/pyweb") / mod / rel.parent)))

hidden = []
for pkg in ("app", "uvicorn", "mcp", "anthropic", "openai", "pypdf", "docx", "openpyxl", "webview"):
    try:
        hidden += collect_submodules(pkg)
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(BACKEND)],
    datas=datas,
    hiddenimports=hidden,
    # PIL: only desktop/make_icons.py uses Pillow (at build time). pypdf and openpyxl import it optionally, for images;
    # the app reads text only. Leaving it out keeps ~19 MB out of both installers.
    excludes=["tkinter", "pytest", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)
ICON = ROOT / "desktop" / "assets" / "icon.ico"
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ProductivitySuite", console=False,
          icon=str(ICON) if ICON.exists() else None)
coll = COLLECT(exe, a.binaries, a.datas, name="ProductivitySuite")
