"""Sign in to a connector from the app.

Two ways, both run by the connector's own server, which keeps the tokens:

* ``command`` (Microsoft 365): the server signs in with a device code. See below.
* ``tool`` (Google Workspace): the suite starts the connector's server and calls its sign-in tool, which
  answers with a sign-in address and waits on its own local callback. The person signs in in a browser on
  this computer; the server saves that account's credentials as one file per address, and the suite sees the
  file appear (it never opens it). Agents cannot call the sign-in tool: it is not read-only, so the suite's
  policy hides it from them; only this module calls it, directly.

Device-code sign-in: some connector servers sign in with a device code. The server prints a web address and a short code. The
person opens the address in any browser (on this computer or a phone), enters the code and signs in. The
server then saves the tokens in its own cache. Before, that meant running a command in a terminal. Now the
suite runs the same command in the background and shows the address and code in Settings.

The command is the connector's own launch command and environment, with the sign-in arguments added. So
the sign-in asks for exactly the permissions the connector uses (read-only) and lands in the token cache the
connector reads. The suite never sees or stores a token: it reads only the printed prompt, the JSON result
and the list of signed-in accounts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from mcp.client.stdio import get_default_environment

from .connectors import ConnectorConfig, ConnectorError, ConnectorManager, ConnectorWorker
from .settings import expand_env

log = logging.getLogger("suite.signin")

URL_RE = re.compile(r"https://[^\s\"'<>]+")
CODE_RE = re.compile(r"\bcode\s+([A-Z0-9][A-Z0-9-]{4,})\b", re.I)
ACCOUNT_ID_RE = re.compile(r"^[A-Za-z0-9._@-]{1,200}$")  # account ids go on a command line: no shell characters
COMMAND_TIMEOUT_S = 180.0  # listing or removing accounts; the first run of npx downloads the server
NODE_COMMANDS = {"npx", "node", "npm"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
POLL_S = 1.0  # how often a tool sign-in looks for the account's credentials file
START_TIMEOUT_S = 300.0  # starting a server; the first run of uvx or npx downloads it


class SigninError(Exception):
    """A sign-in step that cannot run or failed; the message is shown to the person as it is."""


@dataclass
class SigninSession:
    connector: str
    provider: str
    status: str = "starting"  # starting | waiting | finishing | done | failed | cancelled
    url: str = ""
    code: str = ""
    message: str = ""
    account: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    proc: subprocess.Popen | None = field(default=None, repr=False)
    task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def active(self) -> bool:
        return self.status in ("starting", "waiting", "finishing")

    def view(self) -> dict:
        return {"connector": self.connector, "provider": self.provider, "status": self.status, "url": self.url,
                "code": self.code, "message": self.message, "account": self.account, "error": self.error,
                "started_at": self.started_at}


# ---------------------------------------------------------------- parsing the server's output


def parse_prompt(text: str) -> tuple[str, str]:
    """The sign-in address and code from a device-code prompt (for example Microsoft's "To sign in, use a web
    browser to open the page https://login.microsoft.com/device and enter the code ABCD1234 to authenticate.")."""
    url = URL_RE.search(text)
    code = CODE_RE.search(text)
    return (url.group(0).rstrip(".,;:)") if url else "", code.group(1) if code else "")


def parse_json(lines: list[str], key: str) -> dict | None:
    """The last line of output that is a JSON object holding ``key``."""
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and key in obj:
                return obj
    return None


def last_error(lines: list[str]) -> str:
    """The last meaningful line a command wrote to stderr (npm's notices and warnings are skipped)."""
    for line in reversed(lines):
        line = line.strip()
        if line and not re.match(r"^npm (warn|notice|WARN)\b", line):
            return line[:400]
    return ""


# ---------------------------------------------------------------- running commands


def resolve(command: str, env: dict[str, str]) -> str:
    """The full path of the command (on Windows this finds npx.cmd), or a message saying what to install."""
    found = shutil.which(command, path=env.get("PATH"))
    if found:
        return found
    base = os.path.basename(command).lower().split(".")[0]
    if base in NODE_COMMANDS:
        raise SigninError("Node.js is not installed, or the app cannot find it. Install Node.js 20 or newer from "
                          "https://nodejs.org (the LTS installer), then close and reopen the app.")
    if base in ("uv", "uvx"):
        raise SigninError("uv is not installed, or the app cannot find it. Install it from "
                          "https://docs.astral.sh/uv/getting-started/installation/, then close and reopen the app.")
    raise SigninError(f"'{command}' was not found. Install it, then close and reopen the app.")


def _popen_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {"start_new_session": True}  # its own process group, so cancelling also stops the node process npx starts


def _popen(argv: list[str], env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", **_popen_kwargs())


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _run(argv: list[str], env: dict[str, str], timeout: float) -> tuple[int, list[str], list[str]]:
    proc = _popen(argv, env)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as e:
        _kill(proc)
        proc.communicate()
        raise SigninError(f"The connector did not answer within {int(timeout)} seconds. Try again.") from e
    return proc.returncode, out.splitlines(), err.splitlines()


# ---------------------------------------------------------------- sign-in sessions


class SigninManager:
    """One sign-in at a time per connector, run in the background and polled from Settings."""

    def __init__(self, connectors: ConnectorManager,
                 on_done: Callable[[str, str, list[dict]], Awaitable[None]] | None = None):
        self.connectors = connectors
        self.on_done = on_done  # (connector id, account, every signed-in account) after a successful sign-in
        self.sessions: dict[str, SigninSession] = {}

    def config(self, cid: str) -> ConnectorConfig:
        cfg = self.connectors.configs.get(cid)
        if cfg is None:
            raise KeyError(cid)
        if not cfg.signin or cfg.transport != "stdio":
            raise SigninError(f"{cfg.name} does not sign in from the app.")
        return cfg

    def _argv(self, cfg: ConnectorConfig, extra: list[str]) -> tuple[list[str], dict[str, str]]:
        command, args, env = self.connectors.launch(cfg)
        env = get_default_environment() | env  # what the MCP client gives the connector process too
        return [resolve(command, env), *args, *extra], env

    def _check_online(self, cfg: ConnectorConfig) -> None:
        if self.connectors.offline and cfg.network:
            raise SigninError("Offline mode is on. Go online to sign in.")

    def get(self, cid: str) -> SigninSession | None:
        self.config(cid)
        return self.sessions.get(cid)

    async def start(self, cid: str, account: str | None = None) -> SigninSession:
        cfg = self.config(cid)
        self._check_online(cfg)
        current = self.sessions.get(cid)
        if current and current.active:
            return current  # pressing the button twice does not start a second sign-in
        session = SigninSession(cid, cfg.signin.provider)
        if cfg.signin.kind == "tool":
            account = (account or "").strip()
            if not EMAIL_RE.match(account):
                raise SigninError(f"Enter the {cfg.signin.provider} address to sign in with.")
        if self.connectors.missing_tool(cfg) is None:  # not one the app downloads: say what to install now
            command, _args, env = self.connectors.launch(cfg)
            resolve(command, get_default_environment() | env)
        if cfg.signin.kind == "tool":
            run: Coroutine[Any, Any, None] = self._tool_login(cfg, session, account)
        else:
            run = self._command_login(cfg, session)
        self.sessions[cid] = session
        session.task = asyncio.create_task(self._session(cfg, session, run), name=f"signin:{cid}")
        return session

    async def _prepare(self, cfg: ConnectorConfig, s: SigninSession) -> None:
        """Download uv or Node.js first if this connector needs it and the computer has none."""
        tool = self.connectors.missing_tool(cfg)
        if tool is not None:
            s.message = f"Downloading {tool.name} (once, for this connector)…"
            try:
                await self.connectors.prepare(cfg)
            except ConnectorError as e:
                raise SigninError(str(e)) from e
            s.message = ""

    async def _command_login(self, cfg: ConnectorConfig, s: SigninSession) -> None:
        await self._prepare(cfg, s)
        if s.status == "cancelled":
            return
        argv, env = self._argv(cfg, cfg.signin.login)
        await asyncio.to_thread(self._login, cfg, s, argv, env)

    async def _session(self, cfg: ConnectorConfig, s: SigninSession, run: Coroutine[Any, Any, None]) -> None:
        try:
            await run
            if s.status == "finishing":  # signed in: save the account, then say done
                try:
                    accounts = await self.accounts(cfg.id)
                except SigninError:
                    accounts = []
                # The account as the server names it in its list: that is the name agents pass back.
                match = next((a for a in accounts if a["username"].lower() == s.account.lower()), None)
                s.account = match["username"] if match else s.account
                if self.on_done:
                    await self.on_done(cfg.id, s.account, accounts)
                s.status = "done"
        except Exception as e:  # noqa: BLE001 - every failure is reported on the session
            log.warning("sign-in for %s failed: %s", cfg.id, e)
            if s.status != "cancelled":
                s.status, s.error = "failed", str(e)[:400] or type(e).__name__

    def _login(self, cfg: ConnectorConfig, s: SigninSession, argv: list[str], env: dict[str, str]) -> None:
        """Blocking: run the sign-in command, publish its prompt as soon as it appears, then wait for the result."""
        proc = _popen(argv, env)
        s.proc = proc
        if s.status == "cancelled":
            _kill(proc)
        errors: list[str] = []
        drain = threading.Thread(target=lambda: errors.extend(proc.stderr), daemon=True)  # a full pipe would block it
        drain.start()
        expired = threading.Event()
        timer = threading.Timer(cfg.signin.timeout_s, lambda: (expired.set(), _kill(proc)))
        timer.start()
        out: list[str] = []
        try:
            for line in proc.stdout:
                out.append(line)
                if s.status == "starting" or (s.status == "waiting" and not s.code):
                    url, code = parse_prompt("".join(out))
                    if url:  # if the wording ever changes and no code is found, the person still sees the message
                        s.url, s.code = url, code
                        s.message = " ".join(x.strip() for x in out if URL_RE.search(x) or CODE_RE.search(x))[:400]
                        s.status = "waiting"
            proc.wait()
        finally:
            timer.cancel()
            drain.join(timeout=2)
        if s.status == "cancelled":
            return
        result = parse_json(out, "success")
        if result and result.get("success") is True:
            user = result.get("userData") or {}
            s.account = str(user.get("userPrincipalName") or "")
            s.status = "finishing"
            return
        s.status = "failed"
        if expired.is_set():
            s.error = "The code expired before the sign-in finished. Press Sign in again for a new code."
        else:
            s.error = (str((result or {}).get("message") or "") or last_error(errors)
                       or f"The sign-in ended without a result (exit code {proc.returncode}).")[:400]

    async def cancel(self, cid: str) -> SigninSession | None:
        s = self.get(cid)
        if s and s.status in ("starting", "waiting"):  # once signed in, the account is saved whatever happens
            s.status = "cancelled"
            if s.proc:
                await asyncio.to_thread(_kill, s.proc)
            elif s.task and not s.task.done():
                s.task.cancel()  # a tool sign-in: stops its server
                try:
                    await s.task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001 - it is being stopped
                    pass
        return s

    async def accounts(self, cid: str) -> list[dict]:
        """Accounts signed in to this connector's server: id, username, name, and whether it is the default."""
        cfg = self.config(cid)
        if cfg.signin.kind == "tool":
            default = (self.connectors.env.get(cfg.accounts.vars[0], "") if cfg.accounts else "").lower()
            return [{"id": email, "username": email, "name": "", "selected": email.lower() == default}
                    for email in sorted(credential_files(self.credentials_dir(cfg)))]
        if self.connectors.missing_tool(cfg) is not None:
            return []  # its tool is not downloaded yet, so nothing can be signed in; opening Settings downloads nothing
        argv, env = self._argv(cfg, cfg.signin.accounts)
        code, out, err = await asyncio.to_thread(_run, argv, env, COMMAND_TIMEOUT_S)
        data = parse_json(out, "accounts")
        if data is None or not isinstance(data.get("accounts"), list):
            raise SigninError(last_error(err) or f"Could not list the signed-in accounts (exit code {code}).")
        return [{"id": str(a.get("id") or ""), "username": str(a.get("username") or ""),
                 "name": str(a.get("name") or ""), "selected": bool(a.get("selected"))}
                for a in data["accounts"] if isinstance(a, dict) and a.get("id")]

    async def remove(self, cid: str, account_id: str) -> None:
        """Sign one account out: the server deletes its tokens."""
        cfg = self.config(cid)
        if cfg.signin.kind == "tool":
            folder = self.credentials_dir(cfg)
            files = credential_files(folder).get(account_id)
            if not files:
                raise SigninError("That account is not signed in.")
            for path in files[1]:
                if path.resolve().parent != folder.resolve():  # never outside the server's credentials folder
                    raise SigninError("That account's sign-in is not where the connector keeps it.")
                path.unlink(missing_ok=True)
            return
        if not ACCOUNT_ID_RE.match(account_id):
            raise SigninError("That is not a valid account id.")
        argv, env = self._argv(cfg, [*cfg.signin.remove, account_id])
        code, out, err = await asyncio.to_thread(_run, argv, env, COMMAND_TIMEOUT_S)
        data = parse_json(out, "error") or {}
        if code != 0 or data.get("error"):
            raise SigninError(str(data.get("error") or last_error(err) or f"Sign-out failed (exit code {code})."))

    async def shutdown(self) -> None:
        for cid, s in list(self.sessions.items()):
            if s.active:
                await self.cancel(cid)

    # ------------------------------------------------------------ sign-in through the server's own tool

    def credentials_dir(self, cfg: ConnectorConfig) -> Path:
        """Where the connector's server saves each account's credentials (one file per address)."""
        _command, _args, env = self.connectors.launch(cfg)
        raw = expand_env(cfg.signin.credentials_dir or "", get_default_environment() | env)
        if not raw:
            raise SigninError(f"{cfg.name} does not say where its server keeps sign-ins.")
        return Path(raw).expanduser()

    async def _tool_login(self, cfg: ConnectorConfig, s: SigninSession, account: str) -> None:
        await self._prepare(cfg, s)
        folder = self.credentials_dir(cfg)
        before = {email: stamp for email, (stamp, _paths) in credential_files(folder).items()}
        await self.connectors.restart([cfg.id])  # one server at a time owns the sign-in callback port
        # ``login`` arguments are added to the launch: workspace-mcp keeps its sign-in tool only in the
        # "complete" tier. Its permissions come from the services and --read-only, so they stay the same.
        launch = cfg.model_copy(update={"id": f"{cfg.id}:signin", "args": [*cfg.args, *cfg.signin.login]})
        worker = ConnectorWorker(launch, self.connectors._target(launch))
        try:
            worker.start()
            await asyncio.wait_for(worker.ready.wait(), timeout=START_TIMEOUT_S)
            if worker.state.status != "ready":
                raise SigninError(f"The connector did not start: {worker.state.error}")
            args = {**cfg.signin.tool_args, (cfg.signin.account_arg or "account"): account}
            result = await worker.request("call", {"name": cfg.signin.tool, "arguments": args})
            text = "\n".join(getattr(b, "text", "") for b in result.content or [])
            found = URL_RE.search(text)
            if not found or result.is_error:
                raise SigninError(re.sub(r"[*`]", "", text).strip()[:400] or "The connector did not return a sign-in address.")
            if s.status == "cancelled":  # cancelled while the server was starting
                return
            s.url = found.group(0).rstrip(".,;:)*")
            s.message = f"Sign in to {cfg.signin.provider} as {account} in the browser on this computer."
            s.status = "waiting"
            deadline = time.time() + cfg.signin.timeout_s
            while s.status == "waiting":
                await asyncio.sleep(POLL_S)
                now = credential_files(folder)
                changed = [email for email, (stamp, _paths) in now.items() if stamp > before.get(email, 0.0)]
                if changed:  # Google may sign in a different account than the one typed: take what it saved
                    s.account = next((e for e in changed if e.lower() == account.lower()), changed[0])
                    s.status = "finishing"
                elif time.time() > deadline:
                    s.status = "failed"
                    s.error = (f"The sign-in was not finished within {int(cfg.signin.timeout_s // 60)} minutes. "
                               "Press Sign in again.")
        finally:
            await worker.stop()


def credential_files(folder: Path) -> dict[str, tuple[float, list[Path]]]:
    """Accounts with a credentials file in ``folder``: address -> (newest change time, files). Names are the
    address, URL-encoded by newer servers; files without an address in the name are not accounts."""
    out: dict[str, tuple[float, list[Path]]] = {}
    try:
        entries = list(folder.glob("*.json"))
    except OSError:
        return out
    for path in entries:
        email = unquote(path.stem) if "%" in path.stem else path.stem
        if "@" not in email or not path.is_file():
            continue
        try:
            stamp = path.stat().st_mtime
        except OSError:
            continue
        prev = out.get(email, (0.0, []))
        out[email] = (max(prev[0], stamp), [*prev[1], path])
    return out
