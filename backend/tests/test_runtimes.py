"""uv and Node.js for connectors: a new-enough copy on the computer wins, then the app's own copy (put there by
the installer or downloaded on first use). Downloads are pinned, checked and unpacked inside their folder."""

import hashlib
import io
import sys
import tarfile
from pathlib import Path

import pytest

from app import runtimes
from app.connectors import ConnectorConfig, ConnectorError, ConnectorManager

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake programs are shell scripts")


def program(folder: Path, name: str, version: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text(f"#!/bin/sh\necho '{version}'\n")
    p.chmod(0o755)
    return p


def app_copy(root: Path, tool: runtimes.Tool, *names: str) -> Path:
    """What an install of the tool looks like in a tools folder."""
    bindir = tool.bin_dir(root)
    for n in names:
        program(bindir, n, "app copy")
    (tool.folder(root) / ".complete").write_text("ok")
    return bindir


def npx_cfg(**kw) -> ConnectorConfig:
    return ConnectorConfig.model_validate({"id": "ms", "name": "Mail", "transport": "stdio", "command": "npx",
                                           "args": ["-y", "server"], **kw})


def test_the_computer_s_copy_wins_when_new_enough_and_the_app_s_copy_replaces_an_old_one(tmp_path):
    system, root = tmp_path / "system", tmp_path / "app-tools"
    program(system, "node", "v22.11.0")
    program(system, "npx", "10.9.0")
    mgr = ConnectorManager([npx_cfg()], env={"PATH": str(system)})
    mgr.tool_roots, mgr.download_root = [root], root
    command, _args, env = mgr.launch(mgr.configs["ms"])
    assert command == "npx" and env["PATH"] == str(system)  # nothing duplicated: the computer's copy is used
    assert mgr.missing_tool(mgr.configs["ms"]) is None

    program(system, "node", "v16.20.2")  # too old for the connectors (needs 20+)
    runtimes._versions.clear()
    assert mgr.missing_tool(mgr.configs["ms"]) is runtimes.NODE  # the app would download its own
    bindir = app_copy(root, runtimes.NODE, "node", "npx")
    command, _args, env = mgr.launch(mgr.configs["ms"])
    assert command == str(bindir / "npx") and env["PATH"].split(":")[0] == str(bindir)  # ahead of the old one
    assert mgr.missing_tool(mgr.configs["ms"]) is None

    program(system, "node", "v26.1.0")  # newer than the app's pinned copy: the computer's wins again
    runtimes._versions.clear()
    assert mgr.launch(mgr.configs["ms"])[0] == "npx"


def test_a_copy_whose_version_cannot_be_read_is_used(tmp_path):
    program(tmp_path / "s", "uv", "something unexpected")
    assert runtimes.on_computer(runtimes.UV, str(tmp_path / "s"))
    assert runtimes.on_computer(runtimes.UV, str(tmp_path / "empty")) is None


def archive(files: dict[str, bytes], links: dict[str, str] | None = None, mode: str = "w:gz") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as t:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(body), 0o755
            t.addfile(info, io.BytesIO(body))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            t.addfile(info)
    return buf.getvalue()


def fake_tool(data: bytes, whole: bool, asset: str) -> runtimes.Tool:
    return runtimes.Tool(name="Fake", key="fake", version="1.0", url="https://example.invalid/{version}/{asset}",
                         builds={runtimes.platform_key(): (asset, hashlib.sha256(data).hexdigest())},
                         commands=frozenset({"fake"}), program="fake", min_version=(1,), whole=whole,
                         programs={"posix": ("fake", "fakex")}, posix_bin="bin" if whole else "")


def test_downloads_are_checked_and_unpacked_inside_their_folder(tmp_path):
    data = archive({"pkg-1.0/fake": b"a", "pkg-1.0/fakex": b"b", "pkg-1.0/README": b"c"})
    tool = fake_tool(data, whole=False, asset="fake.tar.gz")
    with pytest.raises(runtimes.ToolError, match="did not match its published checksum"):
        runtimes.install(tool, tmp_path, fetch=lambda url: data + b"tampered")
    assert not tool.installed(tmp_path) and not list(tmp_path.glob("*"))  # nothing left behind
    runtimes.install(tool, tmp_path, fetch=lambda url: data)
    assert sorted(p.name for p in tool.folder(tmp_path).iterdir()) == [".complete", "fake", "fakex"]  # programs only
    assert (tool.folder(tmp_path) / "fake").stat().st_mode & 0o111
    assert tool.folder(tmp_path).stat().st_mode & 0o055 == 0o055  # other users can run what the installer put there

    node_like = archive({"node-v1/bin/node": b"n", "node-v1/lib/npm/npx-cli.js": b"x"},
                        links={"node-v1/bin/npx": "../lib/npm/npx-cli.js"}, mode="w:xz")
    whole = fake_tool(node_like, whole=True, asset="fake.tar.xz")
    runtimes.install(whole, tmp_path / "w", fetch=lambda url: node_like)
    npx = whole.bin_dir(tmp_path / "w") / "npx"
    assert npx.is_symlink() and npx.read_bytes() == b"x"  # npm's own links still work

    for bad in ({"node-v1/../../evil": b"!"}, {"node-v1/bin/node": b"n"}):
        links = None if "node-v1/../../evil" in bad else {"node-v1/bin/npx": "/etc/passwd"}
        evil = archive(bad, links=links, mode="w:xz")
        with pytest.raises(runtimes.ToolError, match="outside its folder"):
            runtimes.install(fake_tool(evil, whole=True, asset="fake.tar.xz"), tmp_path / "evil", fetch=lambda url, body=evil: body)
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path.parent / "evil").exists()


def test_the_install_step_never_fails_and_skips_what_the_computer_has(tmp_path):
    system, root = tmp_path / "system", tmp_path / "app" / "tools"
    program(system, "node", "v22.0.0")
    program(system, "uv", "uv 0.11.0 (x)")
    calls = []
    lines = runtimes.install_for_app(root, path=str(system), fetch=lambda url: calls.append(url) or b"")
    assert calls == [] and all("using the copy on this computer" in line for line in lines)  # nothing downloaded

    def offline(url):
        raise OSError("no network")
    lines = runtimes.install_for_app(root, path=str(tmp_path / "empty"), fetch=offline)
    assert len(lines) == 2 and all("downloads it when first needed" in line for line in lines)  # and no exception

    app_copy(root, runtimes.UV, "uv", "uvx")
    (root / "uv-0.0.1").mkdir()  # an older pinned version from an earlier release
    lines = runtimes.install_for_app(root, path=str(tmp_path / "empty"), fetch=offline)
    assert any("uv: already installed with the app" in line for line in lines) and not (root / "uv-0.0.1").exists()
    (root / "install.log").write_text("log")
    runtimes.remove_for_app(root)
    assert not root.exists()  # the uninstaller leaves nothing behind


async def test_a_connector_downloads_its_runtime_once_when_nothing_has_it(tmp_path, monkeypatch):
    root = tmp_path / "tools"
    got = []

    async def fake_ensure(tool, where, fetch=None):
        got.append((tool.key, where))
        app_copy(where, tool, "node", "npx")
        return True
    monkeypatch.setattr(runtimes, "ensure", fake_ensure)
    mgr = ConnectorManager([npx_cfg()], env={"PATH": str(tmp_path / "empty")})
    mgr.tool_roots, mgr.download_root = [tmp_path / "installer", root], root
    seen = []
    mgr.on_tool_download = lambda name, version: seen.append(name)
    await mgr.prepare(mgr.configs["ms"])
    assert got == [("node", root)] and seen == ["Node.js"]
    assert mgr.launch(mgr.configs["ms"])[0] == str(runtimes.NODE.bin_dir(root) / "npx")
    await mgr.prepare(mgr.configs["ms"])
    assert len(got) == 1  # once

    async def failing(tool, where, fetch=None):
        raise runtimes.ToolError("Could not download Node.js")
    monkeypatch.setattr(runtimes, "ensure", failing)
    other = ConnectorManager([npx_cfg()], env={"PATH": str(tmp_path / "empty")})
    other.tool_roots, other.download_root = [tmp_path / "none"], tmp_path / "none"
    with pytest.raises(ConnectorError, match="Could not download Node.js"):
        await other.prepare(other.configs["ms"])
