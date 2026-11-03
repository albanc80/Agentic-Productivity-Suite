"""SQLite persistence: runs, steps, approvals, uploaded files, settings and audit trail.

Everything a run needs to resume after a gate lives here, so a restart of the
server does not lose paused runs. Prompts are stored only when
``store_prompts`` is on; otherwise only their size and hash are kept.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .guards import redact

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, playbook_id TEXT NOT NULL, title TEXT, status TEXT NOT NULL, outcome TEXT,
  data_class TEXT NOT NULL, inputs TEXT NOT NULL, options TEXT NOT NULL DEFAULT '{}',
  cursor INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0,
  demo INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '[]', deliverable TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step_id TEXT NOT NULL, parent TEXT, kind TEXT NOT NULL,
  agent TEXT, title TEXT, status TEXT NOT NULL, provider TEXT, model TEXT, attempt INTEGER NOT NULL DEFAULT 1,
  tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0, latency_ms INTEGER DEFAULT 0,
  prompt_chars INTEGER DEFAULT 0, prompt TEXT, output TEXT, deliverable TEXT, warnings TEXT NOT NULL DEFAULT '[]',
  tool_calls TEXT NOT NULL DEFAULT '[]', error TEXT, started_at TEXT, ended_at TEXT
);
CREATE INDEX IF NOT EXISTS steps_run ON steps(run_id);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step_id TEXT NOT NULL, title TEXT NOT NULL, instructions TEXT,
  required_role TEXT, payload TEXT, status TEXT NOT NULL, decided_by TEXT, note TEXT, edited TEXT,
  created_at TEXT NOT NULL, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, media_type TEXT, chars INTEGER, text TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, run_id TEXT, event TEXT NOT NULL, detail TEXT
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.db.execute(sql, args)

    def _row(self, sql: str, args: tuple = ()) -> dict | None:
        r = self._exec(sql, args).fetchone()
        return dict(r) if r else None

    def _rows(self, sql: str, args: tuple = ()) -> list[dict]:
        return [dict(r) for r in self._exec(sql, args).fetchall()]

    # ------------------------------------------------------------ audit / settings

    def audit(self, event: str, run_id: str | None = None, **detail: Any) -> None:
        self._exec("INSERT INTO audit(ts, run_id, event, detail) VALUES (?,?,?,?)",
                   (now(), run_id, event, redact(json.dumps(detail, default=str))))

    def audit_log(self, run_id: str | None = None, limit: int = 500) -> list[dict]:
        if run_id:
            return self._rows("SELECT * FROM audit WHERE run_id=? ORDER BY id", (run_id,))
        return self._rows("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))

    def get_setting(self, key: str, default: Any = None) -> Any:
        r = self._row("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(r["value"]) if r else default

    def set_setting(self, key: str, value: Any) -> None:
        self._exec("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, json.dumps(value)))

    # ------------------------------------------------------------ runs

    def create_run(self, playbook_id: str, title: str, data_class: str, inputs: dict, options: dict) -> str:
        rid = new_id("run")
        t = now()
        self._exec("INSERT INTO runs(id, playbook_id, title, status, data_class, inputs, options, created_at, updated_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?)",
                   (rid, playbook_id, title, "queued", data_class, json.dumps(inputs), json.dumps(options), t, t))
        return rid

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        for k in ("notes", "inputs", "options"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k])
        fields["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), run_id))

    def add_run_usage(self, run_id: str, tokens: int, cost: float) -> None:
        self._exec("UPDATE runs SET tokens=tokens+?, cost_usd=cost_usd+?, updated_at=? WHERE id=?",
                   (tokens, cost, now(), run_id))

    def run(self, run_id: str) -> dict | None:
        r = self._row("SELECT * FROM runs WHERE id=?", (run_id,))
        if r:
            for k in ("inputs", "options", "notes"):
                r[k] = json.loads(r[k])
            r["demo"] = bool(r["demo"])
        return r

    def runs(self, limit: int = 100) -> list[dict]:
        rows = self._rows("SELECT id, playbook_id, title, status, outcome, data_class, tokens, cost_usd, demo, "
                          "created_at, updated_at FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))
        for r in rows:
            r["demo"] = bool(r["demo"])
        return rows

    def delete_runs(self, run_ids: list[str]) -> int:
        """Delete runs with their steps and approvals. The audit trail is kept."""
        if not run_ids:
            return 0
        marks = ",".join("?" * len(run_ids))
        args = tuple(run_ids)
        with self.lock:
            self.db.execute("BEGIN")
            self.db.execute(f"DELETE FROM steps WHERE run_id IN ({marks})", args)  # noqa: S608 - placeholders only
            self.db.execute(f"DELETE FROM approvals WHERE run_id IN ({marks})", args)  # noqa: S608
            n = self.db.execute(f"DELETE FROM runs WHERE id IN ({marks})", args).rowcount  # noqa: S608
            self.db.execute("COMMIT")
        return n

    def demo_run_ids(self) -> list[str]:
        """Runs made by the demo provider of earlier versions."""
        return [r["id"] for r in self._rows("SELECT id FROM runs WHERE demo=1")]

    def add_note(self, run_id: str, note: str) -> None:
        r = self.run(run_id)
        if r is not None and note not in r["notes"]:
            self.update_run(run_id, notes=r["notes"] + [note])

    # ------------------------------------------------------------ steps

    def start_step(self, run_id: str, step_id: str, kind: str, *, parent: str | None = None, agent: str | None = None,
                   title: str | None = None, attempt: int = 1) -> str:
        sid = new_id("stp")
        self._exec("INSERT INTO steps(id, run_id, step_id, parent, kind, agent, title, status, attempt, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (sid, run_id, step_id, parent, kind, agent, title, "running", attempt, now()))
        return sid

    def finish_step(self, sid: str, **fields: Any) -> None:
        for k in ("warnings", "tool_calls", "output"):
            if k in fields and not isinstance(fields[k], str) and fields[k] is not None:
                fields[k] = json.dumps(fields[k], default=str)
        if "prompt" in fields and fields["prompt"]:
            fields["prompt"] = redact(fields["prompt"])
        fields.setdefault("ended_at", now())
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE steps SET {cols} WHERE id=?", (*fields.values(), sid))

    def steps(self, run_id: str, include_prompts: bool = False) -> list[dict]:
        rows = self._rows("SELECT * FROM steps WHERE run_id=? ORDER BY started_at, rowid", (run_id,))
        for r in rows:
            for k in ("warnings", "tool_calls"):
                r[k] = json.loads(r[k] or "[]")
            r["output"] = json.loads(r["output"]) if r.get("output") else None
            if not include_prompts:
                r.pop("prompt", None)
        return rows

    def latest_step(self, run_id: str, step_id: str) -> dict | None:
        r = self._row("SELECT * FROM steps WHERE run_id=? AND step_id=? ORDER BY rowid DESC LIMIT 1", (run_id, step_id))
        if r:
            r["output"] = json.loads(r["output"]) if r.get("output") else None
            r["warnings"] = json.loads(r["warnings"] or "[]")
        return r

    # ------------------------------------------------------------ approvals

    def create_approval(self, run_id: str, step_id: str, title: str, instructions: str, required_role: str | None,
                        payload: str) -> str:
        aid = new_id("apr")
        self._exec("INSERT INTO approvals(id, run_id, step_id, title, instructions, required_role, payload, status, created_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?)",
                   (aid, run_id, step_id, title, instructions, required_role, payload, "pending", now()))
        return aid

    def approvals(self, status: str | None = None, run_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM approvals WHERE 1=1", []
        if status:
            sql += " AND status=?"
            args.append(status)
        if run_id:
            sql += " AND run_id=?"
            args.append(run_id)
        return self._rows(sql + " ORDER BY created_at DESC", tuple(args))

    def approval(self, aid: str) -> dict | None:
        return self._row("SELECT * FROM approvals WHERE id=?", (aid,))

    def decide_approval(self, aid: str, status: str, decided_by: str, note: str, edited: str | None) -> None:
        self._exec("UPDATE approvals SET status=?, decided_by=?, note=?, edited=?, decided_at=? WHERE id=?",
                   (status, decided_by, note, edited, now(), aid))

    # ------------------------------------------------------------ files

    def add_file(self, name: str, media_type: str, text: str) -> dict:
        fid = new_id("file")
        self._exec("INSERT INTO files(id, name, media_type, chars, text, created_at) VALUES (?,?,?,?,?,?)",
                   (fid, name, media_type, len(text), text, now()))
        return {"id": fid, "name": name, "media_type": media_type, "chars": len(text)}

    def file(self, fid: str) -> dict | None:
        return self._row("SELECT * FROM files WHERE id=?", (fid,))
