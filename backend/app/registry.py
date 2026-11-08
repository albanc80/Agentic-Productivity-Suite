"""Loads the compiled agent registry (registry/) and the authored output policies."""

from __future__ import annotations

import base64
import binascii
import io
import os
import zipfile
from pathlib import Path, PurePosixPath
from typing import ClassVar

import yaml
from pydantic import BaseModel, Field

NOT_INSTALLED = ("Agent instructions are not installed in this copy of the app, so agents work from their short public "
                 "descriptions and answers are more generic. To fix it, install a release built with the agent pack, or import "
                 "your agent pack in Settings → System → Agent instructions.")
MAX_PACK_FILES = 500
MAX_PACK_FILE_BYTES = 2 * 1024 * 1024
MAX_PACK_BYTES = 25 * 1024 * 1024


def _safe_name(name: str) -> str:
    """Only the file name is kept, so nothing can be written outside the agents folder."""
    base = PurePosixPath(name.replace("\\", "/")).name
    if not base or base.startswith("."):
        raise ValueError(f"{name!r} is not a usable file name.")
    return base


def _yaml_from_zip(data: bytes) -> dict[str, bytes]:
    """The agent files in a .zip: those under an ``agents/`` folder if there is one, else every .yaml file."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ValueError("That .zip file could not be opened.") from e
    with zf:
        entries = [i for i in zf.infolist() if not i.is_dir() and i.filename.lower().endswith((".yaml", ".yml"))
                   and not PurePosixPath(i.filename).name.startswith(".") and "__MACOSX" not in i.filename]
        under_agents = [i for i in entries if "agents" in PurePosixPath(i.filename).parts[:-1]]
        entries = under_agents or entries
        if len(entries) > MAX_PACK_FILES:
            raise ValueError(f"That .zip has more than {MAX_PACK_FILES} files; it does not look like an agent pack.")
        if sum(i.file_size for i in entries) > MAX_PACK_BYTES or any(i.file_size > MAX_PACK_FILE_BYTES for i in entries):
            raise ValueError("That .zip is too large to be an agent pack.")
        return {_safe_name(i.filename): zf.read(i) for i in entries}


# ---------------------------------------------------------------- built-in agent pack (ADR 0007)
# The pack ships inside the installers encrypted (registry/agent-pack.enc). The key is written into the build
# from a repository secret and never committed. This keeps the text out of the public repository, the
# installer's plain files and the UI; it does not stop someone who extracts the key from an installer.

PACK_MAGIC = b"APSPACK1"
PACK_AAD = b"agentic-productivity-suite/agent-pack/v1"
PACK_KEY_ENV = "SUITE_AGENT_PACK_KEY"


def parse_pack_key(raw: str) -> bytes:
    """A key is 32 random bytes, written as URL-safe base64 (what ``scripts/agent_pack.py genkey`` makes)."""
    try:
        key = base64.urlsafe_b64decode(raw.strip().encode() + b"=" * (-len(raw.strip()) % 4))
    except (ValueError, binascii.Error) as e:
        raise ValueError("The agent pack key is not valid base64.") from e
    if len(key) != 32:
        raise ValueError("The agent pack key must be 32 bytes.")
    return key


def encrypt_pack(zip_bytes: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return PACK_MAGIC + nonce + AESGCM(key).encrypt(nonce, zip_bytes, PACK_AAD)


def decrypt_pack(blob: bytes, key: bytes) -> bytes:
    """The pack's .zip bytes, in memory only. ValueError when the file or the key is wrong."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith(PACK_MAGIC) or len(blob) < len(PACK_MAGIC) + 12 + 16:
        raise ValueError("it is not an encrypted agent pack")
    nonce, body = blob[len(PACK_MAGIC):len(PACK_MAGIC) + 12], blob[len(PACK_MAGIC) + 12:]
    try:
        return AESGCM(key).decrypt(nonce, body, PACK_AAD)
    except InvalidTag as e:
        raise ValueError("the key does not match this pack") from e


def read_pack_key(home: Path) -> str | None:
    """The key: SUITE_AGENT_PACK_KEY if set (an empty value means none), else the one the build wrote."""
    if PACK_KEY_ENV in os.environ:
        return os.environ[PACK_KEY_ENV].strip() or None
    f = home / "config" / "agent-pack.key"
    try:
        return f.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


class Persona(BaseModel):
    id: str
    text: str


class AgentMode(BaseModel):
    summary: str = ""
    instructions: str = ""


class Agent(BaseModel):
    """Public card (registry/catalog.yaml) merged with the private layer when it is present."""

    id: str
    name: str
    desk: str
    summary: str
    capabilities: list[str] = Field(default_factory=list)
    default_tier: str = "specialist"
    safety_critical: bool = False
    core_skills: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    default_mode: str | None = None
    modes: dict[str, AgentMode] = Field(default_factory=dict)
    # Private layer, never committed or sent to the UI.
    persona: Persona | None = None
    merged_from: list[str] = Field(default_factory=list)
    source: list[str] = Field(default_factory=list)
    instructions: str = ""

    # Never sent to the UI: the instructions, the persona and where the agent came from
    # (source files and the agents it was merged from) are the suite's own design.
    PRIVATE: ClassVar[frozenset[str]] = frozenset({"instructions", "modes", "persona", "merged_from", "source"})

    @property
    def has_private(self) -> bool:
        return bool(self.instructions.strip())

    def instructions_for(self, mode: str | None) -> str:
        if mode and mode != self.default_mode:
            if mode not in self.modes:
                raise KeyError(f"agent {self.id} has no mode '{mode}'")
            return self.modes[mode].instructions or self.fallback_instructions(mode)
        return self.instructions or self.fallback_instructions(None)

    def fallback_instructions(self, mode: str | None) -> str:
        """Used when the private layer is not installed: the agent works from its public card."""
        lines = [f"You are the {self.name}. {self.summary}", "", "What you do:"]
        lines += [f"- {c}" for c in self.capabilities]
        if mode and mode in self.modes:
            lines += ["", f"Current mode: {mode}. {self.modes[mode].summary}"]
        lines += ["", "Stay inside this remit and say when a request is outside it. Separate facts from "
                      "assumptions, state every assumption, and never invent data, sources or results."]
        if self.safety_critical:
            lines += ["You are advisory only. Never override validated engineering or safety rules; "
                      "a qualified person makes and owns the decision."]
        return "\n".join(lines) + "\n"

    def public(self) -> dict:
        """What the UI may show: identity, capability summary, skills, tools and mode summaries."""
        d = self.model_dump(exclude=set(self.PRIVATE))
        d["modes"] = {k: v.summary for k, v in self.modes.items()}
        return d


class Desk(BaseModel):
    id: str
    name: str
    lead: str
    summary: str
    members: list[str]


class Skill(BaseModel):
    id: str
    description: str
    chars: int
    resources: list[str] = Field(default_factory=list)


class Registry:
    """Agents, desks and skills.

    The repository holds only the public catalog (``registry/catalog.yaml``). Each agent's full
    instructions, persona, mode instructions and lineage live in a private directory outside the
    repository (``<private>/agents/<agent-id>.yaml``) and are merged in at load time.
    """

    def __init__(self, registry_dir: Path, policies_dir: Path, private_dir: Path | None = None,
                 pack_file: Path | None = None, pack_key: str | None = None):
        self.dir = registry_dir
        self.policies_dir = policies_dir
        self.private_dir = private_dir
        self.pack_file, self._pack_key = pack_file, pack_key  # the key is never logged, returned or stored
        self.layer: dict[str, str] = {}  # agent id -> "built-in" or "imported": where its instructions came from
        self.warnings: list[str] = []
        self.agents: dict[str, Agent] = {}
        catalog = yaml.safe_load((registry_dir / "catalog.yaml").read_text(encoding="utf-8"))["agents"]
        for card in catalog:
            card = dict(card)
            card["modes"] = {k: {"summary": v} for k, v in (card.get("modes") or {}).items()}
            a = Agent.model_validate(card)
            self.agents[a.id] = a
        desks = yaml.safe_load((registry_dir / "desks.yaml").read_text(encoding="utf-8"))["desks"]
        self.desks = {d["id"]: Desk.model_validate(d) for d in desks}
        idx = yaml.safe_load((registry_dir / "skills" / "index.yaml").read_text(encoding="utf-8"))["skills"]
        self.skills = {s["id"]: Skill.model_validate(s) for s in idx}
        if not self.agents:
            raise RuntimeError(f"No agents found in {registry_dir / 'catalog.yaml'}.")
        self._load_private()

    def _builtin_files(self) -> dict[str, bytes]:
        """The agent files of the encrypted pack built into the app, decrypted in memory; {} when there is none."""
        if not self.pack_file or not self.pack_file.is_file() or not self._pack_key:
            return {}
        try:
            return _yaml_from_zip(decrypt_pack(self.pack_file.read_bytes(), parse_pack_key(self._pack_key)))
        except (OSError, ValueError) as e:
            self.warnings.append(f"The agent instructions built into this app could not be opened ({e}). "
                                 "Agents use an imported pack if there is one, else their public descriptions.")
            return {}

    def _folder_files(self) -> dict[str, bytes] | None:
        d = self.private_dir / "agents" if self.private_dir else None
        if not d or not d.is_dir():
            return None
        out = {}
        for p in sorted(d.glob("*.yaml")):
            try:
                out[p.name] = p.read_bytes()
            except OSError as e:
                self.warnings.append(f"Agent pack file {p.name} could not be read ({type(e).__name__}: {e}); ignored.")
        return out

    def _load_private(self) -> None:
        """Built-in pack first, then an imported pack on top: an imported file replaces that agent's built-in one."""
        builtin, folder = self._builtin_files(), self._folder_files()
        if not builtin and folder is None:
            self.warnings.append(NOT_INSTALLED)
            return
        for label, files in (("built-in", builtin), ("imported", folder or {})):
            for name, data in sorted(files.items()):
                self._apply(name, data, label)
        missing = [a.id for a in self.agents.values() if not a.has_private]
        if missing:
            self.warnings.append(f"{len(missing)} agent(s) have no instructions in the agent pack and run on their public "
                                 f"capability summary: {', '.join(missing)}.")

    def _apply(self, name: str, data: bytes, label: str) -> None:
        try:
            raw = yaml.safe_load(data.decode("utf-8")) or {}
            if not isinstance(raw, dict):
                raise ValueError("it is not a YAML mapping")
            a = self.agents.get(str(raw.get("id", "")))
            if not a:
                self.warnings.append(f"Agent pack file {name} matches no agent in the catalog; ignored.")
                return
            persona = Persona.model_validate(raw["persona"]) if raw.get("persona") else None
        except Exception as e:  # one bad file never stops the app from starting
            self.warnings.append(f"Agent pack file {name} could not be read ({type(e).__name__}: {e}); ignored.")
            return
        a.instructions = str(raw.get("instructions") or "")
        a.persona = persona
        a.merged_from = list(raw.get("merged_from") or [])
        a.source = list(raw.get("source") or [])
        for m in a.modes.values():
            m.instructions = ""
        for mname, text in (raw.get("modes") or {}).items():
            if mname in a.modes:
                a.modes[mname].instructions = text or ""
            else:
                self.warnings.append(f"Agent pack file {name} has mode '{mname}', which the catalog does not list; ignored.")
        if a.has_private:
            self.layer[a.id] = label

    def reload_private(self, private_dir: Path | None = None) -> None:
        """Re-read the private layer in place (after an import in Settings), so no restart is needed.
        Agents are updated in place because the engine and chat hold this registry."""
        if private_dir is not None:
            self.private_dir = private_dir
        for a in self.agents.values():
            a.instructions, a.persona, a.merged_from, a.source = "", None, [], []
            for m in a.modes.values():
                m.instructions = ""
        self.warnings, self.layer = [], {}
        self._load_private()

    def private_status(self) -> dict:
        """For Settings: whether the agent pack is installed and how many agents it covers. No content."""
        d = self.private_dir / "agents" if self.private_dir else None
        built_in = sum(1 for v in self.layer.values() if v == "built-in")
        return {"installed": bool(d and d.is_dir()) or built_in > 0,
                "folder": str(self.private_dir) if self.private_dir else None,
                "agents_total": len(self.agents),
                "agents_with_instructions": sum(1 for a in self.agents.values() if a.has_private),
                "built_in": built_in, "imported": sum(1 for v in self.layer.values() if v == "imported")}

    def import_private(self, uploads: list[tuple[str, bytes]], target: Path) -> dict:
        """Install agent pack files (a .zip, or .yaml files) into ``target/agents`` and reload.

        Every file is checked before anything is written: it must parse, be a mapping and name an agent in
        the catalog. Files that match no agent are skipped and reported. Existing files with the same name
        are replaced; others are kept. Raises ValueError with a readable reason when nothing usable is found.
        """
        found: dict[str, bytes] = {}
        for name, data in uploads:
            if name.lower().endswith(".zip"):
                found.update(_yaml_from_zip(data))
            elif name.lower().endswith((".yaml", ".yml")):
                found[_safe_name(name)] = data
            else:
                raise ValueError(f"{name}: choose a .zip agent pack or the agents' .yaml files.")
        if not found:
            raise ValueError("No agent files (.yaml) were found in what you chose.")
        good: dict[str, bytes] = {}
        skipped: list[str] = []
        for fname, data in found.items():
            try:
                raw = yaml.safe_load(data.decode("utf-8")) or {}
            except (UnicodeDecodeError, yaml.YAMLError) as e:
                raise ValueError(f"{fname} is not a readable YAML file ({type(e).__name__}).") from e
            if not isinstance(raw, dict) or str(raw.get("id", "")) not in self.agents:
                skipped.append(fname)
                continue
            if raw.get("persona"):
                try:
                    Persona.model_validate(raw["persona"])
                except Exception as e:
                    raise ValueError(f"{fname}: its persona is not valid ({e.__class__.__name__}).") from e
            good[f"{raw['id']}.yaml"] = data
        if not good:
            raise ValueError("None of the files names an agent in this app's catalog, so nothing was installed. "
                             "Check that you chose the agent pack for this app.")
        agents_dir = target / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)  # plain mkdir: never mkdtemp (owner-only folders on Windows)
        for fname, data in good.items():
            tmp = agents_dir / f".{fname}.part"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # the person's own design: readable by them only
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, agents_dir / fname)
        self.reload_private(target)
        return {"imported_files": sorted(good), "skipped": sorted(skipped), **self.private_status()}

    def agent(self, agent_id: str) -> Agent:
        if agent_id not in self.agents:
            raise KeyError(f"unknown agent '{agent_id}'")
        return self.agents[agent_id]

    def skill_text(self, skill_id: str, resource: str | None = None) -> str:
        """Read a skill or one of its resources. Paths are confined to the skill folder."""
        if skill_id not in self.skills:
            raise KeyError(f"unknown skill '{skill_id}'")
        base = (self.dir / "skills" / skill_id).resolve()
        target = (base / (resource or "SKILL.md")).resolve()
        if base not in target.parents and target != base / "SKILL.md":
            raise PermissionError("resource path escapes the skill folder")
        if not target.exists():
            raise KeyError(f"skill '{skill_id}' has no resource '{resource}'")
        return target.read_text(encoding="utf-8")

    def policy_text(self, policy_id: str) -> str:
        p = self.policies_dir / f"{policy_id}.md"
        if not p.exists():
            raise KeyError(f"unknown output policy '{policy_id}'")
        return p.read_text(encoding="utf-8").strip()
