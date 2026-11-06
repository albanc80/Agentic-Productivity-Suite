"""MCP connectors with read-only enforcement in the suite itself.

Each enabled connector gets a worker task that owns one ``mcp.Client`` session
(stdio subprocess or Streamable HTTP) and serves requests from a queue. The MCP
SDK's transports must be entered and exited in the same task, which is why a
worker owns the session instead of request handlers.

Read-only is enforced here regardless of how the server is configured:
  * ``deny_tools`` always wins;
  * if ``allow_tools`` is set, only those tools (glob patterns) are exposed;
  * otherwise a tool is exposed only if it declares ``read_only_hint`` and is
    not destructive, or (when ``infer_read_only``) its name reads as a query
    (get_/list_/search_/read_/...) and contains no write verb.
Blocked tools are never offered to a model, and a direct call to one is refused.
Server-side read-only flags in the presets are a second layer, not the control.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from pydantic import BaseModel, Field

from . import runtimes
from .settings import env_refs, env_vars, expand_env

log = logging.getLogger("suite.connectors")

READ_PREFIX = re.compile(
    r"^(get|list|search|read|query|fetch|describe|find|view|show|retrieve|count|ask|poll|lookup|explain|"
    r"directory_tree|summari[sz]e)(_|-|$)", re.I)
WRITE_WORD = re.compile(
    r"(create|update|delete|remove|write|send|post|merge|push|set|add|close|assign|comment|upload|"
    r"execute|run|trigger|cancel|approve|move|rename|edit|patch|publish|archive|invite|share|reply|forward)",
    re.I)


class AccountsConfig(BaseModel):
    """Several accounts behind one connector (for example a work and a personal mailbox).

    The server picks the account from one tool argument (``param``). The accounts the user allows are
    listed in settings (``vars``, each comma-separated; the first account listed is the default). The
    suite refuses calls to any other account and fills in the default when a call names none.
    """

    param: str
    vars: list[str]


ACCOUNT_SPLIT = re.compile(r"[\s,;]+")


class SigninConfig(BaseModel):
    """Sign-in from the app, run by the connector's own server (see signin.py). The server keeps the tokens;
    the suite never reads them. A successful sign-in adds the account to the connector's account list and sets
    ``confirms`` (the connector's opt-in flag, if it has one).

    ``kind: command`` (Microsoft 365): the suite runs the connector's launch command with extra arguments.
    ``login`` signs one account in (the server prints a link and a code, then a JSON result), ``accounts``
    lists the signed-in accounts as JSON and ``remove`` (followed by an account id) signs one out.

    ``kind: tool`` (Google Workspace): the suite starts the connector's server (with ``login`` added to its
    arguments) and calls its sign-in ``tool`` with ``tool_args`` and the address in ``account_arg``. The tool answers with a sign-in address; the
    server's own callback receives the result and saves the account's credentials as one file per address in
    ``credentials_dir``, which is how the suite sees who is signed in. Signing out deletes that file.
    """

    provider: str  # shown on the button: "Sign in with Microsoft"
    kind: Literal["command", "tool"] = "command"
    login: list[str] = Field(default_factory=list)
    accounts: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
    tool: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    account_arg: str | None = None
    credentials_dir: str | None = None  # ${VAR:-default} and ~ are expanded
    confirms: str | None = None
    timeout_s: float = 960.0  # a device code lasts 15 minutes


def parse_client_file(raw: str | bytes, spec: ClientFileConfig) -> dict[str, str]:
    """The connector variables in an OAuth client file, or ValueError saying what is wrong with it."""
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise ValueError("This is not a JSON file. Use the file Google Cloud downloads for an OAuth client.") from e
    body = (data.get("installed") or data.get("web") or data) if isinstance(data, dict) else None
    if not isinstance(body, dict):
        raise ValueError("This is not an OAuth client file.")
    found = {var: str(body[key]).strip() for key, var in spec.vars.items() if str(body.get(key) or "").strip()}
    missing = [key for key, var in spec.vars.items() if var not in found]
    if missing:
        raise ValueError(f"The file has no {' or '.join(missing)}. Download the OAuth client JSON again.")
    return found


class ClientFileConfig(BaseModel):
    """An OAuth client the app can ship with: a JSON file as Google Cloud downloads it ({"installed": {...}}
    or {"web": {...}}), found by ``name`` in the suite's config folders. ``vars`` maps its keys to the
    connector's variables. A value typed in the app, or an environment variable, still wins."""

    name: str
    vars: dict[str, str]


class ConnectorPart(BaseModel):
    """One service of a grouped connector (for example Genie inside Databricks).

    A grouped connector has one switch and shared values (host, token); each part is its own MCP
    endpoint and turns on once its own values are filled in.
    """

    id: str
    name: str
    description: str = ""
    url: str
    headers: dict[str, str] | None = None  # default: the connector's headers
    allow_tools: list[str] = Field(default_factory=list)
    timeout_s: float | None = None


class Launch(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)


class ConnectorConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    transport: Literal["stdio", "http", "builtin"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = False  # off until the user sets the connector up and switches it on
    allow_tools: list[str] = Field(default_factory=list)
    deny_tools: list[str] = Field(default_factory=list)
    infer_read_only: bool = True
    timeout_s: float = 60.0
    network: bool = True  # needs internet; unavailable in offline mode
    requires: list[str] = Field(default_factory=list)  # extra env vars that must be set (explicit opt-in)
    setup: str = ""
    verify: str = ""  # what to double-check against upstream docs
    folders: list[str] = Field(default_factory=list)  # builtin local-files: folders agents may read
    accounts: AccountsConfig | None = None  # several accounts behind one server
    signin: SigninConfig | None = None  # sign-in from the app (stdio connectors)
    client_file: ClientFileConfig | None = None  # an OAuth client built into the app
    steps: list[str] = Field(default_factory=list)  # numbered setup steps shown in the app
    docs_url: str = ""  # the server's own documentation
    labels: dict[str, str] = Field(default_factory=dict)  # variable -> label shown in the app
    hints: dict[str, str] = Field(default_factory=dict)  # variable -> help line shown under the field
    context: dict[str, str] = Field(default_factory=dict)  # variable -> line told to agents ({value})
    parts: list[ConnectorPart] = Field(default_factory=list)  # grouped connector: one endpoint per part
    replaces: list[str] = Field(default_factory=list)  # older connector ids this one supersedes
    legacy: list[Launch] = Field(default_factory=list)  # launches earlier versions shipped (upgraded on load)

    def _sources(self) -> list:
        return [self.args, self.env, self.url or "", self.headers, self.command or ""]

    def part_vars(self, part: ConnectorPart) -> set[str]:
        """Values only this part needs (the shared ones, such as host and token, are excluded)."""
        return set(env_vars([part.url, part.headers or {}])) - self.shared_vars()

    def shared_vars(self) -> set[str]:
        if not self.parts:
            return set()
        common = set.intersection(*(set(env_vars([p.url, p.headers or self.headers])) for p in self.parts))
        return common | set(env_vars([self.headers]))

    def required_env(self) -> set[str]:
        if self.parts:
            return self.shared_vars() | set(self.requires)
        return env_refs(self._sources()) | set(self.requires)

    def variables(self) -> dict[str, str | None]:
        """Settings this connector reads: variable name -> default (None = required)."""
        # A grouped connector names the workspace (in every part's address) before the token (in the headers).
        out = env_vars([[p.url for p in self.parts], *self._sources()]) if self.parts else env_vars(self._sources())
        for part in self.parts:
            for name, default in env_vars([part.url, part.headers or {}]).items():
                out.setdefault(name, default)
            for name in self.part_vars(part):  # a part's own values are optional: the part stays off without them
                out[name] = out[name] or ""
        for r in self.requires:
            out.setdefault(r, None)
        for v in self.accounts.vars if self.accounts else []:
            out.setdefault(v, "")
        for v in self.context:
            out.setdefault(v, "")
        return out

    def part_config(self, part: ConnectorPart) -> ConnectorConfig:
        """A plain HTTP connector for one part; its tools are reported under the group's id."""
        return self.model_copy(update={
            "id": f"{self.id}.{part.id}", "name": f"{self.name}: {part.name}", "transport": "http", "url": part.url,
            "headers": part.headers if part.headers is not None else self.headers,
            "allow_tools": part.allow_tools or self.allow_tools, "timeout_s": part.timeout_s or self.timeout_s,
            "parts": []})


SECRET_NAME = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|_KEY$|_PAT$)", re.I)


def is_secret(var: str) -> bool:
    return bool(SECRET_NAME.search(var))


class ConnectorSetting(BaseModel):
    """Choices made in the app for one connector, layered over connectors.yaml."""

    enabled: bool | None = None
    folders: list[str] | None = None


BUILTIN_LOCAL_FILES = ConnectorConfig(
    id="local-files", name="Local files", transport="builtin", network=False,
    description="Read files in folders you choose: reports, exports, notes, PDFs, Word and Excel files.",
    setup="Choose one or more folders. Agents can list, search and read files inside them, and nothing else. "
          "Nothing is written or deleted. Works offline; no other software is needed.",
)


def tool_allowed(cfg: ConnectorConfig, name: str, annotations: Any | None) -> tuple[bool, str]:
    if any(fnmatch.fnmatch(name, p) for p in cfg.deny_tools):
        return False, "denied by config"
    if cfg.allow_tools:
        ok = any(fnmatch.fnmatch(name, p) for p in cfg.allow_tools)
        return (ok, "allow-listed" if ok else "not in allow list")
    ro = getattr(annotations, "read_only_hint", None) if annotations is not None else None
    destructive = getattr(annotations, "destructive_hint", None) if annotations is not None else None
    if ro is True and destructive is not True:
        return True, "declared read-only"
    if ro is False:
        return False, "declared as writing"
    if cfg.infer_read_only and READ_PREFIX.search(name) and not WRITE_WORD.search(name):
        return True, "read-only by name"
    return False, "not provably read-only"


@dataclass
class ToolInfo:
    connector: str
    name: str
    description: str
    input_schema: dict
    allowed: bool
    reason: str

    @property
    def qualified(self) -> str:
        return qualify(self.connector, self.name)


def qualify(connector: str, tool: str) -> str:
    raw = f"{connector}__{tool}"
    return re.sub(r"[^a-zA-Z0-9_-]", "_", raw)[:64]


@dataclass
class _Request:
    op: str
    payload: dict
    future: asyncio.Future


@dataclass
class ConnectorState:
    status: str = "idle"  # idle | connecting | ready | error | unconfigured | disabled
    error: str = ""
    tools: list[ToolInfo] = field(default_factory=list)


class ConnectorWorker:
    def __init__(self, cfg: ConnectorConfig, target_factory):
        self.cfg = cfg
        self._target_factory = target_factory
        self.queue: asyncio.Queue[_Request | None] = asyncio.Queue()
        self.state = ConnectorState()
        self.ready = asyncio.Event()
        self.task: asyncio.Task | None = None

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.ready.clear()
            self.state = ConnectorState(status="connecting")
            self.task = asyncio.create_task(self._run(), name=f"connector:{self.cfg.id}")

    async def _run(self) -> None:
        try:
            async with Client(self._target_factory(), read_timeout_seconds=self.cfg.timeout_s) as client:
                listed = await client.list_tools()
                self.state.tools = [
                    ToolInfo(self.cfg.id, t.name, t.description or "", t.input_schema or {"type": "object"},
                             *tool_allowed(self.cfg, t.name, t.annotations))
                    for t in listed.tools
                ]
                self.state.status = "ready"
                self.ready.set()
                while True:
                    req = await self.queue.get()
                    if req is None:
                        break
                    try:
                        if req.op == "call":
                            res = await client.call_tool(req.payload["name"], req.payload["arguments"])
                            req.future.set_result(res)
                        elif req.op == "list":
                            listed = await client.list_tools()
                            req.future.set_result(listed)
                    except Exception as e:  # noqa: BLE001 - surface any tool failure to the caller
                        if not req.future.done():
                            req.future.set_exception(e)
        except Exception as e:  # noqa: BLE001
            self.state.status = "error"
            self.state.error = _short_error(e)
            log.warning("connector %s failed: %s", self.cfg.id, self.state.error)
        finally:
            self.ready.set()
            while not self.queue.empty():
                req = self.queue.get_nowait()
                if req and not req.future.done():
                    req.future.set_exception(RuntimeError(f"connector {self.cfg.id} is not running"))
            if self.state.status not in ("error",):
                self.state.status = "idle"

    async def request(self, op: str, payload: dict) -> Any:
        fut = asyncio.get_running_loop().create_future()
        await self.queue.put(_Request(op, payload, fut))
        return await asyncio.wait_for(fut, timeout=self.cfg.timeout_s + 5)

    async def stop(self) -> None:
        if self.task and not self.task.done():
            await self.queue.put(None)
            try:
                await asyncio.wait_for(self.task, timeout=10)
            except (TimeoutError, asyncio.CancelledError):
                self.task.cancel()


def _short_error(e: BaseException) -> str:
    if isinstance(e, BaseExceptionGroup):
        return "; ".join(_short_error(x) for x in e.exceptions)[:400]
    return f"{type(e).__name__}: {e}"[:400]


class ConnectorError(Exception):
    pass


# Environment variables a stdio connector inherits from the suite (everything else comes from its own config).
PASS_ENV = ("PATH", "HOME", "USERPROFILE", "APPDATA", "TMPDIR", "TEMP")


class ConnectorManager:
    def __init__(self, configs: list[ConnectorConfig], env: dict[str, str] | None = None,
                 in_process: dict[str, Any] | None = None, offline: bool = False):
        self.base_env = dict(os.environ) if env is None else env
        self.values: dict[str, str] = {}  # variables entered in the app (shared by every connector that uses them)
        self.bundled: dict[str, str] = {}  # values from an OAuth client file built into the app (lowest priority)
        self.bundled_from: dict[str, str] = {}  # variable -> the file it came from
        self.uploads_dir: Path | None = None  # where a client file uploaded in the app is saved (it wins)
        # uv and Node.js (runtimes.py): tool folders searched after the computer's own copy (the installer's
        # first, then first-use downloads), and the one first-use downloads go to.
        self.tool_roots: list[Path] = []
        self.download_root: Path | None = None
        self.on_tool_download: Callable[[str, str], None] | None = None  # (tool, version) once downloaded
        self.env = dict(self.base_env)
        self.file_configs = {c.id: _normalize(c) for c in configs}
        self.configs = dict(self.file_configs)
        self._in_process = in_process or {}  # tests: connector id -> MCPServer instance
        self.offline = offline
        self.workers: dict[str, ConnectorWorker] = {}

    @classmethod
    def from_file(cls, path: Path | None, offline: bool = False, presets: Path | None = None) -> ConnectorManager:
        """Load connectors.yaml. Presets (the shipped example) fill in connectors the file does not list,
        so connectors added in newer versions appear for people whose file was copied earlier. A connector
        that ``replaces`` older ids (Databricks, which used to be three) removes them, even from an older file."""
        configs: dict[str, ConnectorConfig] = {}
        shipped: dict[str, ConnectorConfig] = {}
        for src in (presets, path):
            if src and src.exists():
                raw = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
                for c in raw.get("connectors", []):
                    cfg = ConnectorConfig.model_validate(c)
                    if src == presets:
                        shipped[cfg.id] = cfg
                    else:
                        cfg = _with_shipped_signin(cfg, shipped.get(cfg.id))
                    configs[cfg.id] = cfg
        for cfg in list(configs.values()):
            for old in cfg.replaces:
                configs.pop(old, None)
        return cls(list(configs.values()), offline=offline)

    def available(self, values: dict[str, str]) -> dict[str, str]:
        """Every value a connector can use: built into the app, then typed in the app, then the environment."""
        return {**self.bundled, **{k: v for k, v in values.items() if v}, **{k: v for k, v in self.base_env.items() if v}}

    def load_client_files(self, folders: list[Path]) -> list[str]:
        """Read the OAuth client files connectors ship with (the first match in ``folders``). Returns problems."""
        problems: list[str] = []
        self.bundled, self.bundled_from = {}, {}
        for cfg in self.file_configs.values():
            spec = cfg.client_file
            if not spec:
                continue
            path = next((f / spec.name for f in folders if (f / spec.name).is_file()), None)
            if path is None:
                continue
            try:
                found = parse_client_file(path.read_text(encoding="utf-8"), spec)
            except (OSError, ValueError) as e:
                problems.append(f"{cfg.name}: could not use the OAuth client file {path}: {e}")
                continue
            self.bundled.update(found)
            self.bundled_from.update({var: str(path) for var in found})
        self.env = self.available(self.values)
        return problems

    def _client_file_view(self, cfg: ConnectorConfig) -> dict | None:
        """Where this connector's OAuth client comes from: uploaded in the app, built into the app, or neither."""
        if not cfg.client_file:
            return None
        found = next((self.bundled_from[v] for v in cfg.client_file.vars.values() if v in self.bundled_from), None)
        source = None
        if found:
            uploaded = self.uploads_dir is not None and Path(found).parent.resolve() == self.uploads_dir.resolve()
            source = "uploaded" if uploaded else "built-in"
        return {"name": cfg.client_file.name, "source": source}

    def replaced_by(self) -> dict[str, str]:
        """Old connector id -> the connector that now covers it."""
        return {old: cid for cid, cfg in self.file_configs.items() for old in cfg.replaces}

    def apply_settings(self, settings: dict[str, ConnectorSetting], values: dict[str, str]) -> None:
        """Layer the app's choices over the file. Environment variables still win over values typed in the app."""
        self.values = {k: v for k, v in values.items() if v}
        self.env = self.available(self.values)
        self.configs = {}
        for cid, cfg in self.file_configs.items():
            st = settings.get(cid)
            if st is None and cfg.replaces:  # carry the switch over from the connectors this one replaced
                old = [settings[o] for o in cfg.replaces if o in settings and settings[o].enabled is not None]
                st = ConnectorSetting(enabled=any(o.enabled for o in old)) if old else None
            upd: dict[str, Any] = {}
            if st and st.enabled is not None:
                upd["enabled"] = st.enabled
            if st and st.folders is not None:
                upd["folders"] = st.folders
            self.configs[cid] = cfg.model_copy(update=upd) if upd else cfg

    async def restart(self, cids: list[str] | None = None) -> None:
        """Stop workers so the next use starts them with the current settings."""
        for cid in list(cids or self.workers):
            for key in [k for k in self.workers if k == cid or k.startswith(cid + ".")]:
                w = self.workers.pop(key, None)
                if w:
                    await w.stop()

    # ------------------------------------------------------------ status

    def missing_env(self, cid: str) -> list[str]:
        cfg = self.configs[cid]
        if cfg.transport == "builtin":
            return []
        return sorted(v for v in cfg.required_env() if not self.env.get(v))

    def missing(self, cid: str) -> list[str]:
        cfg = self.configs[cid]
        if cfg.transport == "builtin":
            return [] if cfg.folders else ["a folder"]
        out = self.missing_env(cid)
        if cfg.parts and not self.ready_parts(cid):
            out.append("at least one of: " + "; ".join(p.name for p in cfg.parts))
        return out

    def ready_parts(self, cid: str) -> list[ConnectorPart]:
        """Parts of a grouped connector whose own values are all filled in."""
        cfg = self.configs[cid]
        return [p for p in cfg.parts if all(self.env.get(v) for v in cfg.part_vars(p))]

    def context_lines(self, cid: str) -> list[str]:
        """Lines told to agents from values the person entered (for example the repositories they work in)."""
        cfg = self.configs.get(cid)
        if not cfg:
            return []
        out = []
        for var, line in cfg.context.items():
            value = (self.env.get(var) or "").strip()
            if value:
                items = [re.sub(r"^https?://[^/]+/|\.git$|/$", "", x) for x in ACCOUNT_SPLIT.split(value) if x]
                out.append(line.format(value=", ".join(items)))
        return out

    def accounts(self, cid: str) -> list[str]:
        """Accounts the user allows on this connector, default first (empty: the server decides)."""
        cfg = self.configs.get(cid)
        if not cfg or not cfg.accounts:
            return []
        out: list[str] = []
        for var in cfg.accounts.vars:
            for a in ACCOUNT_SPLIT.split(self.env.get(var, "") or ""):
                if a and a.lower() not in (x.lower() for x in out):
                    out.append(a)
        return out

    def _with_account(self, cid: str, info: ToolInfo, arguments: dict) -> dict:
        """Refuse accounts the user did not list; name the default account when the call names none."""
        cfg = self.configs[cid]
        allowed = self.accounts(cid)
        if not cfg.accounts or not allowed:
            return arguments
        param = cfg.accounts.param
        value = arguments.get(param)
        if value not in (None, ""):
            if str(value).strip().lower() not in (a.lower() for a in allowed):
                raise ConnectorError(f"account '{value}' is not enabled for {cfg.name}; "
                                     f"allowed: {', '.join(allowed)}")
            return arguments
        if param in ((info.input_schema or {}).get("properties") or {}):
            return {**arguments, param: allowed[0]}
        return arguments

    def configured(self, cid: str) -> bool:
        cfg = self.configs.get(cid)
        if not cfg or not cfg.enabled:
            return False
        if self.offline and cfg.network:
            return False
        return cid in self._in_process or not self.missing(cid)

    def variables(self, cid: str) -> list[dict]:
        """The fields shown in the app: required ones first (in the order the connector names them), then the
        optional ones, account lists right after the account they extend, and each part's fields last."""
        cfg = self.configs[cid]
        found = cfg.variables()
        part_of = {v: p.id for p in cfg.parts for v in cfg.part_vars(p)}
        accounts = cfg.accounts.vars if cfg.accounts else []

        def rank(item: tuple[int, str]) -> tuple:
            i, name = item
            if name in part_of:
                return (3, [p.id for p in cfg.parts].index(part_of[name]), i)
            if found[name] is None or name in cfg.requires:
                return (0, 0, i)
            return (1 if name in accounts else 2, 0, i)

        out = []
        for _i, name in sorted(enumerate(found), key=rank):
            default = found[name]
            env = self.base_env.get(name)
            app = self.values.get(name)
            built_in = self.bundled.get(name)
            secret = is_secret(name)
            flag = name in cfg.requires
            out.append({"name": name, "secret": secret, "flag": flag, "optional": default is not None,
                        "default": default or "", "set": bool(env or app or built_in),
                        "source": "env" if env else ("app" if app else ("bundled" if built_in else None)),
                        "value": None if secret or env else (app or ""),
                        "label": cfg.labels.get(name, ""), "hint": cfg.hints.get(name, ""), "part": part_of.get(name)})
        return out

    def describe(self) -> list[dict]:
        out = []
        for cid, cfg in self.configs.items():
            w = self._worker_view(cid)
            if not cfg.enabled:
                status, err = "disabled", ""
            elif self.offline and cfg.network:
                status, err = "offline", "paused: needs the internet and offline mode is on"
            elif not self.configured(cid):
                status, err = "unconfigured", "needs: " + ", ".join(self.missing(cid))
            else:
                status, err = (w.state.status, w.state.error) if w else ("idle", "")
            tools = [{"name": t.name, "allowed": t.allowed, "reason": t.reason} for t in (w.state.tools if w else [])]
            out.append({"id": cid, "name": cfg.name, "description": cfg.description, "transport": cfg.transport,
                        "status": status, "error": err, "setup": cfg.setup, "verify": cfg.verify,
                        "enabled": cfg.enabled, "network": cfg.network, "offline_paused": bool(self.offline and cfg.network),
                        "builtin": cfg.transport == "builtin", "folders": list(cfg.folders),
                        "required_env": sorted(cfg.required_env()) if cfg.transport != "builtin" else [],
                        "missing": self.missing(cid), "steps": list(cfg.steps), "docs_url": cfg.docs_url,
                        "parts": [{"id": p.id, "name": p.name, "description": p.description,
                                   "ready": p in self.ready_parts(cid)} for p in cfg.parts],
                        "variables": self.variables(cid) if cfg.transport != "builtin" else [], "tools": tools,
                        "client_file": self._client_file_view(cfg),
                        "signin": ({"provider": cfg.signin.provider, "kind": cfg.signin.kind, "confirms": cfg.signin.confirms,
                                    "accounts_vars": list(cfg.accounts.vars) if cfg.accounts else []}
                                   if cfg.signin and cfg.transport == "stdio" else None)})
        return out

    # ------------------------------------------------------------ lifecycle

    def launch(self, cfg: ConnectorConfig) -> tuple[str, list[str], dict[str, str]]:
        """Command, arguments and environment of a stdio connector. Sign-in uses the same ones, so it asks for
        exactly the permissions the connector uses and writes to the token cache the connector reads."""
        if not cfg.command:
            raise ConnectorError(f"{cfg.id}: stdio connector needs a command")
        env = {**{k: v for k, v in self.env.items() if k in PASS_ENV}, **expand_env(cfg.env, self.env)}
        command = expand_env(cfg.command, self.env)
        tool = runtimes.tool_for(command) if os.path.basename(command) == command else None
        if tool is not None:
            path = env.get("PATH") or os.environ.get("PATH", "")
            where = runtimes.find(tool, path, self.tool_roots)
            if where and where[0] == "app":  # the computer has none, or one too old: the app's copy goes first
                env["PATH"] = os.pathsep.join([str(where[1]), *[p for p in path.split(os.pathsep) if p]])
                # A full path, so it is found on every OS (Windows looks up commands on the suite's own PATH).
                command = shutil.which(command, path=str(where[1])) or command
        return command, expand_env(cfg.args, self.env), env

    def missing_tool(self, cfg: ConnectorConfig) -> runtimes.Tool | None:
        """The runtime (uv, Node.js) the app has to download before this connector can run, or None: the computer
        has a new-enough copy, the app has one, or it is not a runtime the app can get."""
        if cfg.transport != "stdio" or not cfg.command or self.download_root is None:
            return None
        command = expand_env(cfg.command, self.env)
        tool = runtimes.tool_for(command) if os.path.basename(command) == command else None
        if tool is None:
            return None
        path = self.env.get("PATH") or os.environ.get("PATH", "")
        return None if runtimes.find(tool, path, self.tool_roots) else tool

    async def prepare(self, cfg: ConnectorConfig) -> None:
        """Download the runtime this connector needs if neither the computer nor the app has it (once)."""
        tool = self.missing_tool(cfg)
        if tool is None:
            return
        try:
            downloaded = await runtimes.ensure(tool, self.download_root)
        except runtimes.ToolError as e:
            raise ConnectorError(str(e)) from e
        if downloaded and self.on_tool_download:
            self.on_tool_download(tool.name, tool.version)

    def _target(self, cfg: ConnectorConfig):
        if cfg.id in self._in_process:
            return lambda: self._in_process[cfg.id]
        if cfg.transport == "builtin":
            from .local_files import build_server
            server = build_server(cfg.folders)
            return lambda: server
        if cfg.transport == "stdio":
            command, args, env = self.launch(cfg)
            params = StdioServerParameters(command=command, args=args, env=env)
            return lambda: params
        url = expand_env(cfg.url or "", self.env)
        headers = expand_env(cfg.headers, self.env)

        def http_target():
            return streamable_http_client(url, http_client=create_mcp_http_client(headers=headers))
        return http_target

    async def ensure(self, cid: str) -> ConnectorWorker:
        if cid not in self.configs:
            raise ConnectorError(f"unknown connector '{cid}'")
        if not self.configured(cid):
            raise ConnectorError(f"connector '{cid}' is not configured (needs: {', '.join(self.missing(cid)) or 'to be switched on'})")
        if self.configs[cid].parts:
            return await self._ensure_group(cid)
        if cid not in self._in_process:
            await self.prepare(self.configs[cid])
        return await self._start(cid, self.configs[cid])

    async def _start(self, key: str, cfg: ConnectorConfig) -> ConnectorWorker:
        w = self.workers.get(key)
        if w is None:
            w = ConnectorWorker(cfg, self._target(cfg))
            self.workers[key] = w
        if w.task is None or w.task.done():
            w.start()
        await asyncio.wait_for(w.ready.wait(), timeout=cfg.timeout_s + 30)
        if w.state.status != "ready":
            raise ConnectorError(f"connector '{cfg.id}' failed to start: {w.state.error}")
        return w

    async def _ensure_group(self, cid: str) -> ConnectorWorker:
        """Start every ready part. Their tools are listed under the group, named ``<part>.<tool>``.
        A part that fails is reported and the others stay usable."""
        cfg = self.configs[cid]
        tools: list[ToolInfo] = []
        errors: list[str] = []
        for part in self.ready_parts(cid):
            try:
                w = await self._start(f"{cid}.{part.id}", cfg.part_config(part))
            except (ConnectorError, TimeoutError) as e:
                errors.append(f"{part.name}: {e}")
                continue
            tools += [ToolInfo(cid, f"{part.id}.{t.name}", t.description, t.input_schema, t.allowed, t.reason)
                      for t in w.state.tools]
        view = _GroupView(cfg, tools, errors)
        if not tools and errors:
            raise ConnectorError(f"connector '{cid}' failed to start: " + "; ".join(errors))
        return view

    def _worker_view(self, cid: str):
        cfg = self.configs[cid]
        if not cfg.parts:
            return self.workers.get(cid)
        parts = [(p, self.workers.get(f"{cid}.{p.id}")) for p in cfg.parts]
        if not any(w for _p, w in parts):
            return None
        tools = [ToolInfo(cid, f"{p.id}.{t.name}", t.description, t.input_schema, t.allowed, t.reason)
                 for p, w in parts if w for t in w.state.tools]
        errors = [f"{p.name}: {w.state.error}" for p, w in parts if w and w.state.status == "error"]
        return _GroupView(cfg, tools, errors)

    async def shutdown(self) -> None:
        await asyncio.gather(*(w.stop() for w in self.workers.values()), return_exceptions=True)

    # ------------------------------------------------------------ tools

    async def tools(self, cid: str, *, allowed_only: bool = True) -> list[ToolInfo]:
        w = await self.ensure(cid)
        return [t for t in w.state.tools if t.allowed or not allowed_only]

    async def call(self, cid: str, tool: str, arguments: dict) -> tuple[str, bool]:
        """Call a tool. Returns (text, is_error). Refuses tools the policy blocks."""
        w = await self.ensure(cid)
        info = next((t for t in w.state.tools if t.name == tool), None)
        if info is None:
            raise ConnectorError(f"connector '{cid}' has no tool '{tool}'")
        if not info.allowed:
            raise ConnectorError(f"tool '{cid}.{tool}' is blocked by the read-only policy ({info.reason})")
        arguments = self._with_account(cid, info, arguments)
        name = tool
        if self.configs[cid].parts:  # "<part>.<tool>" goes to that part's own server
            part, name = tool.split(".", 1)
            w = self.workers[f"{cid}.{part}"]
        res = await w.request("call", {"name": name, "arguments": arguments})
        parts: list[str] = []
        for block in res.content or []:
            if getattr(block, "type", "") == "text":
                parts.append(block.text)
            else:
                parts.append(f"[{getattr(block, 'type', 'content')} omitted]")
        if not parts and res.structured_content is not None:
            parts.append(json.dumps(res.structured_content, default=str)[:20000])
        return "\n".join(parts), bool(res.is_error)


@dataclass
class _GroupView:
    """What a grouped connector looks like to callers: one status and one tool list across its parts."""

    cfg: ConnectorConfig
    tools: list[ToolInfo]
    errors: list[str]

    @property
    def state(self) -> ConnectorState:
        status = "ready" if self.tools else ("error" if self.errors else "idle")
        return ConnectorState(status=status, error="; ".join(self.errors), tools=self.tools)


SHIPPED_TEXT = ("setup", "steps", "hints", "labels", "docs_url", "verify")


def _with_shipped_signin(cfg: ConnectorConfig, shipped: ConnectorConfig | None) -> ConnectorConfig:
    """Bring a connectors.yaml copied by an earlier version up to date, without touching what the person changed.

    * It still uses a launch an earlier version shipped (``legacy``: Microsoft 365 in org mode, GitHub and Jira
      through Docker): take the shipped entry whole. Values stay where they are: in the app or the environment.
    * It launches the shipped server: take today's setup text, and the shipped sign-in and client file if it
      predates them.
    A connector whose launch was changed in any other way is left alone."""
    if not shipped or cfg.transport != shipped.transport:
        return cfg
    if any(cfg.command == old.command and cfg.args == old.args for old in shipped.legacy):
        # Nothing in a connector entry is personal (values live in the app or the environment), so an entry an
        # earlier version shipped unchanged is replaced whole: launch, name, accounts, sign-in and setup text.
        return shipped.model_copy()
    if cfg.command != shipped.command or cfg.args != shipped.args:
        return cfg
    # Same launch as today: the setup text is today's (it is display text, written for this version), and a sign-in
    # or built-in client the file predates is added. Anything else in the entry (allow or deny lists) is kept.
    update = {k: getattr(shipped, k) for k in SHIPPED_TEXT}
    if not cfg.signin:
        update.update(signin=shipped.signin, client_file=shipped.client_file)
    return cfg.model_copy(update=update)


def _normalize(cfg: ConnectorConfig) -> ConnectorConfig:
    """The local-files connector is built in. Older files launched it through Node.js (npx); use the built-in one."""
    if cfg.id == "local-files" and cfg.transport != "builtin":
        return BUILTIN_LOCAL_FILES.model_copy(update={"enabled": cfg.enabled})
    return cfg
