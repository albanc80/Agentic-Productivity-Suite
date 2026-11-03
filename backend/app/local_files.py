"""Built-in "Local files" connector: read-only access to folders the user picks in Settings.

It runs inside the suite as an in-process MCP server, so it needs no Node.js or
other install and works in offline mode. Every path is resolved (following
symlinks) and must stay inside one of the chosen folders; nothing can be
written, moved or deleted. PDF, Word and Excel files are returned as text with
the same extractor used for uploads.
"""

from __future__ import annotations

import fnmatch
import os
from datetime import UTC, datetime
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .files import MAX_BYTES, UnsupportedFile, extract_text

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
MAX_LIST = 500
MAX_SEARCH = 200
MAX_WALK = 20_000
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "$RECYCLE.BIN", "System Volume Information"}


class FolderError(ToolError, ValueError):
    """A path or folder problem. Shown to the agent (and in Settings) as a plain message."""


def check_folder(raw: str) -> Path:
    """Validate a folder chosen in Settings: it must exist, be a directory and not be a whole drive."""
    text = (raw or "").strip().strip('"')
    if not text:
        raise FolderError("enter a folder path")
    p = Path(os.path.expandvars(os.path.expanduser(text)))
    if not p.is_absolute():
        raise FolderError(f"{text}: use a full path, for example C:\\Users\\you\\Documents\\Reports or /home/you/reports")
    try:
        p = p.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise FolderError(f"{text}: folder not found") from e
    if not p.is_dir():
        raise FolderError(f"{text}: not a folder")
    if p == Path(p.anchor):
        raise FolderError(f"{text}: choose a folder, not a whole drive")
    return p


class Roots:
    def __init__(self, folders: list[str]):
        self.roots: list[Path] = []
        for f in folders:
            try:
                self.roots.append(check_folder(f))
            except FolderError:
                continue  # a folder removed since it was chosen is skipped, not fatal

    def resolve(self, path: str | None) -> Path:
        """Map a tool path (absolute, or relative to the first folder, or '<folder name>/...') inside the roots."""
        if not self.roots:
            raise FolderError("no folders are shared; choose one in Settings > Connectors > Local files")
        raw = (path or "").strip().strip('"')
        if not raw or raw in (".", "/"):
            return self.roots[0]
        cand = Path(raw)
        if not cand.is_absolute():
            head = cand.parts[0]
            named = next((r for r in self.roots if r.name == head), None)
            cand = (named.parent if named else self.roots[0]) / cand
        try:
            real = cand.resolve(strict=True)
        except (OSError, RuntimeError) as e:
            raise FolderError(f"{raw}: not found") from e
        if not any(real == r or real.is_relative_to(r) for r in self.roots):
            raise FolderError(f"{raw}: outside the shared folders")
        return real

    def show(self, p: Path) -> str:
        for r in self.roots:
            if p == r or p.is_relative_to(r):
                rel = p.relative_to(r)
                return r.name if str(rel) == "." else f"{r.name}/{rel.as_posix()}"
        return p.name


def _when(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def build_server(folders: list[str]) -> MCPServer:
    roots = Roots(folders)
    server = MCPServer("local-files")

    @server.tool(annotations=READ_ONLY)
    def list_allowed_directories() -> str:
        """List the folders shared with agents. Paths in other tools are relative to these (e.g. 'Reports/q3.pdf')."""
        if not roots.roots:
            return "No folders are shared."
        return "\n".join(f"{r.name}  ({r})" for r in roots.roots)

    @server.tool(annotations=READ_ONLY)
    def list_directory(path: str = "") -> str:
        """List files and subfolders in a shared folder. Empty path = the first shared folder."""
        d = roots.resolve(path)
        if not d.is_dir():
            raise FolderError(f"{path}: not a folder")
        rows = []
        for i, e in enumerate(sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))):
            if i >= MAX_LIST:
                rows.append(f"[... more than {MAX_LIST} entries]")
                break
            try:
                st = e.stat()
            except OSError:
                continue
            rows.append(f"[dir]  {e.name}/" if e.is_dir() else f"[file] {e.name}  {st.st_size:,} bytes  {_when(st.st_mtime)}")
        return f"{roots.show(d)}:\n" + ("\n".join(rows) or "(empty)")

    @server.tool(annotations=READ_ONLY)
    def search_files(pattern: str, path: str = "") -> str:
        """Find files whose name matches a pattern such as '*.pdf' or '*budget*', searching subfolders."""
        base = roots.resolve(path)
        pat = pattern.strip() or "*"
        if not any(c in pat for c in "*?["):
            pat = f"*{pat}*"
        hits, seen = [], 0
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [n for n in dirnames if n not in SKIP_DIRS and not n.startswith(".")]
            for n in filenames:
                seen += 1
                if fnmatch.fnmatch(n.lower(), pat.lower()):
                    hits.append(roots.show(Path(dirpath) / n))
                    if len(hits) >= MAX_SEARCH:
                        return "\n".join(hits) + f"\n[stopped at {MAX_SEARCH} matches]"
            if seen > MAX_WALK:
                hits.append(f"[stopped after scanning {MAX_WALK:,} files]")
                break
        return "\n".join(hits) or "No matching files."

    @server.tool(annotations=READ_ONLY)
    def read_file(path: str) -> str:
        """Read a file as text. Supports text, CSV, JSON, YAML, PDF, DOCX and XLSX."""
        f = roots.resolve(path)
        if not f.is_file():
            raise FolderError(f"{path}: not a file")
        if f.stat().st_size > MAX_BYTES:
            raise FolderError(f"{path}: larger than {MAX_BYTES // (1024 * 1024)} MB")
        try:
            _, text = extract_text(f.name, f.read_bytes())
        except UnsupportedFile as e:
            raise FolderError(str(e)) from e
        return text

    @server.tool(annotations=READ_ONLY)
    def get_file_info(path: str) -> str:
        """Size, type and modified time of a file or folder."""
        f = roots.resolve(path)
        st = f.stat()
        kind = "folder" if f.is_dir() else "file"
        return f"{roots.show(f)}: {kind}, {st.st_size:,} bytes, modified {_when(st.st_mtime)}"

    return server
