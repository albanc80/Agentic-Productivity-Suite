#!/usr/bin/env python3
"""Smoke-test a packaged build: start it headless and offline, check health, run a calculation.

    python desktop/smoke_test.py path/to/ProductivitySuite[.exe] [extra launcher args]

Uses a throwaway user folder so it never touches real settings. Exits non-zero on failure.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

CASING = {"casing_size_in": 9.625, "weight_ppf": 47, "grade": "P-110", "setting_depth_ft": 10000,
          "pore_pressure_ppg": 10.5, "fracture_gradient_ppg": 15.0, "mud_weight_ppg": 11.0}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def main() -> int:
    exe, extra = sys.argv[1], sys.argv[2:]
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    user_dir = tempfile.mkdtemp(prefix="suite-smoke-")
    env = {**os.environ, "SUITE_USER_DIR": user_dir}
    proc = subprocess.Popen([exe, "--headless", "--offline", "--port", str(port), *extra], env=env)
    try:
        deadline = time.time() + 120
        while True:
            try:
                health = call(base + "/api/health")
                break
            except OSError:
                if proc.poll() is not None or time.time() > deadline:
                    log = os.path.join(user_dir, "suite.log")
                    print(open(log).read() if os.path.exists(log) else "(no log)")
                    raise SystemExit(f"app did not start (exit code {proc.poll()})") from None
                time.sleep(1)
        assert health["status"] == "ok" and health["offline"] is True, health
        with urllib.request.urlopen(base + "/", timeout=10) as r:
            assert b"<!doctype html>" in r.read(200).lower(), "UI not served"
        ov = call(base + "/api/overview")
        assert len(ov["playbooks"]) >= 9 and len(ov["agents"]) == 34, (len(ov["playbooks"]), len(ov["agents"]))
        # A build made with the AGENT_PACK_KEY secret must open its built-in agent pack (ADR 0007).
        keyed = any(Path(exe).resolve().parent.rglob("agent-pack.key"))
        pack = ov.get("agent_pack", {})
        if keyed:
            assert pack.get("built_in") == 34, (pack, [w for w in ov["warnings"] if "agent" in w.lower()])
        print(f"Agent pack: {'built in, ' + str(pack.get('built_in')) + ' agents' if keyed else 'no key in this build'}")
        rid = call(base + "/api/runs", {"playbook_id": "well-plan-review", "inputs": {
            "well": "Smoke-1", "plan_summary": "smoke test", "casing_json": json.dumps(CASING)}})["id"]
        for _ in range(120):
            run = call(f"{base}/api/runs/{rid}")
            if run["status"] not in ("queued", "running"):
                break
            time.sleep(0.5)
        steps = {s["step_id"]: s for s in run["steps"]}
        casing = steps.get("casing_check", {})
        assert casing.get("status") == "COMPLETE", casing
        burst = json.loads(casing["output"]["data"])["burst"]["load_psi"]
        assert burst == round(0.052 * (11.0 - 8.6) * 10000), burst
        print(f"OK: {exe} served the UI, {len(ov['playbooks'])} playbooks, casing burst load {burst} psi, run {run['status']}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
