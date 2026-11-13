"""Reproduce the targeted post-rerun check; --live opts into subscription calls.

Uses the unchanged frozen references. Replays the prior route plans, not prior answers.
"""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime

from reglens.config import PROJECT_ROOT, load_config
from reglens.eval.answers import load_run, run
from reglens.eval.judge import judge
from reglens.eval.snapshots import load
from reglens.index.db import connect
from reglens.llm.provider import get_provider

SNAPSHOT = "20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--config", default=None,
                        help="e.g. config.codex.yaml for subscription Codex")
    args = parser.parse_args()
    print("Estimate: 650,000–900,000 new tokens including helper usage and grading.", flush=True)
    if not args.live:
        print("Dry run; no model calls.")
        return
    os.environ["REGLENS_INFERENCE_URL"] = "http://127.0.0.1:18001"
    from reglens.inference_client import ready

    identity = ready()
    config = load_config(args.config)
    frozen, all_items = load(PROJECT_ROOT / f"evals/frozen/{SNAPSHOT}.json")
    items = [i for i in all_items if i.id in {"mh-013", "mh-014", "oos-006"}]
    routes = {
        i.id: {"route": "single" if i.type == "out_of_scope" else "agent",
               "reason": "Replay prior run's planned route; no router call", "tokens": 0}
        for i in items
    }
    start = datetime.now(UTC).isoformat()
    ledger_start = len(config.ledger_path.read_text(encoding="utf-8").splitlines())
    with connect() as conn:
        summary = run(conn, get_provider(config), config, items, routes=routes,
                      dataset=frozen, label=f"{config.provider}-followup-3",
                      log=lambda s: print(s, flush=True))
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    manifest = load_run(summary["run_id"])
    manifest_path = PROJECT_ROOT / summary["file"]
    report = {
        "started_utc": start, "snapshot": SNAPSHOT, "model_identity": identity,
        "provider": config.provider, "billing": config.billing,
        "config": args.config or "config.yaml",
        "answer_model": config.model("dev"), "judge_model": config.model("bulk"),
        "route_basis": "fixed replay of prior route plans; router not re-evaluated",
        "summary": summary,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    if summary["new_tokens_this_run"] < 900_000:
        report["judge"] = judge(get_provider(config), config, manifest, items,
                                log=lambda s: print(s, flush=True))
    else:
        report["judge_skipped"] = "Usage exceeded planning allowance; no additional calls started"
    new_ledger = [json.loads(line) for line in
                  config.ledger_path.read_text(encoding="utf-8").splitlines()[ledger_start:]]
    report["ledger_receipts"] = new_ledger
    report["completed_utc"] = datetime.now(UTC).isoformat()
    path = PROJECT_ROOT / "docs/review" / f"frozen118-followup-{summary['run_id']}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    print(f"Saved {path}", flush=True)


if __name__ == "__main__":
    main()
