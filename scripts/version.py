"""The app version, which lives in five files. Every pull request raises it; a merge to main then releases it.

    python scripts/version.py                      # print the version (and check the five files agree)
    python scripts/version.py set 0.8.0            # write it everywhere
    python scripts/version.py check --newer-than 0.7.0   # CI: agree, and higher than the base branch

Exit code 1 when the files disagree or the version is not higher, with a message saying what to do.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

# file -> (pattern whose group 1 is the version, how to find it)
PATTERNS = {
    "backend/app/__init__.py": re.compile(r'^(__version__ = ")([^"]+)(")', re.M),
    "backend/pyproject.toml": re.compile(r'^(\[project\]\nname = "productivity-suite"\nversion = ")([^"]+)(")', re.M),
    "backend/uv.lock": re.compile(r'^(\[\[package\]\]\nname = "productivity-suite"\nversion = ")([^"]+)(")', re.M),
}
PACKAGE_JSON = "frontend/package.json"
PACKAGE_LOCK = "frontend/package-lock.json"


def read_all() -> dict[str, str]:
    found: dict[str, str] = {}
    for rel, pattern in PATTERNS.items():
        m = pattern.search((ROOT / rel).read_text(encoding="utf-8"))
        found[rel] = m.group(2) if m else "<not found>"
    found[PACKAGE_JSON] = json.loads((ROOT / PACKAGE_JSON).read_text(encoding="utf-8")).get("version", "<not found>")
    lock = json.loads((ROOT / PACKAGE_LOCK).read_text(encoding="utf-8"))
    found[PACKAGE_LOCK] = lock.get("version", "<not found>")
    found[PACKAGE_LOCK + " (packages[''])"] = lock.get("packages", {}).get("", {}).get("version", "<not found>")
    return found


def write_all(version: str) -> None:
    for rel, pattern in PATTERNS.items():
        path = ROOT / rel
        text, n = pattern.subn(lambda m: m.group(1) + version + m.group(3), path.read_text(encoding="utf-8"), count=1)
        if n != 1:
            sys.exit(f"could not find the version in {rel}")
        path.write_text(text, encoding="utf-8")
    for rel in (PACKAGE_JSON, PACKAGE_LOCK):
        path = ROOT / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        if rel == PACKAGE_LOCK:
            data["packages"][""]["version"] = version
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")  # npm's format


def as_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "set":
        if not SEMVER.match(argv[1]):
            sys.exit(f"'{argv[1]}' is not a version like 0.8.0")
        write_all(argv[1])
        argv = []
    found = read_all()
    versions = set(found.values())
    if len(versions) != 1:
        print("The version files disagree. Run: python scripts/version.py set <version>", file=sys.stderr)
        for rel, v in found.items():
            print(f"  {rel}: {v}", file=sys.stderr)
        return 1
    version = versions.pop()
    if len(argv) == 3 and argv[0] == "check" and argv[1] == "--newer-than":
        base = argv[2]
        if not SEMVER.match(version) or as_tuple(version) <= as_tuple(base):
            print(f"Version {version} is not higher than {base} on the base branch. Every pull request raises it "
                  f"(patch for fixes, minor for features): python scripts/version.py set <version>", file=sys.stderr)
            return 1
        print(f"Version {version} (base {base}): ok")
        return 0
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
