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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from pydantic import BaseModel, Field

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
    enabled: bool = True
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

    def required_env(self) -> set[str]:
        return env_refs([self.args, self.env, self.url or "", self.headers, self.command or ""]) | set(self.requires)

    def variables(self) -> dict[str, str | None]:
        """Settings this connector reads: variable name -> default (None = required)."""
        out = env_vars([self.args, self.env, self.url or "", self.headers, self.command or ""])
        for r in self.requires:
            out.setdefault(r, None)
        for v in self.accounts.vars if self.accounts else []:
            out.setdefault(v, "")
        return out


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


class ConnectorManager:
    def __init__(self, configs: list[ConnectorConfig], env: dict[str, str] | None = None,
                 in_process: dict[str, Any] | None = None, offline: bool = False):
        import os

        self.base_env = dict(os.environ) if env is None else env
        self.values: dict[str, str] = {}  # variables entered in the app (shared by every connector that uses them)
        self.env = dict(self.base_env)
        self.file_configs = {c.id: _normalize(c) for c in configs}
        self.configs = dict(self.file_configs)
        self._in_process = in_process or {}  # tests: connector id -> MCPServer instance
        self.offline = offline
        self.workers: dict[str, ConnectorWorker] = {}

    @classmethod
    def from_file(cls, path: Path | None, offline: bool = False, presets: Path | None = None) -> ConnectorManager:
        """Load connectors.yaml. Presets (the shipped example) fill in connectors the file does not list,
        so connectors added in newer versions appear for people whose file was copied earlier."""
        configs: dict[str, ConnectorConfig] = {}
        for src in (presets, path):
            if src and src.exists():
                raw = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
                for c in raw.get("connectors", []):
                    cfg = ConnectorConfig.model_validate(c)
                    configs[cfg.id] = cfg
        return cls(list(configs.values()), offline=offline)

    def apply_settings(self, settings: dict[str, ConnectorSetting], values: dict[str, str]) -> None:
        """Layer the app's choices over the file. Environment variables still win over values typed in the app."""
        self.values = {k: v for k, v in values.items() if v}
        self.env = {**self.values, **{k: v for k, v in self.base_env.items() if v}}
        self.configs = {}
        for cid, cfg in self.file_configs.items():
            st = settings.get(cid)
            upd: dict[str, Any] = {}
            if st and st.enabled is not None:
                upd["enabled"] = st.enabled
            if st and st.folders is not None:
                upd["folders"] = st.folders
            self.configs[cid] = cfg.model_copy(update=upd) if upd else cfg

    async def restart(self, cids: list[str] | None = None) -> None:
        """Stop workers so the next use starts them with the current settings."""
        for cid in list(cids or self.workers):
            w = self.workers.pop(cid, None)
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
        return self.missing_env(cid)

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
        out = []
        for name, default in sorted(self.configs[cid].variables().items()):
            env = self.base_env.get(name)
            app = self.values.get(name)
            secret = is_secret(name)
            flag = name in self.configs[cid].requires
            out.append({"name": name, "secret": secret, "flag": flag, "optional": default is not None,
                        "default": default or "", "set": bool(env or app),
                        "source": "env" if env else ("app" if app else None),
                        "value": None if secret or env else (app or "")})
        return out

    def describe(self) -> list[dict]:
        out = []
        for cid, cfg in self.configs.items():
            w = self.workers.get(cid)
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
                        "variables": self.variables(cid) if cfg.transport != "builtin" else [], "tools": tools})
        return out

    # ------------------------------------------------------------ lifecycle

    def _target(self, cfg: ConnectorConfig):
        if cfg.id in self._in_process:
            return lambda: self._in_process[cfg.id]
        if cfg.transport == "builtin":
            from .local_files import build_server
            server = build_server(cfg.folders)
            return lambda: server
        if cfg.transport == "stdio":
            if not cfg.command:
                raise ConnectorError(f"{cfg.id}: stdio connector needs a command")
            params = StdioServerParameters(
                command=expand_env(cfg.command, self.env), args=expand_env(cfg.args, self.env),
                env={**{k: v for k, v in self.env.items() if k in ("PATH", "HOME", "USERPROFILE", "APPDATA", "TMPDIR", "TEMP")},
                     **expand_env(cfg.env, self.env)},
            )
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
        w = self.workers.get(cid)
        if w is None:
            w = ConnectorWorker(self.configs[cid], self._target(self.configs[cid]))
            self.workers[cid] = w
        if w.task is None or w.task.done():
            w.start()
        await asyncio.wait_for(w.ready.wait(), timeout=self.configs[cid].timeout_s + 30)
        if w.state.status != "ready":
            raise ConnectorError(f"connector '{cid}' failed to start: {w.state.error}")
        return w

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
        res = await w.request("call", {"name": tool, "arguments": arguments})
        parts: list[str] = []
        for block in res.content or []:
            if getattr(block, "type", "") == "text":
                parts.append(block.text)
            else:
                parts.append(f"[{getattr(block, 'type', 'content')} omitted]")
        if not parts and res.structured_content is not None:
            parts.append(json.dumps(res.structured_content, default=str)[:20000])
        return "\n".join(parts), bool(res.is_error)


def _normalize(cfg: ConnectorConfig) -> ConnectorConfig:
    """The local-files connector is built in. Older files launched it through Node.js (npx); use the built-in one."""
    if cfg.id == "local-files" and cfg.transport != "builtin":
        return BUILTIN_LOCAL_FILES.model_copy(update={"enabled": cfg.enabled})
    return cfg
