"""Five-case completeness follow-up. Dry-run by default; no frozen-reference edits.

Personal project, not affiliated with an employer or supervisor; not legal/regulatory advice.
"""

import argparse
import json
import os
import time
from datetime import UTC, datetime

from run_codex_claude_smoke import BudgetStop, WitnessLedger

from reglens.config import PROJECT_ROOT, load_config
from reglens.eval.answers import file_sha, load_run, run
from reglens.eval.fingerprint import AGENT_FILES
from reglens.eval.judge import judge
from reglens.eval.snapshots import load
from reglens.index.db import connect
from reglens.llm.codex import CodexCLIProvider
from reglens.llm.provider import LLMError

SNAPSHOT = "20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b"
IDS = {"pd-003", "cmp-001", "app-001", "mh-015", "oos-006"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--ids", nargs="+", choices=sorted(IDS), default=sorted(IDS))
    args = parser.parse_args()
    estimate = 120_000 if len(args.ids) == 1 else 720_000
    print(
        f"{len(args.ids)} case(s); estimate {estimate:,} tokens; "
        "stop before requests exceeding 900,000 reserve.",
        flush=True,
    )
    if not args.live:
        return
    os.environ["REGLENS_INFERENCE_URL"] = "http://127.0.0.1:18001"
    from reglens.inference_client import ready

    cfg = load_config(PROJECT_ROOT / "config.codex.yaml")
    ledger = WitnessLedger(cfg)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    directory = PROJECT_ROOT / "data/evals/comparisons" / f"{timestamp}-completeness5"
    directory.mkdir(parents=True, exist_ok=False)
    report = {
        "started_utc": datetime.now(UTC).isoformat(),
        "completed": False,
        "snapshot": SNAPSHOT,
        "ids": args.ids,
        "budget": 900_000,
        "estimate": estimate,
        "inference": ready(),
        "calls": [],
        "source_hashes": {
            p: file_sha(PROJECT_ROOT / "src/reglens" / p) for p in sorted(set(AGENT_FILES))
        },
        "config_sha256": file_sha(PROJECT_ROOT / "config.codex.yaml"),
    }

    def checkpoint():
        report["ledger_receipts"] = ledger.receipts
        report["new_tokens"] = sum(r["total_tokens"] for r in ledger.receipts)
        (directory / "progress.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    class MeasuredCodex(CodexCLIProvider):
        def complete(self, prompt, **kwargs):
            spent = sum(r["total_tokens"] for r in ledger.receipts)
            if spent + len(prompt) // 3 + 20_000 > report["budget"]:
                raise BudgetStop("Budget reserve reached; no new request started")
            start = time.perf_counter()
            call = {"purpose": kwargs["purpose"], "started_utc": datetime.now(UTC).isoformat()}
            report["calls"].append(call)
            checkpoint()
            try:
                result = super().complete(prompt, **kwargs)
                call["tokens"] = result.usage.total_tokens
                return result
            except LLMError as exc:
                call["error"] = str(exc)
                if not exc.usage_known:
                    raise BudgetStop("Unknown usage; stop before further model calls") from exc
                raise
            finally:
                call["seconds"] = time.perf_counter() - start
                checkpoint()

    provider = MeasuredCodex(cfg, ledger)
    frozen, all_items = load(PROJECT_ROOT / f"evals/frozen/{SNAPSHOT}.json")
    items = [i for i in all_items if i.id in set(args.ids)]
    routes = {
        i.id: {
            "route": "single",
            "tokens": 0,
            "reason": "Fixed single-pass plan; normal required-gap fallback enabled",
        }
        for i in items
    }
    try:
        start = time.perf_counter()
        with connect() as conn:
            report["answers"] = run(
                conn,
                provider,
                cfg,
                items,
                routes=routes,
                dataset=frozen,
                label="codex-completeness5",
                log=lambda s: print(s, flush=True),
            )
        report["answer_seconds"] = time.perf_counter() - start
        checkpoint()
        manifest = load_run(report["answers"]["run_id"])
        report["manifest_sha256"] = file_sha(PROJECT_ROOT / report["answers"]["file"])
        report["judge"] = judge(provider, cfg, manifest, items, log=lambda s: print(s, flush=True))
        report["completed"] = True
    except BudgetStop as exc:
        report["stopped"] = str(exc)
    finally:
        report["completed_utc"] = datetime.now(UTC).isoformat()
        checkpoint()
        with (directory / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        print(f"Saved {directory / 'result.json'}", flush=True)


if __name__ == "__main__":
    main()
