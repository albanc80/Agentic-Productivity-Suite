#!/usr/bin/env python3
"""Run the benchmark cases in evals/cases.yaml against the configured providers.

Every run spends real tokens on whichever providers your config enables.
Gates are approved automatically as "eval-runner" so the playbook completes.

    cd backend && uv run python ../scripts/run_evals.py
    cd backend && uv run python ../scripts/run_evals.py --case scope-change-sized --data-class restricted

Writes evals/reports/<timestamp>.md with deterministic check results and a
blank "Human grade" column for you to fill in.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("SUITE_NO_AUTOAPP", "1")

from app.guards import scan_people_eval  # noqa: E402
from app.main import Suite  # noqa: E402
from app.settings import load_settings  # noqa: E402


def check(case: dict, run: dict, steps: list[dict]) -> list[tuple[str, bool]]:
    md = (run.get("deliverable") or "").lower()
    exp = case.get("expect", {})
    results = [("run completed", run["status"] == "completed"),
               ("not demo output", not run["demo"]),
               ("no people-evaluation language", not scan_people_eval(run.get("deliverable") or "")),
               ("every agent step returned a contract",
                all("contract repair failed" not in " ".join(s["warnings"]) for s in steps if s["kind"] in ("agent", "review")))]
    for group in exp.get("contains_any", []):
        results.append((f"mentions one of {group}", any(w.lower() in md for w in group)))
    for w in exp.get("contains_all", []):
        results.append((f"mentions '{w}'", w.lower() in md))
    if exp.get("review_has_verdict"):
        results.append(("review returned a verdict", any(s["kind"] == "review" and (s["output"] or {}).get("handoff", {}).get("verdict")
                                                         for s in steps)))
    return results


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--data-class")
    args = ap.parse_args()
    cases = yaml.safe_load((ROOT / "evals" / "cases.yaml").read_text())["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
    settings = load_settings()
    settings.data_dir = ROOT / "evals" / "data"
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    suite = Suite(settings)
    eng = suite.engine
    rows = []
    for case in cases:
        rid = await eng.start(case["playbook"], case["inputs"], args.data_class)
        for _ in range(20):
            await eng.wait(rid)
            run = suite.store.run(rid)
            if run["status"] == "awaiting_approval":
                for a in suite.store.approvals(status="pending", run_id=rid):
                    await eng.decide(a["id"], "approved", "eval-runner", "automatic approval for evaluation")
                continue
            if run["status"] not in ("queued", "running"):
                break
        run = suite.store.run(rid)
        steps = suite.store.steps(rid)
        res = check(case, run, steps)
        passed = sum(ok for _, ok in res)
        models = sorted({s["model"] for s in steps if s.get("model")})
        rows.append((case, run, res, passed, models))
        print(f"{case['id']}: {passed}/{len(res)} checks · {run['outcome']} · {run['tokens']} tokens · ${run['cost_usd']:.4f}")
    await suite.connectors.shutdown()

    out = ROOT / "evals" / "reports"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now():%Y%m%d-%H%M%S}.md"
    lines = ["# Eval report", "", f"Generated {datetime.now():%Y-%m-%d %H:%M}.", "",
             "| Case | Outcome | Checks | Models | Tokens | Cost | Human grade |", "|---|---|---|---|---|---|---|"]
    for case, run, res, passed, models in rows:
        lines.append(f"| {case['id']} | {run['outcome']} | {passed}/{len(res)} | {', '.join(models)} | {run['tokens']} | ${run['cost_usd']:.4f} | |")
    for case, run, res, _, _ in rows:
        lines += ["", f"## {case['id']}", ""] + [f"- {'PASS' if ok else 'FAIL'}: {name}" for name, ok in res]
        lines += ["", "<details><summary>Deliverable</summary>", "", run.get("deliverable") or "", "", "</details>"]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {path}")
    return 0 if all(p == len(r) for _, _, r, p, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
