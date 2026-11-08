#!/usr/bin/env python3
"""Owner tool for the agent pack built into the installers (ADR 0007). Run from backend/:

    uv run python ../scripts/agent_pack.py genkey --key-file ~/agent-pack.key
    uv run python ../scripts/agent_pack.py encrypt ~/agent-pack.zip --key-file ~/agent-pack.key
    uv run python ../scripts/agent_pack.py check --key-file ~/agent-pack.key
    uv run python ../scripts/agent_pack.py decrypt --key-file ~/agent-pack.key -o ~/agent-pack.zip

`encrypt` writes registry/agent-pack.enc (commit it). The key goes in the AGENT_PACK_KEY repository secret
and in a safe place of your own; never commit it. The key may also come from the AGENT_PACK_KEY variable.
Nothing here prints the key or the instructions.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.registry import Registry, _yaml_from_zip, decrypt_pack, encrypt_pack, parse_pack_key  # noqa: E402

ENC = ROOT / "registry" / "agent-pack.enc"


def key_from(args) -> bytes:
    raw = Path(args.key_file).expanduser().read_text(encoding="utf-8") if args.key_file else os.environ.get("AGENT_PACK_KEY", "")
    if not raw.strip():
        raise SystemExit("Give --key-file or set AGENT_PACK_KEY.")
    return parse_pack_key(raw)


def count(zip_bytes: bytes) -> tuple[int, int]:
    import tempfile
    reg = Registry(ROOT / "registry", ROOT / "config" / "policies", Path(tempfile.mkdtemp()) / "none")
    files = _yaml_from_zip(zip_bytes)
    for name, data in files.items():
        reg._apply(name, data, "built-in")
    bad = [w for w in reg.warnings if "could not be read" in w or "matches no agent" in w]
    if bad:
        raise SystemExit("The pack has problems:\n- " + "\n- ".join(bad))
    return sum(1 for a in reg.agents.values() if a.has_private), len(reg.agents)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("genkey").add_argument("--key-file", required=True)
    enc = sub.add_parser("encrypt")
    enc.add_argument("zip")
    enc.add_argument("--key-file")
    sub.add_parser("check").add_argument("--key-file")
    dec = sub.add_parser("decrypt")
    dec.add_argument("--key-file")
    dec.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    if args.cmd == "genkey":
        target = Path(args.key_file).expanduser()
        if target.exists():
            raise SystemExit(f"{target} exists; not overwriting a key.")
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(base64.urlsafe_b64encode(os.urandom(32)).decode() + "\n")
        print(f"New key written to {target} (readable by you only). Keep a backup: without it the pack cannot be opened.")
        return 0
    key = key_from(args)
    if args.cmd == "encrypt":
        data = Path(args.zip).expanduser().read_bytes()
        n, total = count(data)
        ENC.write_bytes(encrypt_pack(data, key))
        print(f"Wrote {ENC.relative_to(ROOT)}: {n} of {total} agents have instructions. Commit it; never commit the key.")
        return 0
    plain = decrypt_pack(ENC.read_bytes(), key)
    if args.cmd == "check":
        n, total = count(plain)
        print(f"OK: the key opens {ENC.relative_to(ROOT)}; {n} of {total} agents have instructions.")
        return 0
    out = Path(args.out).expanduser()
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(plain)
    print(f"Decrypted pack written to {out} (readable by you only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
