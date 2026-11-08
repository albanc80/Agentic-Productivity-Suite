"""Build step: put the agent pack key into the installers, from the AGENT_PACK_KEY secret (ADR 0007).

registry/agent-pack.enc (committed, encrypted) is bundled with registry/. This writes the key to
config/agent-pack.key, which git ignores and the PyInstaller spec bundles with config/, so the app can open the
pack in memory. The key is checked against the pack first: a key that does not open it fails the build, so a
release never ships agents that silently fall back to their public descriptions. The key is never printed.
Run from backend/ with `uv run python ../desktop/bundle_agent_key.py`.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.registry import _yaml_from_zip, decrypt_pack, parse_pack_key  # noqa: E402

PACK = ROOT / "registry" / "agent-pack.enc"
TARGET = ROOT / "config" / "agent-pack.key"


def main() -> int:
    raw = os.environ.get("AGENT_PACK_KEY", "").strip()
    if not raw:
        print("No AGENT_PACK_KEY secret: the installers' agents run on their public descriptions until a pack is imported.")
        return 0
    if not PACK.is_file():
        print(f"AGENT_PACK_KEY is set but registry/{PACK.name} is missing.", file=sys.stderr)
        return 1
    try:
        files = _yaml_from_zip(decrypt_pack(PACK.read_bytes(), parse_pack_key(raw)))
    except ValueError as e:
        print(f"AGENT_PACK_KEY does not open registry/{PACK.name}: {e}.", file=sys.stderr)
        return 1
    TARGET.write_text(raw + "\n", encoding="utf-8")
    print(f"Agent pack key written: the installers open {len(files)} agent files built in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
