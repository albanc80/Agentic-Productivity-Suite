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
]
for pkg in ("anthropic", "openai", "mcp", "markdown_it"):
    datas += collect_data_files(pkg)

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
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ProductivitySuite", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ProductivitySuite")
