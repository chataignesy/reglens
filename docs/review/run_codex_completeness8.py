"""Fresh eight-question completeness evaluation; dry-run by default.

--live requires prior budget approval.

Personal project; not affiliated with an employer or supervisor; not legal/regulatory advice.
"""

import argparse
import json
import os
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from run_codex_claude_smoke import BudgetStop, WitnessLedger

from reglens.answer.route import gate_abstains, route_question
from reglens.config import PROJECT_ROOT, load_config
from reglens.eval import answers
from reglens.eval.answers import file_sha, load_run
from reglens.eval.fingerprint import AGENT_FILES
from reglens.eval.judge import judge
from reglens.eval.snapshots import load
from reglens.index.db import connect
from reglens.index.generations import current
from reglens.llm.codex import CodexCLIProvider
from reglens.llm.provider import LLMError

SNAPSHOT = "20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b"


def main(*, cohort_ids=None, label="codex-completeness8", allowance=3_000_000):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=int, default=allowance)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    cfg = load_config(PROJECT_ROOT / "config.codex.yaml")
    snapshot_path = PROJECT_ROOT / f"evals/frozen/{SNAPSHOT}.json"
    frozen, items = load(snapshot_path)
    if len(items) != 118 or any(i.status != "verified" for i in items):
        raise ValueError("Expected the unchanged verified118 snapshot")
    selected = set(cohort_ids) if cohort_ids else {
        "app-004", "dod-005", "val-001", "lom-001", "mh-012", "irb-007", "lgd-007", "app-001",
    }
    items = [i for i in items if i.id in selected]
    if len(items) != len(selected):
        raise ValueError("The selected frozen cohort contains missing questions")
    if args.budget > allowance:
        raise ValueError("This focused evaluation exceeds its planning/approval allowance")
    identity = {
        "snapshot_sha256": file_sha(snapshot_path),
        "config_sha256": file_sha(PROJECT_ROOT / "config.codex.yaml"),
        "source_hashes": {
            p: file_sha(PROJECT_ROOT / "src/reglens" / p) for p in sorted(set(AGENT_FILES))
        },
    }
    with connect() as conn:
        identity["corpus_generation"] = current(conn)
        chunk_count = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    plan = {
        "items": len(items),
        "ids": [i.id for i in items],
        "types": dict(Counter(i.type for i in items)),
        "estimate_tokens": {"planning_allowance": allowance},
        "budget": args.budget,
        "model": cfg.model("dev"),
        "billing": cfg.billing,
        "router": "fresh Codex decisions, after the normal free gate",
        "answers": "isolated cache; no pilot reuse; normal bounded fallback",
        "grading": "all items, unchanged frozen references, Codex bulk-tier judge",
        "chunk_count": chunk_count,
        **identity,
        "live": args.live,
    }
    print(json.dumps(plan, indent=2), flush=True)
    if not args.live:
        print("Dry run only; no model calls.", flush=True)
        return
    os.environ["REGLENS_INFERENCE_URL"] = "http://127.0.0.1:18001"
    from reglens.inference_client import ready

    inference = ready()
    if args.resume:
        directory = args.resume.resolve()
        root = (PROJECT_ROOT / "data/evals/comparisons").resolve()
        if not directory.is_relative_to(root):
            raise ValueError("Resume directory must belong to this project's benchmark records")
        report = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
        if report["identity"] != identity or report["budget"] != args.budget:
            raise ValueError(
                "Code, corpus, config, snapshot or budget changed; do not mix revisions"
            )
        if report.get("completed"):
            raise ValueError("This benchmark is already complete")
        previous_receipts = report["ledger_receipts"]
        report.setdefault("resumptions", []).append(datetime.now(UTC).isoformat())
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        directory = PROJECT_ROOT / "data/evals/comparisons" / f"{timestamp}-{label}"
        directory.mkdir(parents=True, exist_ok=False)
        previous_receipts = []
        report = {
            "started_utc": datetime.now(UTC).isoformat(),
            "completed": False,
            "identity": identity,
            "plan": plan,
            "budget": args.budget,
            "inference": inference,
            "calls": [],
            "routes": {},
        }
    ledger = WitnessLedger(cfg)
    state = {"phase": "routing"}

    def receipts():
        return previous_receipts + ledger.receipts

    def checkpoint():
        report["ledger_receipts"] = receipts()
        report["new_tokens"] = sum(r["total_tokens"] for r in receipts())
        (directory / "progress.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    class MeasuredCodex(CodexCLIProvider):
        def complete(self, prompt, **kwargs):
            spent = sum(r["total_tokens"] for r in receipts())
            previous = max((c.get("tokens") or 0 for c in report["calls"][-1:]), default=0)
            reserve = max((len(prompt) + len(kwargs.get("system") or "")) // 2 + 30_000,
                          int(previous * 1.3))
            if spent + reserve > args.budget:
                raise BudgetStop("Budget reserve reached before a new model request")
            call = {
                "phase": state["phase"],
                "purpose": kwargs["purpose"],
                "started_utc": datetime.now(UTC).isoformat(),
            }
            call["index"] = len(report["calls"]) + 1
            record_path = directory / f"call-{call['index']:03d}.json"
            request_record = {"prompt": prompt, "options": kwargs, "call": dict(call)}
            record_path.write_text(json.dumps(request_record, indent=2), encoding="utf-8")
            call["artifact"] = str(record_path.relative_to(PROJECT_ROOT))
            report["calls"].append(call)
            checkpoint()
            start = time.perf_counter()
            try:
                result = super().complete(prompt, **kwargs)
                call["tokens"] = result.usage.total_tokens
                request_record["response"] = {"text": result.text, "model": result.model,
                                               "tokens": result.usage.total_tokens}
                if not result.usage_known:
                    raise BudgetStop("Unknown response usage; stop")
                return result
            except LLMError as exc:
                call["error"] = str(exc)
                call["tokens"] = exc.tokens
                request_record["error"] = str(exc)
                if re.search(r"quota|usage.limit|subscription.limit|rate.limit", str(exc), re.I):
                    raise BudgetStop("Provider quota rejection; stop before further calls") from exc
                if not exc.usage_known:
                    raise BudgetStop("Unknown usage; stop before further model calls") from exc
                raise
            finally:
                call["seconds"] = time.perf_counter() - start
                request_record["call"] = dict(call)
                record_path.write_text(json.dumps(request_record, indent=2), encoding="utf-8")
                call["artifact_sha256"] = file_sha(record_path)
                checkpoint()

    provider = MeasuredCodex(cfg, ledger)
    old_answer_dir = answers.ANSWER_DIR
    # This cache belongs to this benchmark alone, but survives an explicit resume.
    answers.ANSWER_DIR = PROJECT_ROOT / "data/evals/answers" / directory.name
    try:
        with connect() as conn:
            for n, item in enumerate(items, 1):
                if item.id in report["routes"]:
                    continue
                if gate_abstains(conn, cfg, item.question):
                    route, reason, tokens = "single", "Normal deterministic scope/retrieval gate", 0
                else:
                    route, reason, tokens = route_question(provider, item.question)
                report["routes"][item.id] = {"route": route, "reason": reason, "tokens": tokens}
                checkpoint()
                print(f"Route [{n}/{len(items)}] {item.id}: {route} "
                      f"({tokens:,} tokens)", flush=True)
            state["phase"] = "answers"
            start = time.perf_counter()
            if "answers" not in report:
                report["answers"] = answers.run(
                    conn,
                    provider,
                    cfg,
                    items,
                    routes=report["routes"],
                    dataset=frozen,
                    label=label,
                    log=lambda s: print(s, flush=True),
                )
                report["answer_phase_seconds"] = time.perf_counter() - start
                checkpoint()
        manifest_path = PROJECT_ROOT / report["answers"]["file"]
        manifest = load_run(report["answers"]["run_id"])
        report["manifest_sha256"] = file_sha(manifest_path)
        state["phase"] = "grading"
        start = time.perf_counter()
        report["judge"] = judge(provider, cfg, manifest, items, log=lambda s: print(s, flush=True))
        report["grading_phase_seconds"] = time.perf_counter() - start
        report["completed"] = (
            report["judge"]["items"] == len(items) and not report["judge"]["problems"]
        )
    except BaseException as exc:
        report.setdefault("interruptions", []).append(
            {"utc": datetime.now(UTC).isoformat(), "type": type(exc).__name__, "message": str(exc)}
        )
        raise
    finally:
        answers.ANSWER_DIR = old_answer_dir
        report["last_finished_utc"] = datetime.now(UTC).isoformat()
        checkpoint()
        # Each attempt gets its own immutable result, while progress.json is resumable.
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        with (directory / f"result-{stamp}.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        print(f"Saved benchmark records: {directory}", flush=True)


if __name__ == "__main__":
    main()
