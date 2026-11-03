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
from .connectors import ConnectorError, ConnectorManager
from .endpoints import Endpoint, ModelEdit, ProviderOverride, apply_runtime, locality_of, normalize_url
from .engine import Engine, RunStopped
from .export import to_html
from .files import UnsupportedFile, extract_text
from .playbooks import load_playbooks
from .providers import ModelRouter, ProviderError
from .registry import Registry
from .router import route
from .settings import Settings, load_profile, load_settings
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


class Discover(BaseModel):
    base_url: str | None = None
    provider: str | None = None  # use this provider's address and saved key unless given here
    api_key: str | None = None


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
        self.registry = Registry(settings.registry_dir, settings.policies_dir)
        self.connectors = connectors or ConnectorManager.from_file(settings.connectors_path, offline=settings.offline)
        self.playbooks, self.warnings = load_playbooks(settings.playbooks_dir, self.registry, set(self.connectors.configs))
        self.store = Store(settings.data_dir / "suite.db")
        self.models = ModelRouter(settings, http_client=http_client)
        self.profile = load_profile(settings)
        self.engine = Engine(settings, self.registry, self.playbooks, self.models, self.connectors, self.store, self.profile)
        # File/env configuration is the base; choices made in the app are layered on top and persisted.
        self.base = {"providers": dict(settings.providers), "models": list(settings.models),
                     "tiers": {k: list(v) for k, v in settings.tiers.items()}, "offline": settings.offline}
        self.http_client = http_client
        self.apply()

    # ------------------------------------------------------------ runtime configuration

    def endpoints(self) -> list[Endpoint]:
        return [Endpoint.model_validate(e) for e in self.store.get_setting("endpoints", [])]

    def offline_override(self) -> bool | None:
        return self.store.get_setting("offline_override", None)

    def provider_overrides(self) -> dict[str, ProviderOverride]:
        return {k: ProviderOverride.model_validate(v) for k, v in self.store.get_setting("provider_overrides", {}).items()}

    def apply(self) -> None:
        override = self.offline_override()
        offline = self.base["offline"] if override is None else bool(override)
        apply_runtime(self.settings, self.base, self.endpoints(), offline, self.provider_overrides())
        self.connectors.offline = offline
        self.models._instances = {}  # addresses or keys may have changed

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
        await suite.connectors.shutdown()

    app = FastAPI(title="Productivity Suite", version=__version__, lifespan=lifespan)
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
            "profile_configured": bool(settings.profile_path and settings.profile_path.name == "profile.yaml"),
            "warnings": suite.warnings,
            "pending_approvals": len(store.approvals(status="pending")),
        }

    @app.get("/api/agents/{agent_id}")
    def agent(agent_id: str):
        a = suite.registry.agents.get(agent_id)
        if not a:
            raise HTTPException(404, "agent not found")
        return {**a.public(), "instructions": a.instructions,
                "modes_detail": {k: v.model_dump() for k, v in a.modes.items()},
                "persona_text": a.persona.text if a.persona else None,
                "skills_detail": [suite.registry.skills[s].model_dump() for s in a.core_skills + a.skills]}

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

    @app.get("/api/connectors")
    def connectors():
        return suite.connectors.describe()

    @app.post("/api/connectors/{cid}/connect")
    async def connect(cid: str):
        try:
            tools = await suite.connectors.tools(cid, allowed_only=False)
        except ConnectorError as e:
            raise HTTPException(409, str(e)) from e
        store.audit("connector_connected", None, connector=cid, tools=len(tools))
        return {"id": cid, "tools": [{"name": t.name, "allowed": t.allowed, "reason": t.reason, "description": t.description[:200]}
                                     for t in tools]}

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
