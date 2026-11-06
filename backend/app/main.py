"""HTTP API and static UI.

Run:  uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
The server binds to localhost by default. If you expose it on a network, set
SUITE_API_TOKEN; every API call must then send ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .appconfig import (
    ConnectorEdit,
    GeneralEdit,
    GeneralSettings,
    OutputsEdit,
    ProfileEdit,
    TierPref,
    order_chain,
)
from .chat import Chat, ChatError
from .connectors import (
    ACCOUNT_SPLIT,
    ConnectorConfig,
    ConnectorError,
    ConnectorManager,
    ConnectorSetting,
    is_secret,
    parse_client_file,
)
from .endpoints import Endpoint, ModelEdit, ProviderOverride, apply_runtime, locality_of, normalize_url
from .engine import Engine, RunStopped
from .export import to_html
from .files import UnsupportedFile, extract_text
from .local_files import FolderError, check_folder
from .outputs import Outputs
from .playbooks import load_playbooks
from .providers import ModelRouter, ProviderError
from .registry import Registry
from .router import route
from .settings import Budgets, PersonaSettings, Settings, load_profile, load_settings
from .signin import SigninError, SigninManager
from .store import Store

log = logging.getLogger("suite")


class RunRequest(BaseModel):
    playbook_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    data_class: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class RouteRequest(BaseModel):
    text: str
    data_class: str | None = None


class InputAnswers(BaseModel):
    answers: list[str] = Field(default_factory=list, max_length=50)  # in the order of the questions asked
    skip: bool = False  # continue without answering
    by: str = Field(default="", max_length=120)


class Decision(BaseModel):
    decision: Literal["approved", "rejected"]
    decided_by: str
    note: str = ""
    edited: str | None = None


class KillSwitch(BaseModel):
    on: bool
    by: str = "user"


class OfflineSwitch(BaseModel):
    on: bool | None  # None = return to the config file / SUITE_OFFLINE default
    by: str = "user"


class ChatStart(BaseModel):
    agent_id: str = "chief-of-staff"
    data_class: str | None = None


class ChatMessage(BaseModel):
    content: str = Field(max_length=40_000)
    files: list[str] = Field(default_factory=list)


class Discover(BaseModel):
    base_url: str | None = None
    provider: str | None = None  # use this provider's address and saved key unless given here
    api_key: str | None = None


MAX_CLIENT_FILE_BYTES = 64 * 1024  # a Google OAuth client file is well under 1 KB


class SigninStart(BaseModel):
    account: str | None = Field(default=None, max_length=320)  # the address to sign in with (Google)


class ProviderEdit(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    api_key: str | None = None  # empty or omitted keeps the saved key
    clear_api_key: bool = False
    models: list[ModelEdit] | None = None


def public_endpoint(e: Endpoint) -> dict:
    d = e.model_dump(exclude={"api_key"})
    return {**d, "has_api_key": bool(e.api_key), "provider": e.provider_name, "ref": e.ref,
            "locality": locality_of(e.base_url)}


class Suite:
    def __init__(self, settings: Settings, connectors: ConnectorManager | None = None, http_client=None):
        self.settings = settings
        self.registry = Registry(settings.registry_dir, settings.policies_dir, settings.private_registry_dir)
        self.connectors = connectors or ConnectorManager.from_file(
            settings.connectors_path, offline=settings.offline, presets=settings.home / "config" / "connectors.example.yaml")
        self.playbooks, self.warnings = load_playbooks(settings.playbooks_dir, self.registry, set(self.connectors.configs),
                                                      self.connectors.replaced_by())
        self.warnings = self.registry.warnings + self.warnings
        self.store = Store(settings.data_dir / "suite.db")
        self.models = ModelRouter(settings, http_client=http_client)
        self.file_profile = load_profile(settings)
        self.profile: dict = {}  # same dict object the engine reads; refreshed in place by apply()
        # The outputs folder: the one chosen in Settings, else suite.yaml / SUITE_OUTPUTS_DIR, else Documents.
        self.file_outputs = settings.outputs_dir
        self.outputs = Outputs(self._outputs_choice(), settings.theme_dir)
        problem = self.outputs.ensure()
        if problem:
            self.warnings.append(problem)
        self.engine = Engine(settings, self.registry, self.playbooks, self.models, self.connectors, self.store, self.profile,
                             outputs=self.outputs)
        self.chat = Chat(settings, self.registry, self.models, self.store, self.profile, self.playbooks, lambda: self.engine.killed,
                         outputs=self.outputs, connectors=self.connectors)
        # File/env configuration is the base; choices made in the app are layered on top and persisted.
        self.base = {"providers": dict(settings.providers), "models": list(settings.models),
                     "tiers": {k: list(v) for k, v in settings.tiers.items()}, "offline": settings.offline,
                     "budgets": settings.budgets.model_copy(), "persona": settings.persona.model_copy(),
                     "store_prompts": settings.store_prompts, "default_data_class": settings.default_data_class,
                     "data_classes": {k: list(v) for k, v in settings.data_classes.items()},
                     "agent_overrides": {k: list(v) for k, v in settings.agent_overrides.items()}}
        self.offline_default: str | None = None
        self.http_client = http_client
        self.signin = SigninManager(self.connectors, self.signed_in, log_dir=settings.data_dir / "logs")
        self.prefilled: dict[str, str] = {}  # connector -> address a sign-in filled in as the default account
        # OAuth clients built into the app (Google): in the shipped config folder, or next to connectors.yaml.
        # First match wins: a file uploaded in Settings, then one next to connectors.yaml, then the shipped one.
        self.client_folders = list(dict.fromkeys(
            [settings.data_dir, *([settings.connectors_path.parent] if settings.connectors_path else []),
             settings.home / "config"]))
        self.connectors.uploads_dir = settings.data_dir
        # uv and Node.js: the computer's own copy if new enough, else the one the installer put in <app>/tools,
        # else downloaded into the data folder the first time a connector needs it (runtimes.py).
        self.connectors.tool_roots = [settings.home / "tools", settings.data_dir / "tools"]
        self.connectors.download_root = settings.data_dir / "tools"
        self.connectors.on_tool_download = lambda name, version: self.store.audit(
            "tool_downloaded", None, tool=name, version=version)
        self.warnings += self.connectors.load_client_files(self.client_folders)
        self.apply()

    # ------------------------------------------------------------ runtime configuration

    def endpoints(self) -> list[Endpoint]:
        return [Endpoint.model_validate(e) for e in self.store.get_setting("endpoints", [])]

    def offline_override(self) -> bool | None:
        return self.store.get_setting("offline_override", None)

    def provider_overrides(self) -> dict[str, ProviderOverride]:
        return {k: ProviderOverride.model_validate(v) for k, v in self.store.get_setting("provider_overrides", {}).items()}

    def general(self) -> GeneralSettings:
        return GeneralSettings.model_validate(self.store.get_setting("general", {}))

    def saved_profile(self) -> dict | None:
        return self.store.get_setting("profile", None)

    def connector_settings(self) -> dict[str, ConnectorSetting]:
        return {k: ConnectorSetting.model_validate(v) for k, v in self.store.get_setting("connector_settings", {}).items()}

    def apply(self) -> None:
        s, b, g = self.settings, self.base, self.general()
        override = self.offline_override()
        offline = b["offline"] if override is None else bool(override)
        apply_runtime(s, b, self.endpoints(), offline, self.provider_overrides())
        for t, pref in (g.tiers or {}).items():
            s.tiers[t] = order_chain(s.tiers.get(t, []), pref)
        # Default and fallback model: tried first and second for every kind of work, local or cloud.
        known = {m.ref for m in s.models}
        lead = [r for r in (g.default_model, g.fallback_model) if r and r in known]
        if lead:
            for t in s.tiers:
                s.tiers[t] = list(dict.fromkeys(lead + s.tiers[t]))
        s.agent_overrides = {k: list(v) for k, v in b["agent_overrides"].items()}
        self.offline_default = None
        if offline:
            # One local model for every agent: first in every chain; per-agent choices wait until online.
            self.offline_default = self._local_default(g.offline_model)
            if self.offline_default:
                for t in s.tiers:
                    s.tiers[t] = [self.offline_default] + [r for r in s.tiers[t] if r != self.offline_default]
            s.agent_overrides = {}
        else:
            for aid, ref in (g.agent_models or {}).items():
                agent = self.registry.agents.get(aid)
                if agent and any(m.ref == ref for m in s.models):
                    chain = s.tiers.get(agent.default_tier, [])
                    s.agent_overrides[aid] = [ref] + [r for r in chain if r != ref]  # the tier chain stays as fallback
        s.budgets = Budgets(**g.budgets.model_dump()) if g.budgets else b["budgets"].model_copy()
        s.persona = PersonaSettings(chat=b["persona"].chat if g.persona_chat is None else g.persona_chat,
                                    exports=b["persona"].exports if g.persona_exports is None else g.persona_exports)
        s.store_prompts = b["store_prompts"] if g.store_prompts is None else g.store_prompts
        s.default_data_class = g.default_data_class or b["default_data_class"]
        dc = {k: list(v) for k, v in b["data_classes"].items()}
        for k, allowed in (g.cloud_allowed or {}).items():
            dc[k] = ["local", "cloud"] if allowed else ["local"]
        dc["restricted"] = ["local"]  # fixed: restricted data never leaves your network
        s.data_classes = dc
        self.profile.clear()
        self.profile.update(self.saved_profile() or self.file_profile)
        self.connectors.apply_settings(self.connector_settings(), self.store.get_setting("connector_values", {}))
        self.connectors.offline = offline
        self.models._instances = {}  # addresses or keys may have changed

    def _local_default(self, chosen: str | None) -> str | None:
        order = [chosen] if chosen else []
        for t in ("specialist", "synthesis", "router", "review"):
            order += self.settings.tiers.get(t, [])
        order += [m.ref for m in self.settings.models]
        for ref in order:
            prov = ref.split("/", 1)[0]
            cfg = self.settings.providers.get(prov)
            if cfg and cfg.locality == "local" and self.models.availability(prov)[0]:
                return ref
        return None

    # ------------------------------------------------------------ settings pages

    def save_general(self, edit: GeneralEdit, by: str) -> None:
        g = self.general()
        if edit.budgets is not None:
            g.budgets = edit.budgets
        for f in ("persona_chat", "persona_exports", "store_prompts", "default_data_class"):
            v = getattr(edit, f)
            if v is not None:
                setattr(g, f, v)
        if edit.cloud_allowed is not None:
            g.cloud_allowed = {**(g.cloud_allowed or {}), **edit.cloud_allowed}
        known_refs = {m.ref for m in self.settings.models}
        if edit.agent_models is not None:
            am = dict(g.agent_models or {})
            for aid, ref in edit.agent_models.items():
                if aid not in self.registry.agents:
                    raise ValueError(f"unknown agent {aid}")
                if not ref:
                    am.pop(aid, None)
                elif ref not in known_refs:
                    raise ValueError(f"unknown model {ref}; add it to a provider first")
                else:
                    am[aid] = ref
            g.agent_models = am or None
        for f in ("default_model", "fallback_model"):
            ref = getattr(edit, f)
            if ref is None:
                continue
            if ref and ref not in known_refs:
                raise ValueError(f"unknown model {ref}; add it to a provider first")
            setattr(g, f, ref or None)
        if g.default_model and g.default_model == g.fallback_model:
            raise ValueError("the fallback model must differ from the default model")
        if edit.offline_model is not None:
            if edit.offline_model == "":
                g.offline_model = None
            else:
                prov = self.settings.providers.get(edit.offline_model.split("/", 1)[0])
                if edit.offline_model not in known_refs or not prov or prov.locality != "local":
                    raise ValueError("the offline model must be a model on a local provider or endpoint")
                g.offline_model = edit.offline_model
        if edit.tiers is not None:
            tiers = dict(g.tiers or {})
            known = {m.ref for m in self.settings.models}
            for t, order in edit.tiers.items():
                bad = [r for r in order if r not in known]
                if bad:
                    raise ValueError(f"unknown model {bad[0]}; add it to a provider first")
                current = self.settings.tiers.get(t, [])
                prev = tiers.get(t, TierPref())
                excluded = sorted((set(prev.excluded) | {r for r in current if r not in order}) - set(order))
                tiers[t] = TierPref(order=list(dict.fromkeys(order)), excluded=excluded)
            g.tiers = tiers
        self.store.set_setting("general", g.model_dump(exclude_none=True))
        self.apply()
        self.store.audit("settings_changed", None, fields=sorted(edit.model_dump(exclude_none=True)), by=by)

    # ------------------------------------------------------------ outputs folder

    def outputs_setting(self) -> dict:
        return self.store.get_setting("outputs_folder", {}) or {}

    def _outputs_choice(self) -> Path | None:
        st = self.outputs_setting()
        if st.get("off"):
            return None
        return Path(st["path"]) if st.get("path") else self.file_outputs

    def set_outputs(self, path: str | None, off: bool, by: str) -> None:
        """Choose the outputs folder in the app: a folder, off, or back to the default (path None, off False)."""
        if off:
            self.store.set_setting("outputs_folder", {"off": True})
        elif path:
            p = Path(path.strip().strip('"')).expanduser()
            if not p.is_absolute():
                raise ValueError("Enter the full path of the folder, for example C:\\Users\\you\\Documents\\Outputs.")
            problem = Outputs(p, self.settings.theme_dir).ensure()
            if problem:
                raise ValueError(problem)
            self.store.set_setting("outputs_folder", {"path": str(p)})
        else:
            self.store.set_setting("outputs_folder", {})
        self.outputs.root = self._outputs_choice()
        problem = self.outputs.ensure()
        self.store.audit("outputs_folder_changed", None, path=str(self.outputs.root) if self.outputs.root else None, by=by)
        if problem:
            raise ValueError(problem)

    def outputs_info(self) -> dict:
        from .outputs import default_outputs_dir
        st = self.outputs_setting()
        root = self.outputs.root
        shared = []
        if root:
            for folder in self.connectors.configs.get("local-files", ConnectorConfig(id="x", name="x", transport="builtin")).folders:
                f = Path(folder)
                if root == f or f in root.parents or root in f.parents:
                    shared.append(folder)
        return {"path": str(root) if root else None, "source": "app" if st else ("file" if self.file_outputs != default_outputs_dir() else "default"),
                "default": str(self.file_outputs or default_outputs_dir()), "shared_with_local_files": shared}

    def reset_general(self, part: str, by: str) -> None:
        g = self.general()
        if part == "tiers":
            g.tiers = None
        elif part == "budgets":
            g.budgets = None
        elif part == "all":
            g = GeneralSettings()
        else:
            raise ValueError("part must be tiers, budgets or all")
        self.store.set_setting("general", g.model_dump(exclude_none=True))
        self.apply()
        self.store.audit("settings_reset", None, part=part, by=by)

    def save_profile(self, edit: ProfileEdit | None, by: str) -> None:
        self.store.set_setting("profile", edit.model_dump() if edit else None)
        self.apply()
        self.store.audit("profile_saved" if edit else "profile_reset", None, by=by)

    async def save_connector(self, cid: str, edit: ConnectorEdit, by: str) -> None:
        cfg = self.connectors.file_configs.get(cid)
        if cfg is None:
            raise KeyError(cid)
        all_settings = self.connector_settings()
        st = all_settings.get(cid, ConnectorSetting())
        if edit.enabled is not None:
            st.enabled = edit.enabled
        if edit.folders is not None:
            if cfg.transport != "builtin":
                raise ValueError("only Local files takes folders")
            folders: list[str] = []
            for f in edit.folders:
                if f.strip():
                    folders.append(str(check_folder(f)))  # raises FolderError with a readable message
            st.folders = list(dict.fromkeys(folders))[:20]
        all_settings[cid] = st
        values = dict(self.store.get_setting("connector_values", {}))
        known = cfg.variables()
        changed: list[str] = []
        for var in edit.clear:
            if var in known and values.pop(var, None) is not None:
                changed.append(var)
        for var, val in (edit.values or {}).items():
            if var not in known:
                raise ValueError(f"{cid} does not use {var}")
            if val:
                values[var] = val
                changed.append(var)
            elif not is_secret(var) and values.pop(var, None) is not None:
                changed.append(var)
        if edit.enabled is True:
            # A connector is switched on only once it is set up: every required value, or a folder for Local files.
            if cfg.transport == "builtin":
                missing = [] if (st.folders if st.folders is not None else cfg.folders) else ["a folder"]
            else:
                have = self.connectors.available(values)
                missing = sorted(v for v in cfg.required_env() if not have.get(v))
            if missing:
                raise ValueError(f"{cfg.name} needs {', '.join(missing)} before it can be switched on. Open Edit to set it up.")
        self.store.set_setting("connector_settings", {k: v.model_dump() for k, v in all_settings.items()})
        self.store.set_setting("connector_values", values)
        self.apply()
        await self.connectors.restart()
        self.store.audit("connector_edited", None, connector=cid, enabled=st.enabled, variables_changed=sorted(set(changed)),
                         folders=len(st.folders or []), by=by)

    async def reset_connector(self, cid: str, by: str) -> None:
        all_settings = self.connector_settings()
        all_settings.pop(cid, None)
        self.store.set_setting("connector_settings", {k: v.model_dump() for k, v in all_settings.items()})
        cfg = self.connectors.file_configs.get(cid)
        if cfg:
            values = dict(self.store.get_setting("connector_values", {}))
            others = {v for c, oc in self.connectors.file_configs.items() if c != cid for v in oc.variables()}
            for var in cfg.variables():
                if var not in others:  # keep values another connector still uses (e.g. DATABRICKS_HOST)
                    values.pop(var, None)
            self.store.set_setting("connector_values", values)
        self.apply()
        await self.connectors.restart([cid])
        self.store.audit("connector_reset", None, connector=cid, by=by)

    def _sign_in_state(self, cid: str, values: dict[str, str], accounts: list[str], by: str, event: str, **audit) -> None:
        """Save a connector's sign-in state: its accounts list and sign-in flag, and its switch (on once it has
        everything it needs after a sign-in, off once no account is left)."""
        cfg = self.connectors.file_configs[cid]
        env = self.connectors.base_env
        if cfg.accounts and not any(env.get(v) for v in cfg.accounts.vars):  # a list set in the environment stays
            names = cfg.accounts.vars
            # One field holds them all (Microsoft). Two (Google): the default address, then the others.
            parts = [accounts] if len(names) == 1 else [accounts[:1], *([] for _ in names[1:-1]), accounts[1:]]
            for var, part in zip(names, parts, strict=True):
                if part:
                    values[var] = ", ".join(part)
                else:
                    values.pop(var, None)
        flag = cfg.signin.confirms if cfg.signin else None
        if flag and not env.get(flag):
            if accounts:
                values[flag] = "1"
            else:
                values.pop(flag, None)
        all_settings = self.connector_settings()
        st = all_settings.get(cid, ConnectorSetting())
        enabled = self.connectors.configs[cid].enabled
        have = self.connectors.available(values)
        if accounts and not enabled and all(have.get(v) for v in cfg.required_env()):
            st.enabled = True
        elif not accounts and enabled:
            st.enabled = False
        all_settings[cid] = st
        self.store.set_setting("connector_settings", {k: v.model_dump() for k, v in all_settings.items()})
        self.store.set_setting("connector_values", values)
        self.apply()
        self.store.audit(event, None, connector=cid, enabled=self.connectors.configs[cid].enabled, by=by, **audit)

    async def save_client_file(self, cid: str, data: bytes, by: str) -> None:
        """Keep an OAuth client file uploaded in Settings (it wins over one built into the app)."""
        cfg = self.connectors.file_configs[cid]
        if not cfg.client_file:
            raise ValueError(f"{cfg.name} does not take an OAuth client file.")
        if len(data) > MAX_CLIENT_FILE_BYTES:
            raise ValueError("That file is too large to be an OAuth client file.")
        found = parse_client_file(data, cfg.client_file)  # ValueError says what is wrong
        target = self.settings.data_dir / cfg.client_file.name
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # readable by this user only
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data.decode("utf-8"))
        self.connectors.load_client_files(self.client_folders)
        self.apply()
        await self.connectors.restart([cid])
        # The client ID is not secret (it appears in every sign-in address); the secret is never logged.
        self.store.audit("connector_client_file_saved", None, connector=cid, by=by,
                         client_id=next((v for k, v in found.items() if not is_secret(k)), ""))

    async def remove_client_file(self, cid: str, by: str) -> None:
        cfg = self.connectors.file_configs[cid]
        if not cfg.client_file:
            raise ValueError(f"{cfg.name} does not take an OAuth client file.")
        (self.settings.data_dir / cfg.client_file.name).unlink(missing_ok=True)
        self.connectors.load_client_files(self.client_folders)
        self.apply()
        await self.connectors.restart([cid])
        self.store.audit("connector_client_file_removed", None, connector=cid, by=by)

    def _listed_accounts(self, cid: str, values: dict[str, str]) -> list[str]:
        """The accounts agents may use, default first, as saved in the app (every account field, in order)."""
        cfg = self.connectors.file_configs[cid]
        out: list[str] = []
        for var in cfg.accounts.vars if cfg.accounts else []:
            for a in ACCOUNT_SPLIT.split(values.get(var, "")):
                if a and a.lower() not in (x.lower() for x in out):
                    out.append(a)
        return out

    def prefill_default(self, cid: str, account: str) -> None:
        """The address typed to sign in becomes the default account right away when none is set (Google)."""
        cfg = self.connectors.file_configs[cid]
        if not account or not cfg.accounts:
            return
        var = cfg.accounts.vars[0]
        values = dict(self.store.get_setting("connector_values", {}))
        if values.get(var) or self.connectors.base_env.get(var):
            return
        values[var] = account.strip()
        self.store.set_setting("connector_values", values)
        self.prefilled[cid] = account.strip()  # replaced if Google signs in a different account
        self.apply()

    async def use_signed_in(self, cid: str, by: str) -> list[dict]:
        """Allow the accounts already signed in to the connector's server (for example from a terminal)."""
        accounts = await self.signin.accounts(cid)
        if not accounts:
            raise SigninError("No account is signed in yet.")
        names = [a["username"] for a in sorted(accounts, key=lambda a: not a["selected"]) if a["username"]]
        values = dict(self.store.get_setting("connector_values", {}))
        self._sign_in_state(cid, values, names, by, "connector_signed_in", account=", ".join(names))
        await self.connectors.restart([cid])
        return accounts

    async def signed_in(self, cid: str, account: str, signed_in: list[dict]) -> None:
        """After a sign-in from the app: add the account to the accounts agents may use, confirm the sign-in and
        switch the connector on if it now has everything it needs. The server's new tokens apply on restart."""
        values = dict(self.store.get_setting("connector_values", {}))
        listed = self._listed_accounts(cid, values)
        names = {a["username"].lower() for a in signed_in if a["username"]}
        if names:  # an address typed before signing in that is not signed in (Google chose another) is dropped
            listed = [a for a in listed if a.lower() in names or a.lower() == account.lower()]
        typed = self.prefilled.pop(cid, "")
        if typed and account and typed.lower() != account.lower():  # the address this sign-in filled in was not the one
            listed = [a for a in listed if a.lower() != typed.lower()]
        if not listed:  # until now the server chose among every signed-in account: keep them, its default first
            listed = [a["username"] for a in sorted(signed_in, key=lambda a: not a["selected"]) if a["username"]]
        if account and account.lower() not in (a.lower() for a in listed):
            listed.append(account)
        self._sign_in_state(cid, values, listed, "ui", "connector_signed_in", account=account)
        await self.connectors.restart([cid])

    async def sign_out(self, cid: str, account_id: str, by: str) -> list[dict]:
        """Sign one account out of a connector's server and stop offering it to agents. Returns who is left."""
        accounts = await self.signin.accounts(cid)
        target = next((a for a in accounts if a["id"] == account_id), None)
        if target is None:
            raise SigninError("That account is not signed in.")
        await self.signin.remove(cid, account_id)
        left = [a for a in accounts if a["id"] != account_id]
        values = dict(self.store.get_setting("connector_values", {}))
        listed = self._listed_accounts(cid, values)
        gone = target["username"].lower()
        keep = [a for a in listed if a.lower() != gone] if listed else [a["username"] for a in left]
        self._sign_in_state(cid, values, keep if left else [], by, "connector_signed_out", account=target["username"])
        await self.connectors.restart([cid])
        return left

    def save_provider(self, name: str, edit: ProviderEdit, by: str) -> None:
        if name not in self.base["providers"]:
            raise KeyError(name)
        overrides = self.provider_overrides()
        prev = overrides.get(name, ProviderOverride())
        key = None if edit.clear_api_key else (edit.api_key.strip() if edit.api_key and edit.api_key.strip() else prev.api_key)
        overrides[name] = ProviderOverride(
            enabled=edit.enabled if edit.enabled is not None else prev.enabled,
            base_url=edit.base_url if edit.base_url is not None else prev.base_url,
            api_key=key,
            models=edit.models if edit.models is not None else prev.models,
        )
        self.store.set_setting("provider_overrides", {k: v.model_dump() for k, v in overrides.items()})
        self.apply()
        self.store.audit("provider_edited", None, provider=name, enabled=overrides[name].enabled,
                         base_url=overrides[name].base_url, api_key_saved=bool(key),
                         models=[m.model for m in overrides[name].models or []], by=by)

    def reset_provider(self, name: str, by: str) -> bool:
        overrides = self.provider_overrides()
        if overrides.pop(name, None) is None:
            return False
        self.store.set_setting("provider_overrides", {k: v.model_dump() for k, v in overrides.items()})
        self.apply()
        self.store.audit("provider_reset", None, provider=name, by=by)
        return True

    async def set_offline(self, on: bool | None, by: str) -> bool:
        self.store.set_setting("offline_override", on)
        self.apply()
        if self.settings.offline:  # stop connectors that need the internet
            for cid, w in list(self.connectors.workers.items()):
                if self.connectors.configs[cid].network:
                    await w.stop()
        self.store.audit("offline_mode", None, on=self.settings.offline, override=on, by=by)
        return self.settings.offline

    def save_endpoint(self, ep: Endpoint, by: str) -> None:
        prev = next((e for e in self.endpoints() if e.id == ep.id), None)
        if prev and not ep.api_key:
            ep = ep.model_copy(update={"api_key": prev.api_key})  # editing without retyping the key keeps it
        eps = [e for e in self.endpoints() if e.id != ep.id] + [ep]
        self.store.set_setting("endpoints", [e.model_dump() for e in eps])
        self.apply()
        self.store.audit("endpoint_saved", None, id=ep.id, base_url=ep.base_url, model=ep.model,
                         locality=locality_of(ep.base_url), use_for=ep.use_for, by=by)

    def delete_endpoint(self, eid: str, by: str) -> bool:
        eps = self.endpoints()
        keep = [e for e in eps if e.id != eid]
        if len(keep) == len(eps):
            return False
        self.store.set_setting("endpoints", [e.model_dump() for e in keep])
        self.apply()
        self.store.audit("endpoint_deleted", None, id=eid, by=by)
        return True


def create_app(settings: Settings | None = None, connectors: ConnectorManager | None = None, http_client=None) -> FastAPI:
    settings = settings or load_settings()
    suite = Suite(settings, connectors, http_client)
    token = os.environ.get("SUITE_API_TOKEN", "")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        suite.engine.recover()
        for w in suite.warnings:
            log.warning(w)
        yield
        await suite.signin.shutdown()
        await suite.connectors.shutdown()

    app = FastAPI(title="Agentic Productivity Suite", version=__version__, lifespan=lifespan)
    app.state.suite = suite

    @app.middleware("http")
    async def auth(request: Request, call_next):
        if token and request.url.path.startswith("/api/") and request.url.path != "/api/health":
            got = request.headers.get("authorization", "")
            if not hmac.compare_digest(got, f"Bearer {token}"):
                return JSONResponse({"detail": "missing or invalid API token"}, status_code=401)
        return await call_next(request)

    eng, store = suite.engine, suite.store

    # ---------------------------------------------------------------- overview

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "auth_required": bool(token), "offline": settings.offline,
                "kill_switch": eng.killed}

    @app.get("/api/overview")
    def overview():
        return {
            "desks": [d.model_dump() for d in suite.registry.desks.values()],
            "agents": [a.public() for a in suite.registry.agents.values()],
            "playbooks": [p.card() for p in suite.playbooks.values()],
            "providers": suite.models.describe(),
            "tiers": settings.tiers,
            "connectors": suite.connectors.describe(),
            "data_classes": settings.data_classes,
            "default_data_class": settings.default_data_class,
            "kill_switch": eng.killed,
            "offline": settings.offline,
            "offline_override": suite.offline_override(),
            "endpoints": [public_endpoint(e) for e in suite.endpoints()],
            "budgets": settings.budgets.model_dump(),
            "persona": settings.persona.model_dump(),
            "profile_configured": any(v not in (None, "", []) for v in suite.profile.values()),
            "profile": {k: suite.profile.get(k, [] if k in ("goals", "working_preferences") else "")
                        for k in ProfileEdit.model_fields},
            "profile_saved_in_app": suite.saved_profile() is not None,
            "store_prompts": settings.store_prompts,
            "outputs_dir": str(suite.outputs.root) if suite.outputs.root else None,
            "outputs": suite.outputs_info(),
            "model_refs": [m.ref for m in settings.models],
            "general_edited": sorted(suite.general().model_dump(exclude_none=True)),
            "agent_models": suite.general().agent_models or {},
            "default_model": suite.general().default_model, "fallback_model": suite.general().fallback_model,
            # What is used right now, for the default data class: per kind of work and per agent.
            "in_use": {t: suite.models.pick(t, settings.default_data_class) for t in settings.tiers},
            "agent_in_use": {a: suite.models.pick(ag.default_tier, settings.default_data_class, a)
                             for a, ag in suite.registry.agents.items()},
            "offline_model": suite.general().offline_model,
            "offline_default": suite.offline_default,
            "agent_overrides": settings.agent_overrides,
            "warnings": suite.warnings,
            "pending_approvals": len(store.approvals(status="pending")),
        }

    @app.get("/api/agents/{agent_id}")
    def agent(agent_id: str):
        a = suite.registry.agents.get(agent_id)
        if not a:
            raise HTTPException(404, "agent not found")
        # Capability summary only: instructions, persona and lineage stay server-side.
        return {**a.public(),
                "skills_detail": [suite.registry.skills[s].model_dump(include={"id", "description"})
                                  for s in a.core_skills + a.skills]}

    @app.get("/api/playbooks/{pid}")
    def playbook(pid: str):
        p = suite.playbooks.get(pid)
        if not p:
            raise HTTPException(404, "playbook not found")
        return p.card()

    @app.post("/api/route")
    async def do_route(body: RouteRequest):
        if not body.text.strip():
            raise HTTPException(400, "text is required")
        return await route(body.text, suite.playbooks, suite.models, body.data_class or settings.default_data_class)

    # ---------------------------------------------------------------- files

    @app.post("/api/files")
    async def upload(file: UploadFile = File(...)):
        data = await file.read()
        try:
            media, text = extract_text(file.filename or "upload", data)
        except UnsupportedFile as e:
            raise HTTPException(415, str(e)) from e
        except Exception as e:  # noqa: BLE001 - corrupt files
            raise HTTPException(422, f"could not read {file.filename}: {type(e).__name__}") from e
        meta = store.add_file(file.filename or "upload", media, text)
        store.audit("file_uploaded", None, file=meta["id"], name=meta["name"], chars=meta["chars"])
        return meta

    # ---------------------------------------------------------------- runs

    @app.post("/api/runs", status_code=201)
    async def start_run(body: RunRequest):
        if body.playbook_id not in suite.playbooks:
            raise HTTPException(404, "playbook not found")
        try:
            rid = await eng.start(body.playbook_id, body.inputs, body.data_class, body.options)
        except RunStopped as e:
            raise HTTPException(423, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return {"id": rid}

    @app.get("/api/runs")
    def runs(limit: int = 100):
        return store.runs(limit=min(limit, 500))

    @app.get("/api/runs/{rid}")
    def run(rid: str):
        r = store.run(rid)
        if not r:
            raise HTTPException(404, "run not found")
        return {**r, "steps": store.steps(rid), "approvals": store.approvals(run_id=rid),
                "playbook": suite.playbooks[r["playbook_id"]].card() if r["playbook_id"] in suite.playbooks else None}

    @app.delete("/api/runs")
    def delete_demo_runs(demo: bool = False):
        """Delete the runs made by the demo provider of earlier versions (the only bulk delete offered)."""
        if not demo:
            raise HTTPException(422, "only demo=true is supported")
        ids = [i for i in store.demo_run_ids() if i not in eng._tasks]
        n = store.delete_runs(ids)
        store.audit("runs_deleted", None, count=n, reason="demo runs", by="ui")
        return {"deleted": n}

    @app.delete("/api/runs/{rid}")
    def delete_run(rid: str):
        if not store.run(rid):
            raise HTTPException(404, "run not found")
        if rid in eng._tasks:
            raise HTTPException(409, "Stop the run before deleting it.")
        store.delete_runs([rid])
        store.audit("run_deleted", rid, by="ui")
        return {"deleted": 1}

    @app.post("/api/runs/{rid}/cancel")
    def cancel(rid: str):
        if not store.run(rid):
            raise HTTPException(404, "run not found")
        eng.cancel(rid)
        return store.run(rid)

    @app.post("/api/runs/{rid}/resume")
    def resume(rid: str):
        try:
            eng.resume(rid)
        except (ValueError, RunStopped) as e:
            raise HTTPException(409, str(e)) from e
        return {"id": rid}

    @app.post("/api/runs/{rid}/export/save")
    def export_save(rid: str, format: Literal["md", "html"] = "md"):
        """Export a deliverable into the outputs folder (Runs/) and say where it went."""
        r = store.run(rid)
        if not r or not r.get("deliverable"):
            raise HTTPException(404, "no deliverable yet")
        if not suite.outputs.root:
            raise HTTPException(409, "The outputs folder is switched off; choose one in Settings > Policies & budgets.")
        if r.get("data_class") == "restricted":
            raise HTTPException(409, "Restricted deliverables are not saved to the outputs folder, which may be synced "
                                     "to a cloud drive.")
        suite.outputs.save_run(r)
        path = suite.outputs.last_run_files.get(format)
        if not path:
            raise HTTPException(500, f"The file could not be written to {suite.outputs.root}; see the app log.")
        store.audit("exported", rid, format=format, saved=True)
        return {"name": path.name, "path": str(path), "folder": str(path.parent)}

    @app.get("/api/runs/{rid}/export")
    def export(rid: str, format: Literal["md", "html"] = "md"):
        r = store.run(rid)
        if not r or not r.get("deliverable"):
            raise HTTPException(404, "no deliverable yet")
        slug = re.sub(r"[^a-z0-9]+", "-", (r["title"] or "deliverable").lower()).strip("-")[:60] or "deliverable"
        store.audit("exported", rid, format=format)
        if format == "html":
            body = to_html(r["deliverable"], r["title"] or "Deliverable", settings.theme_dir)
            return Response(body, media_type="text/html; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{slug}.html"'})
        return Response(r["deliverable"], media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{slug}.md"'})

    # ---------------------------------------------------------------- approvals

    @app.get("/api/approvals")
    def approvals(status: str | None = "pending"):
        out = []
        for a in store.approvals(status=status or None):
            r = store.run(a["run_id"])
            out.append({**a, "run_title": r["title"] if r else "", "playbook_id": r["playbook_id"] if r else ""})
        return out

    @app.post("/api/approvals/{aid}")
    async def decide(aid: str, body: Decision):
        try:
            return await eng.decide(aid, body.decision, body.decided_by, body.note, body.edited)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(409, str(e)) from e

    @app.post("/api/approvals/{aid}/answer")
    async def answer(aid: str, body: InputAnswers):
        """Answers to a "your input is needed" pause; the steps that asked run again with them."""
        try:
            return await eng.answer(aid, body.answers, body.by, body.skip)
        except KeyError as e:
            raise HTTPException(404, str(e).strip("'")) from e
        except (ValueError, RunStopped) as e:
            raise HTTPException(409, str(e)) from e

    # ---------------------------------------------------------------- providers / connectors / admin

    @app.get("/api/providers")
    def providers():
        return {"providers": suite.models.describe(), "tiers": settings.tiers, "agent_overrides": settings.agent_overrides}

    # ---------------------------------------------------------------- offline mode and model endpoints

    @app.get("/api/admin/offline")
    def offline_state():
        return {"on": settings.offline, "override": suite.offline_override(), "default": suite.base["offline"]}

    @app.post("/api/admin/offline")
    async def offline_set(body: OfflineSwitch):
        on = await suite.set_offline(body.on, body.by)
        return {"on": on, "override": suite.offline_override(), "default": suite.base["offline"]}

    @app.get("/api/endpoints")
    def endpoints():
        return [public_endpoint(e) for e in suite.endpoints()]

    @app.post("/api/endpoints/discover")
    async def discover(body: Discover):
        """List the models an OpenAI-compatible server offers (GET {base_url}/models)."""
        import openai

        from .providers.openai_compat import OpenAICompatibleProvider
        cfg = settings.providers.get(body.provider) if body.provider else None
        if body.provider and cfg is None:
            raise HTTPException(404, "provider not found")
        raw = body.base_url or (cfg.base_url if cfg else None)
        if not raw:
            raise HTTPException(422, "Enter the server address first.")
        try:
            url = normalize_url(raw)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        locality = locality_of(url)
        if settings.offline and locality != "local":
            raise HTTPException(409, "Offline mode is on: only addresses on your own network can be used.")
        key = (body.api_key or "").strip() or (suite.models._api_key(cfg) if cfg else None) or "not-needed"
        probe = OpenAICompatibleProvider("probe", base_url=url, api_key=key, timeout_s=8, max_retries=0,
                                         http_client=suite.http_client)
        try:
            page = await probe.client.models.list()
            ids = sorted({m.id for m in page.data})
        except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
            raise HTTPException(502, f"The server at {url} refused the request (HTTP {e.status_code}): it needs an API key, "
                                     "or the key entered is wrong. Enter the key the server expects and try again.") from e
        except openai.NotFoundError as e:
            raise HTTPException(502, f"{url} has no model list (HTTP 404). OpenAI-compatible servers usually end in /v1, "
                                     "for example http://localhost:1234/v1.") from e
        except openai.APIConnectionError as e:
            raise HTTPException(502, f"Could not reach {url}. Check that the server is running and the address and port are right; "
                                     "for another device, that it listens on the network and both are on the same network.") from e
        except openai.APIStatusError as e:
            raise HTTPException(502, f"The server at {url} answered HTTP {e.status_code}.") from e
        except Exception as e:  # noqa: BLE001 - unexpected protocol errors
            raise HTTPException(502, f"Could not list models at {url}: {type(e).__name__}.") from e
        return {"base_url": url, "locality": locality, "models": ids}

    @app.post("/api/endpoints", status_code=201)
    def save_endpoint(body: Endpoint):
        if settings.offline and locality_of(body.base_url) != "local":
            raise HTTPException(409, "Offline mode is on: only addresses on your own network can be added.")
        suite.save_endpoint(body, "ui")
        saved = next(e for e in suite.endpoints() if e.id == body.id)
        return public_endpoint(saved)

    @app.delete("/api/endpoints/{eid}")
    def delete_endpoint(eid: str):
        if not suite.delete_endpoint(eid, "ui"):
            raise HTTPException(404, "endpoint not found")
        return {"deleted": eid}

    @app.put("/api/providers/{name}")
    def edit_provider(name: str, body: ProviderEdit):
        if name.startswith("ep-"):
            raise HTTPException(409, "Endpoints added in the app are changed under Model endpoints.")
        if body.base_url:
            try:
                body.base_url = normalize_url(body.base_url)
            except ValueError as e:
                raise HTTPException(422, str(e)) from e
        try:
            suite.save_provider(name, body, "ui")
        except KeyError as e:
            raise HTTPException(404, "provider not found") from e
        return next(p for p in suite.models.describe() if p["name"] == name)

    @app.delete("/api/providers/{name}/override")
    def reset_provider(name: str):
        if not suite.reset_provider(name, "ui"):
            raise HTTPException(404, "no changes to reset for this provider")
        return next(p for p in suite.models.describe() if p["name"] == name)

    @app.post("/api/providers/{name}/test")
    async def test_provider(name: str, model: str | None = None):
        if name not in settings.providers:
            raise HTTPException(404, "provider not found")
        ok, reason = suite.models.availability(name)
        if not ok:
            return {"ok": False, "detail": reason}
        ref = model or next((m.ref for m in settings.models if m.provider == name), None)
        if not ref:
            return {"ok": False, "detail": "no model configured for this provider"}
        mc = settings.model(ref)
        p = suite.models.provider(name)
        try:
            conv = p.start("You are a connectivity check.", "Reply with the single word OK.")
            r = await p.chat(conv, model=mc.model, tools=None, max_tokens=64)
            return {"ok": True, "model": r.model, "latency_ms": r.latency_ms, "reply": r.text[:80]}
        except ProviderError as e:
            return {"ok": False, "detail": str(e)[:400]}

    # ---------------------------------------------------------------- chat

    @app.get("/api/chats")
    def chats():
        return suite.chat.list()

    @app.post("/api/chats", status_code=201)
    def chat_start(body: ChatStart):
        try:
            return suite.chat.create(body.agent_id, body.data_class)
        except ChatError as e:
            raise HTTPException(422, str(e)) from e

    @app.get("/api/chats/{cid}")
    def chat_get(cid: str):
        try:
            return suite.chat.get(cid)
        except KeyError as e:
            raise HTTPException(404, "chat not found") from e

    @app.get("/api/chats/{cid}/messages/{index}/export")
    def chat_export(cid: str, index: int, format: Literal["md", "html"] = "md"):
        """One agent answer as a Markdown or standalone HTML file (HTML is built from the Markdown)."""
        from .chat import file_name
        try:
            chat = suite.chat.get(cid)
        except KeyError as e:
            raise HTTPException(404, "chat not found") from e
        msgs = chat["messages"]
        if not 0 <= index < len(msgs) or msgs[index].get("role") != "assistant":
            raise HTTPException(404, "no agent answer at that position")
        text = msgs[suite.chat.answer_source(chat, index)]["content"]  # a "saved the previous answer" note exports that answer
        f = msgs[index].get("file") or {}
        name = f["name"] if f.get("format") == format else file_name(text, chat["title"], format)
        store.audit("chat_exported", None, chat=cid, index=index, format=format)
        if format == "html":
            title = name.rsplit(".", 1)[0].replace("-", " ").capitalize()
            return Response(to_html(text, title, settings.theme_dir), media_type="text/html; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{name}"'})
        return Response(text, media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/chats/{cid}/messages/{index}/save")
    def chat_save(cid: str, index: int, format: Literal["md", "html"] = "md"):
        """The Save button: writes one answer as a new file into the outputs folder (Files/). Never overwrites."""
        try:
            return suite.chat.save_answer(cid, index, format)
        except KeyError as e:
            raise HTTPException(404, str(e).strip("'")) from e
        except ChatError as e:
            raise HTTPException(409, str(e)) from e

    @app.post("/api/chats/{cid}/messages")
    async def chat_send(cid: str, body: ChatMessage):
        try:
            return await suite.chat.send(cid, body.content, body.files)
        except KeyError as e:
            raise HTTPException(404, "chat not found") from e
        except ChatError as e:
            raise HTTPException(409, str(e)) from e

    @app.delete("/api/chats/{cid}")
    def chat_delete(cid: str):
        try:
            suite.chat.delete(cid)
        except KeyError as e:
            raise HTTPException(404, "chat not found") from e
        return {"deleted": 1}

    @app.get("/api/connectors")
    def connectors():
        return suite.connectors.describe()

    @app.put("/api/connectors/{cid}")
    async def edit_connector(cid: str, body: ConnectorEdit):
        try:
            await suite.save_connector(cid, body, "ui")
        except KeyError as e:
            raise HTTPException(404, "connector not found") from e
        except (FolderError, ValueError) as e:
            raise HTTPException(422, str(e)) from e
        return next(c for c in suite.connectors.describe() if c["id"] == cid)

    @app.delete("/api/connectors/{cid}/settings")
    async def reset_connector(cid: str):
        if cid not in suite.connectors.file_configs:
            raise HTTPException(404, "connector not found")
        await suite.reset_connector(cid, "ui")
        return next(c for c in suite.connectors.describe() if c["id"] == cid)

    @app.put("/api/settings/outputs")
    def edit_outputs(body: OutputsEdit):
        try:
            suite.set_outputs(body.path, body.off, "ui")
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return overview()

    @app.put("/api/settings/general")
    def edit_general(body: GeneralEdit):
        try:
            suite.save_general(body, "ui")
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return overview()

    @app.delete("/api/settings/general/{part}")
    def reset_general(part: str):
        try:
            suite.reset_general(part, "ui")
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return overview()

    @app.put("/api/settings/profile")
    def edit_profile(body: ProfileEdit):
        suite.save_profile(body, "ui")
        return overview()["profile"]

    @app.delete("/api/settings/profile")
    def reset_profile():
        suite.save_profile(None, "ui")
        return overview()["profile"]

    @app.post("/api/connectors/{cid}/connect")
    async def connect(cid: str):
        try:
            tools = await suite.connectors.tools(cid, allowed_only=False)
        except ConnectorError as e:
            raise HTTPException(409, str(e)) from e
        store.audit("connector_connected", None, connector=cid, tools=len(tools))
        return {"id": cid, "tools": [{"name": t.name, "allowed": t.allowed, "reason": t.reason, "description": t.description[:200]}
                                     for t in tools]}

    # Sign-in from the app (Microsoft 365): the connector's own server signs in with a code shown here.

    def signin_errors(e: Exception) -> HTTPException:
        if isinstance(e, KeyError):
            return HTTPException(404, "connector not found")
        return HTTPException(409, str(e))

    @app.get("/api/connectors/{cid}/signin")
    def signin_state(cid: str):
        try:
            s = suite.signin.get(cid)
        except (KeyError, SigninError) as e:
            raise signin_errors(e) from e
        return s.view() if s else {"connector": cid, "status": "none"}

    @app.post("/api/connectors/{cid}/signin")
    async def signin_start(cid: str, body: SigninStart | None = None):
        try:
            account = (body or SigninStart()).account
            s = await suite.signin.start(cid, account)
            if suite.connectors.configs[cid].signin.kind == "tool":
                suite.prefill_default(cid, account or "")
        except (KeyError, SigninError, ConnectorError) as e:
            raise signin_errors(e) from e
        store.audit("connector_signin_started", None, connector=cid, by="ui")
        return s.view()

    @app.delete("/api/connectors/{cid}/signin")
    async def signin_cancel(cid: str):
        try:
            s = await suite.signin.cancel(cid)
        except (KeyError, SigninError) as e:
            raise signin_errors(e) from e
        return s.view() if s else {"connector": cid, "status": "none"}

    @app.get("/api/connectors/{cid}/accounts")
    async def signin_accounts(cid: str):
        try:
            return {"accounts": await suite.signin.accounts(cid)}
        except (KeyError, SigninError, ConnectorError) as e:
            raise signin_errors(e) from e

    @app.post("/api/connectors/{cid}/client-file")
    async def upload_client_file(cid: str, file: UploadFile = File(...)):
        if cid not in suite.connectors.file_configs:
            raise HTTPException(404, "connector not found")
        try:
            await suite.save_client_file(cid, await file.read(MAX_CLIENT_FILE_BYTES + 1), "ui")
        except (ValueError, UnicodeDecodeError) as e:
            raise HTTPException(422, str(e) if isinstance(e, ValueError) else "That is not a text file.") from e
        return next(c for c in suite.connectors.describe() if c["id"] == cid)

    @app.delete("/api/connectors/{cid}/client-file")
    async def delete_client_file(cid: str):
        if cid not in suite.connectors.file_configs:
            raise HTTPException(404, "connector not found")
        try:
            await suite.remove_client_file(cid, "ui")
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return next(c for c in suite.connectors.describe() if c["id"] == cid)

    @app.post("/api/connectors/{cid}/accounts/use")
    async def signin_use_existing(cid: str):
        try:
            return {"accounts": await suite.use_signed_in(cid, "ui")}
        except (KeyError, SigninError, ConnectorError) as e:
            raise signin_errors(e) from e

    @app.delete("/api/connectors/{cid}/accounts/{account_id}")
    async def signin_sign_out(cid: str, account_id: str):
        try:
            return {"accounts": await suite.sign_out(cid, account_id, "ui")}
        except (KeyError, SigninError, ConnectorError) as e:
            raise signin_errors(e) from e

    @app.get("/api/admin/kill-switch")
    def kill_state():
        return {"on": eng.killed}

    @app.post("/api/admin/kill-switch")
    def kill(body: KillSwitch):
        eng.set_kill_switch(body.on, body.by)
        return {"on": eng.killed}

    @app.get("/api/audit")
    def audit(run_id: str | None = None, limit: int = 300):
        return store.audit_log(run_id, limit=min(limit, 2000))

    # ---------------------------------------------------------------- UI

    dist = Path(os.environ.get("SUITE_UI_DIR", settings.home / "frontend" / "dist"))
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (dist / path).resolve()
            if path and dist.resolve() in target.parents and target.is_file():
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


def _lazy_app() -> FastAPI:
    logging.basicConfig(level=os.environ.get("SUITE_LOG_LEVEL", "INFO"))
    return create_app()


app = _lazy_app() if os.environ.get("SUITE_NO_AUTOAPP") != "1" else None
