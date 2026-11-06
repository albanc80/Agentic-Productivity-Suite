"""Runtimes connectors need (uv, Node.js, the GitHub MCP server): found on the computer, or installed by the app.

Connectors run community servers through ``uvx`` (Google Workspace, Jira and Confluence), ``npx`` (Microsoft 365,
Azure DevOps) or GitHub's own server program (GitHub). People should not have to install any of them, Docker
included, and the installers should not grow by shipping them. So:

1. A copy already on the computer is used when it is new enough (``min_version``). Nothing is duplicated, and a
   newer copy than the app's always wins.
2. Otherwise the installer gets it: the .msi and the .deb run the app once with ``--install-tools`` at the end
   of the install, which downloads what is missing or too old into the app's folder (``<app>/tools``).
   A failed download (offline, proxy) never fails the install.
3. Otherwise the app downloads it the first time a connector needs it, into its data folder
   (``<data>/tools``): no administrator rights, nothing added to the system PATH.

uv fetches the Python it needs by itself.

Every download is a fixed release, never a search: the version is pinned, the address is the project's own
release, and the file must match the SHA-256 written below before anything is unpacked. uv's checksums come
from its GitHub release; Node's from the release's SHASUMS256.txt on nodejs.org. Unpacking keeps every file
inside the tool's folder (no absolute paths, no links that point outside).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("suite.tools")


class ToolError(Exception):
    """A tool could not be downloaded; the message is shown to the person as it is."""


@dataclass(frozen=True)
class Tool:
    name: str  # shown to people: "uv", "Node.js"
    key: str  # folder name: tools/<key>-<version>
    version: str
    url: str  # {version} and {asset}
    builds: dict[tuple[str, str], tuple[str, str]]  # (OS, machine) -> (asset, SHA-256)
    commands: frozenset[str]  # commands it provides (without .exe/.cmd)
    program: str  # the program that reports the version: node for npx, uv for uvx
    min_version: tuple[int, ...]  # oldest version on the computer that connectors may use
    whole: bool  # True: unpack the whole archive (Node needs npm's files); False: only the named programs
    programs: dict[str, tuple[str, ...]] = field(default_factory=dict)  # OS -> programs taken out when not whole
    posix_bin: str = ""  # where the commands are after unpacking, on Linux and macOS ("bin" for Node)

    def folder(self, root: Path) -> Path:
        """Where the app keeps this version under a tools folder (``<app>/tools`` or ``<data>/tools``)."""
        return root / f"{self.key}-{self.version}"

    def bin_dir(self, root: Path) -> Path:
        return self.folder(root) / ("" if sys.platform == "win32" else self.posix_bin)

    def installed(self, root: Path) -> bool:
        return (self.folder(root) / ".complete").is_file()


UV = Tool(
    name="uv", key="uv", version="0.11.32",
    url="https://github.com/astral-sh/uv/releases/download/{version}/{asset}",
    builds={
        ("linux", "x86_64"): ("uv-x86_64-unknown-linux-gnu.tar.gz",
                              "aab924fd522efd06f1c5f3b93a243864fc453132c94b2dc49f1371b528a4b967"),
        ("linux", "aarch64"): ("uv-aarch64-unknown-linux-gnu.tar.gz",
                               "4d4fa08d95b06642e5800df6a22bd71455f23f988269e18da2847971d8c0bf31"),
        ("darwin", "x86_64"): ("uv-x86_64-apple-darwin.tar.gz",
                               "77f5ca26c0de20e992a3677a174fe1121ee25c36f9b1434a863f75bf077a05eb"),
        ("darwin", "aarch64"): ("uv-aarch64-apple-darwin.tar.gz",
                                "ed336d0ba49db8ef89b2b41fffa372ce63bd032f22a56f001c265891aec32829"),
        ("win32", "x86_64"): ("uv-x86_64-pc-windows-msvc.zip",
                              "acfde570451cfdb8689fa159a138ee805ba4e241c466432750302c86254b0984"),
        ("win32", "aarch64"): ("uv-aarch64-pc-windows-msvc.zip",
                               "a7427ea0440bb826b6716d1837ff3d173b8e7d496cb09ee8f456b4e023a2fdcd"),
    },
    commands=frozenset({"uv", "uvx"}), program="uv", min_version=(0, 5, 0), whole=False,
    programs={"win32": ("uv.exe", "uvx.exe"), "posix": ("uv", "uvx")},
)

NODE = Tool(
    name="Node.js", key="node", version="v24.22.2",  # Node 24 LTS (Krypton)
    url="https://nodejs.org/dist/{version}/{asset}",
    builds={
        ("linux", "x86_64"): ("node-v24.22.2-linux-x64.tar.xz",
                              "48cc0e21e048790e54c0cf5749c2725005313d652651c40b7a21feb9697aaf75"),
        ("linux", "aarch64"): ("node-v24.22.2-linux-arm64.tar.xz",
                               "eb187837a2230d4047161ac0be008584e16b46f726e9c9490ee35dc6b17d9ba8"),
        ("darwin", "x86_64"): ("node-v24.22.2-darwin-x64.tar.gz",
                               "d5e336d588c45be0c37dbd52cc29895593009ca4997a77a1fd02815131ed0e52"),
        ("darwin", "aarch64"): ("node-v24.22.2-darwin-arm64.tar.gz",
                                "aa9549349e47dffaa42dcf95d6e06ade8c4bdafc980979883b88767670df385a"),
        ("win32", "x86_64"): ("node-v24.22.2-win-x64.zip",
                              "ca1bff5d8ead13c9f2ea404a176db46bd430704d5b5113734049fa365e7799e2"),
        ("win32", "aarch64"): ("node-v24.22.2-win-arm64.zip",
                               "f47968c213105077f64c6510f007632c0ca2574802a0b5067c327c49abe1c468"),
    },
    commands=frozenset({"node", "npx", "npm"}), program="node", min_version=(20, 0, 0), whole=True, posix_bin="bin",
)

GITHUB_MCP = Tool(
    name="GitHub MCP server", key="github-mcp-server", version="2.0.3",  # github/github-mcp-server, MIT
    url="https://github.com/github/github-mcp-server/releases/download/v{version}/{asset}",
    builds={  # from github-mcp-server_2.0.3_checksums.txt in the release
        ("linux", "x86_64"): ("github-mcp-server_Linux_x86_64.tar.gz",
                              "f797c20fe02a755865d0e2d46184ab47e31bf1619b0855b8d89c531e45a651c2"),
        ("linux", "aarch64"): ("github-mcp-server_Linux_arm64.tar.gz",
                               "5d2ddc71273fec8917e8f42cf19f26a6bd7acbb679b3a57de2917018b2eadf82"),
        ("darwin", "x86_64"): ("github-mcp-server_Darwin_x86_64.tar.gz",
                               "115350858c3287843274efbf45e821d98f15d3304cb2c074740461ed32b45598"),
        ("darwin", "aarch64"): ("github-mcp-server_Darwin_arm64.tar.gz",
                                "5c95c01f75a7ec2370607e989b2968d314b02a54d78af8a9fdf38f3dfe6135f4"),
        ("win32", "x86_64"): ("github-mcp-server_Windows_x86_64.zip",
                              "f0e1b9880a1b88730d1250d1c25cfee39617ec3e800a7a252f2279cd0c8394e0"),
        ("win32", "aarch64"): ("github-mcp-server_Windows_arm64.zip",
                               "d1321c411023c9a08e7709c2e9689551e3bff5a57033a3e5ff5f2c1db0c67a6f"),
    },
    commands=frozenset({"github-mcp-server"}), program="github-mcp-server", min_version=(2, 0, 0), whole=False,
    programs={"win32": ("github-mcp-server.exe",), "posix": ("github-mcp-server",)},
)

TOOLS = (UV, NODE, GITHUB_MCP)
_lock = asyncio.Lock()


def platform_key() -> tuple[str, str]:
    osname = "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    return osname, machine


def tool_for(command: str) -> Tool | None:
    """The tool that provides a command (``npx``, ``C:\\...\\npx.cmd``, ``uvx``), if the app can download it."""
    base = os.path.basename(command).lower()
    for ext in (".exe", ".cmd", ".bat"):
        base = base.removesuffix(ext)
    return next((t for t in TOOLS if base in t.commands), None)


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 - fixed https address, checked below
        return r.read()


# ---------------------------------------------------------------- what the computer already has

VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_versions: dict[tuple[str, float], tuple[int, ...] | None] = {}


def version_of(program: str) -> tuple[int, ...] | None:
    """The version a program reports (``node --version``, ``uv --version``); None if it does not say."""
    try:
        stamp = os.stat(program).st_mtime
    except OSError:
        return None
    if (program, stamp) not in _versions:
        try:
            out = subprocess.run([program, "--version"], capture_output=True, text=True, timeout=20,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            m = VERSION_RE.search(out or "")
            _versions[(program, stamp)] = tuple(int(x or 0) for x in m.groups()) if m else None
        except (OSError, subprocess.SubprocessError):
            _versions[(program, stamp)] = None
    return _versions[(program, stamp)]


def on_computer(tool: Tool, path: str | None) -> str | None:
    """The tool's program on this PATH when it is new enough to use, else None (absent or too old). A copy whose
    version cannot be read is used: nothing suggests it is too old."""
    found = shutil.which(tool.program, path=path)
    if not found:
        return None
    version = version_of(found)
    return found if version is None or version >= tool.min_version else None


def find(tool: Tool, path: str | None, roots: list[Path]) -> tuple[str, Path | None] | None:
    """Where connectors get this tool: ("computer", None) for a good copy on PATH, ("app", its bin folder) for
    the one the installer or the app downloaded, or None when it still has to be downloaded."""
    if on_computer(tool, path):
        return "computer", None
    for root in roots:
        if tool.installed(root):
            return "app", tool.bin_dir(root)
    return None


def _open_archive(asset: str, data: bytes):
    if asset.endswith(".zip"):
        return zipfile.ZipFile(io.BytesIO(data))
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:xz" if asset.endswith(".xz") else "r:gz")


def _unpack_whole(asset: str, data: bytes, staging: Path) -> None:
    """Unpack everything under the archive's single top folder into ``staging``, keeping it all inside."""
    root = staging.resolve()
    with _open_archive(asset, data) as archive:
        if isinstance(archive, zipfile.ZipFile):
            for info in archive.infolist():
                parts = Path(info.filename).parts[1:]  # drop node-vX-win-x64/
                if not parts or info.is_dir():
                    continue
                target = (staging / Path(*parts)).resolve()
                if not target.is_relative_to(root):
                    raise ToolError("The download contained a file outside its folder, so it was not used.")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
        else:
            members = []
            for m in archive.getmembers():
                parts = Path(m.name).parts[1:]
                if not parts:
                    continue
                m.name = str(Path(*parts))
                members.append(m)
            try:  # the "data" filter refuses absolute paths, .. and links that leave the folder
                archive.extractall(staging, members=members, filter="data")
            except tarfile.FilterError as e:
                raise ToolError("The download contained a file outside its folder, so it was not used.") from e


def _unpack_programs(tool: Tool, asset: str, data: bytes, staging: Path) -> None:
    names = tool.programs["win32" if sys.platform == "win32" else "posix"]
    with _open_archive(asset, data) as archive:
        if isinstance(archive, zipfile.ZipFile):
            members = {Path(n).name: n for n in archive.namelist() if not n.endswith("/")}
            payload = {n: archive.read(members[n]) for n in names if n in members}
        else:
            members = {Path(m.name).name: m for m in archive.getmembers() if m.isfile()}
            payload = {n: archive.extractfile(members[n]).read() for n in names if n in members}
    if set(payload) != set(names):
        raise ToolError(f"The {tool.name} download did not contain the expected programs.")
    for name, body in payload.items():  # by name only: nothing in the archive chooses where files go
        target = staging / name
        target.write_bytes(body)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install(tool: Tool, root: Path, fetch: Callable[[str], bytes] = _fetch) -> Path:
    """Blocking: download the pinned release, check it and unpack it into the tool's folder."""
    key = platform_key()
    if key not in tool.builds:
        raise ToolError(f"The app has no {tool.name} download for {key[0]} on {key[1]}. "
                        f"Install {tool.name} yourself, then close and reopen the app.")
    asset, digest = tool.builds[key]
    try:
        data = fetch(tool.url.format(version=tool.version, asset=asset))
    except OSError as e:
        raise ToolError(f"Could not download {tool.name}, which this connector needs: {e}. "
                        "Check the internet connection and try again.") from e
    got = hashlib.sha256(data).hexdigest()
    if got != digest:
        raise ToolError(f"The {tool.name} download did not match its published checksum, so it was not used "
                        f"(expected {digest[:12]}…, got {got[:12]}…). Try again later.")
    dest = tool.folder(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{tool.key}-", dir=dest.parent))
    staging.chmod(0o755)  # mkdtemp makes it private; installed by root or SYSTEM, everyone must be able to run it
    try:
        if tool.whole:
            _unpack_whole(asset, data, staging)
        else:
            _unpack_programs(tool, asset, data, staging)
        (staging / ".complete").write_text(f"{tool.version} {asset} sha256:{digest}\n", encoding="utf-8")
        if dest.exists():
            shutil.rmtree(dest)
        os.replace(staging, dest)  # appears complete or not at all
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    log.info("downloaded %s %s (%s, sha256 %s) to %s", tool.name, tool.version, asset, digest, dest)
    return dest


async def ensure(tool: Tool, root: Path, fetch: Callable[[str], bytes] = _fetch) -> bool:
    """Download the tool into ``root`` unless it is there. Returns True when it was downloaded now."""
    async with _lock:  # connectors starting at once download each tool once
        if tool.installed(root):
            return False
        await asyncio.to_thread(install, tool, root, fetch)
        return True


# ---------------------------------------------------------------- at install time (--install-tools)


def install_for_app(root: Path, path: str | None = None, fetch: Callable[[str], bytes] = _fetch) -> list[str]:
    """What the installer runs: get each tool the computer lacks (or has too old) into ``root``. Never raises:
    a tool that cannot be downloaded now is downloaded by the app the first time it is needed."""
    lines = []
    for tool in TOOLS:
        found = on_computer(tool, path if path is not None else os.environ.get("PATH"))
        if found:
            lines.append(f"{tool.name}: using the copy on this computer ({found}, {'.'.join(map(str, version_of(found) or ()))})")
        elif tool.installed(root):
            lines.append(f"{tool.name}: already installed with the app ({tool.version})")
        else:
            try:
                install(tool, root, fetch)
                lines.append(f"{tool.name}: installed {tool.version} into {tool.folder(root)}")
            except Exception as e:  # noqa: BLE001 - the install goes on; the app retries on first use
                lines.append(f"{tool.name}: not installed now ({e}); the app downloads it when first needed")
    for old in root.glob("*-*") if root.is_dir() else []:  # earlier pinned versions the app no longer uses
        ours = any(old.name.startswith(f"{t.key}-") for t in TOOLS)
        if ours and old.is_dir() and not any(old == t.folder(root) for t in TOOLS):
            shutil.rmtree(old, ignore_errors=True)
            lines.append(f"removed an older copy: {old.name}")
    return lines


def remove_for_app(root: Path) -> None:
    """What the uninstaller runs: delete the tools the installer downloaded (only folders this module makes)."""
    if not root.is_dir():
        return
    for child in root.iterdir():
        if child.is_dir() and any(child.name.startswith((f"{t.key}-", f".{t.key}-")) for t in TOOLS):
            shutil.rmtree(child, ignore_errors=True)
    (root / "install.log").unlink(missing_ok=True)
    try:
        root.rmdir()
    except OSError:
        pass  # something else is in there: leave it
