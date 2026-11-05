"""Readable copies of chats and deliverables in the user's Documents folder.

The suite's database stays in its own app folder: it holds API keys and connector secrets, and Documents
is often synced to a cloud drive. What lands here is plain Markdown and HTML a person can open, search and
back up:

    <Documents>/Agentic-Suite-Outputs/
        Chats/   one Markdown transcript per chat, rewritten after every message
        Runs/    each finished playbook deliverable, as .md and .html
        Files/   files asked for in chat ("as an HTML file", "export to markdown") or saved with Save to folder

Restricted chats and runs are not copied: that data class must stay on this computer, and a synced
Documents folder may not. A write that fails (disk full, folder removed, file locked) is logged and never
breaks a chat or a run.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

from .export import to_html

FOLDER_NAME = "Agentic-Suite-Outputs"
README = """# Agentic Suite outputs

The Agentic Productivity Suite saves readable copies of your work here.

- Chats: one Markdown transcript per chat, updated after every message. Deleting a chat in the app deletes it here.
- Runs: each finished playbook deliverable, as Markdown and as an HTML page.
- Files: files you asked for in chat, or saved with the Save to folder button under an answer.

Chats and runs marked Restricted are not copied here; they stay inside the app.
The app keeps working if you move or delete this folder: it is created again on the next start.
"""
log = logging.getLogger("suite.outputs")


def documents_dir() -> Path:
    """The user's Documents folder, where the operating system says it is (it may be redirected)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            from uuid import UUID

            class GUID(ctypes.Structure):
                _fields_ = [("data", ctypes.c_byte * 16)]

            folder = GUID()
            ctypes.memmove(folder.data, UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7").bytes_le, 16)  # FOLDERID_Documents
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder), 0, wintypes.HANDLE(0), ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                if path:
                    return Path(path)
        except Exception:  # noqa: BLE001 - fall back to the usual location
            pass
    elif sys.platform.startswith("linux"):
        conf = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "user-dirs.dirs"
        try:
            m = re.search(r'^XDG_DOCUMENTS_DIR="?([^"\n]+)"?', conf.read_text(encoding="utf-8"), re.M)
            if m:
                return Path(m.group(1).replace("$HOME", str(Path.home())))
        except OSError:
            pass
    return Path.home() / "Documents"


def default_outputs_dir() -> Path:
    return documents_dir() / FOLDER_NAME


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60] or "untitled"


def _tail(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", item_id)[-8:] or "item"


class Outputs:
    """Writes the copies. ``root=None`` turns the feature off."""

    def __init__(self, root: Path | None, theme_dir: Path | None = None):
        self.root = root
        self.theme_dir = theme_dir
        self.last_run_files: dict[str, Path | None] = {}

    def ensure(self) -> str | None:
        """Create the folder tree. Returns a readable problem, or None when all is well."""
        if not self.root:
            return None
        try:
            for sub in ("Chats", "Runs", "Files"):
                (self.root / sub).mkdir(parents=True, exist_ok=True)
            readme = self.root / "README.md"
            if not readme.exists():
                readme.write_text(README, encoding="utf-8")
        except OSError as e:
            log.warning("outputs folder %s is not writable: %s", self.root, e)
            return f"The outputs folder {self.root} could not be created ({e.strerror or e}); chats and deliverables stay in the app only."
        return None

    def _write(self, path: Path, text: str) -> Path | None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)  # never leave a half-written file behind
            return path
        except OSError as e:
            log.warning("could not write %s: %s", path, e)
            return None

    def _remove(self, folder: str, item_id: str) -> None:
        if not self.root:
            return
        for p in (self.root / folder).glob(f"*-{_tail(item_id)}.*"):
            try:
                p.unlink()
            except OSError as e:
                log.warning("could not remove %s: %s", p, e)

    # ------------------------------------------------------------ chats

    def save_chat(self, chat: dict, agent_name: Callable[[str], str]) -> Path | None:
        if not self.root:
            return None
        self._remove("Chats", chat["id"])  # the title, and so the file name, can change after the first message
        if chat.get("data_class") == "restricted":
            return None
        lines = [f"# {chat.get('title') or 'Chat'}", "",
                 f"Agent: {agent_name(chat.get('agent_id', ''))} · Data class: {chat.get('data_class', '')} · "
                 f"Started: {str(chat.get('created_at', ''))[:16].replace('T', ' ')} · "
                 f"Updated: {str(chat.get('updated_at', ''))[:16].replace('T', ' ')}", "", "---", ""]
        for m in chat.get("messages", []):
            when = str(m.get("at", ""))[:16].replace("T", " ")
            if m.get("role") == "user":
                lines += [f"**You** · {when}", "", m.get("content", "")]
                if m.get("files"):
                    lines += ["", "Attached: " + ", ".join(f["name"] for f in m["files"])]
            else:
                who = agent_name(m.get("agent", ""))
                lines += [f"**{who}** · {when}" + (f" · {m['model']}" if m.get("model") else ""), "", m.get("content", "")]
            lines += ["", "---", ""]
        name = f"{str(chat.get('created_at', ''))[:10]}-{_slug(chat.get('title', ''))}-{_tail(chat['id'])}.md"
        return self._write(self.root / "Chats" / name, "\n".join(lines))

    def delete_chat(self, cid: str) -> None:
        self._remove("Chats", cid)

    def save_file(self, chat: dict, name: str, fmt: str, markdown: str) -> Path | None:
        """A file the person asked for in chat, next to the other files, never overwriting a different one."""
        if not self.root or chat.get("data_class") == "restricted":
            return None
        body = markdown if fmt == "md" else to_html(markdown, Path(name).stem.replace("-", " ").capitalize(), self.theme_dir)
        stem, suffix = Path(name).stem, Path(name).suffix
        path, n = self.root / "Files" / name, 2
        while path.exists() and path.read_text(encoding="utf-8", errors="replace") != body:
            path, n = self.root / "Files" / f"{stem}-{n}{suffix}", n + 1
        return self._write(path, body)

    # ------------------------------------------------------------ runs

    def save_run(self, run: dict) -> Path | None:
        if not self.root or not run or not run.get("deliverable") or run.get("data_class") == "restricted":
            return None
        title = run.get("title") or "Deliverable"
        stem = f"{str(run.get('created_at', ''))[:10]}-{_slug(title)}-{_tail(run['id'])}"
        md = self._write(self.root / "Runs" / f"{stem}.md", run["deliverable"])
        html = self._write(self.root / "Runs" / f"{stem}.html", to_html(run["deliverable"], title, self.theme_dir))
        self.last_run_files = {"md": md, "html": html}
        return md
