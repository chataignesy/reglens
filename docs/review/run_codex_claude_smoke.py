"""Fixed-cohort Codex smoke test and common-judge comparison with saved Claude answers.

Dry-run by default. --live requires explicit budget approval outside this script.
No Claude generation calls; old answers and grades are immutable comparison inputs.
"""

import argparse
import copy
import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from functools import wraps

from reglens.config import PROJECT_ROOT, load_config
from reglens.eval.answers import file_sha, load_run, run
from reglens.eval.judge import judge
from reglens.eval.snapshots import load
from reglens.index.db import connect
from reglens.llm.codex import CodexCLIProvider
from reglens.llm.ledger import Ledger
from reglens.llm.provider import LLMError

COHORT = PROJECT_ROOT / "evals/cohorts/codex-claude-smoke30-2026-11-13.json"


def inputs():
    plan = json.loads(COHORT.read_text(encoding="utf-8"))
    frozen, all_items = load(PROJECT_ROOT / f"evals/frozen/{plan['snapshot_sha256']}.json")
    by_id = {i.id: i for i in all_items}
    items = [by_id[i] for i in plan["ids"]]
    if len(items) != 30 or len({i.id for i in items}) != 30:
        raise ValueError("The fixed cohort must contain 30 unique questions")
    old_path = PROJECT_ROOT / plan["claude_manifest"]
    if file_sha(old_path) != plan["claude_manifest_sha256"]:
        raise ValueError("Historical Claude manifest changed")
    old = json.loads(old_path.read_text(encoding="utf-8"))
    if old["dataset"]["snapshot"] != frozen:
        raise ValueError("Comparison uses different frozen questions or references")
    entries = {e["id"]: e for e in old["items"]}
    for item in items:
        entry = entries[item.id]
        if file_sha(PROJECT_ROOT / entry["artifact"]) != entry["artifact_sha256"]:
            raise ValueError(f"Historical Claude answer changed: {item.id}")
    return plan, frozen, items, old


class BudgetStop(RuntimeError):
    pass


class WitnessLedger(Ledger):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.receipts = []

    def record(self, *args, **kwargs):
        receipt = super().record(*args, **kwargs)
        self.receipts.append(receipt)
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget", type=int, default=4_000_000)
    args = parser.parse_args()
    plan, frozen, items, old = inputs()
    print(
        json.dumps(
            {
                "cohort": str(COHORT),
                "items": len(items),
                "types": dict(Counter(i.type for i in items)),
                "estimate": plan["estimate"],
                "live": args.live,
            }
        ),
        flush=True,
    )
    if not args.live:
        return
    cfg = load_config(PROJECT_ROOT / "config.codex.yaml")
    os.environ["REGLENS_INFERENCE_URL"] = "http://127.0.0.1:18001"
    from reglens.inference_client import ready

    identity = ready()
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    directory = PROJECT_ROOT / "data/evals/comparisons" / f"{timestamp}-smoke30"
    directory.mkdir(parents=True, exist_ok=False)
    report = {
        "started_utc": datetime.now(UTC).isoformat(),
        "cohort_sha256": file_sha(COHORT),
        "plan": plan,
        "config_sha256": file_sha(PROJECT_ROOT / "config.codex.yaml"),
        "model_identity": identity,
        "answer_model": cfg.model("dev"),
        "judge_model": cfg.model("bulk"),
        "approved_budget": args.budget,
        "completed": False,
        "timings": [],
        "calls": [],
    }
    ledger = WitnessLedger(cfg)
    state = {"phase": "answers", "id": None}

    def checkpoint():
        report["ledger_receipts"] = ledger.receipts
        report["new_tokens"] = sum(r["total_tokens"] for r in ledger.receipts)
        (directory / "progress.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    class MeasuredCodex(CodexCLIProvider):
        def complete(self, prompt, **kwargs):
            spent = sum(r["total_tokens"] for r in ledger.receipts)
            # Conservative preflight only; a response can exceed the reserved output amount.
            expected = len(prompt) // 3 + 12_000 + 8_000
            if spent + expected > args.budget:
                raise BudgetStop("Comparison budget reserve reached before a new model request")
            call = {
                "phase": state["phase"],
                "id": state["id"],
                "purpose": kwargs["purpose"],
                "started_utc": datetime.now(UTC).isoformat(),
            }
            report["calls"].append(call)
            checkpoint()
            start = time.perf_counter()
            try:
                result = super().complete(prompt, **kwargs)
                call["tokens"] = result.usage.total_tokens
                return result
            except LLMError as exc:
                call["error"] = str(exc)
                if not exc.usage_known:
                    raise BudgetStop(
                        "Unknown call usage; stop before spending further budget"
                    ) from exc
                raise
            finally:
                call["seconds"] = time.perf_counter() - start
                checkpoint()

    provider = MeasuredCodex(cfg, ledger)
    from reglens.eval.fingerprint import AGENT_FILES, SINGLE_FILES

    report["source_hashes"] = {
        p: file_sha(PROJECT_ROOT / "src/reglens" / p)
        for p in sorted(set(SINGLE_FILES + AGENT_FILES))
    }
    by_question = {i.question: i.id for i in items}

    def measured(function, mode):
        @wraps(function)
        def wrapped(conn, provider, config, question, **kwargs):
            state["id"] = by_question[question]
            start = time.perf_counter()
            try:
                return function(conn, provider, config, question, **kwargs)
            finally:
                report["timings"].append(
                    {"id": state["id"], "mode": mode, "seconds": time.perf_counter() - start}
                )
                checkpoint()

        return wrapped

    import reglens.agent.run as agent
    import reglens.eval.answers as answers

    original_single, original_agent = answers.answer_question, agent.answer_agentic
    answers.answer_question = measured(original_single, "single")
    agent.answer_agentic = measured(original_agent, "agent")
    entries = {e["id"]: e for e in old["items"]}
    routes = {
        i.id: {
            "route": entries[i.id]["planned"],
            "tokens": 0,
            "reason": "Fixed historical plan replay; router excluded from comparison",
        }
        for i in items
    }
    try:
        started = time.perf_counter()
        with connect() as conn:
            report["codex"] = run(
                conn,
                provider,
                cfg,
                items,
                dataset=frozen,
                routes=routes,
                label="codex-smoke30",
                log=lambda s: print(s, flush=True),
            )
        report["answer_phase_seconds"] = time.perf_counter() - started
        codex_manifest = load_run(report["codex"]["run_id"])
        report["codex_manifest_sha256"] = file_sha(PROJECT_ROOT / report["codex"]["file"])
        saved = copy.deepcopy(old)
        saved["run_id"] = f"{timestamp}-saved-claude-smoke30"
        saved["kind"] = "historical-saved-claude-comparison"
        saved["created"] = datetime.now(UTC).isoformat()
        saved["source_run"] = old["run_id"]
        saved["source_manifest_sha256"] = plan["claude_manifest_sha256"]
        saved["cohort_sha256"] = report["cohort_sha256"]
        saved["items"] = [entries[i.id] for i in items]
        saved["summary"] = {"items": len(items), "new_answer_tokens": 0}
        saved_path = answers.RUNS_DIR / f"{saved['run_id']}.json"
        with saved_path.open("x", encoding="utf-8") as stream:
            json.dump(saved, stream, indent=2, ensure_ascii=False)
        report["claude_saved_manifest"] = str(saved_path.relative_to(PROJECT_ROOT))
        report["claude_saved_manifest_sha256"] = file_sha(saved_path)
        state.update(phase="grade_codex", id=None)
        print("Common judge: Codex answers", flush=True)
        report["codex_judge"] = judge(
            provider, cfg, codex_manifest, items, log=lambda s: print(s, flush=True)
        )
        report["codex_judge_sha256"] = file_sha(PROJECT_ROOT / report["codex_judge"]["file"])
        checkpoint()
        state.update(phase="grade_saved_claude", id=None)
        print("Common judge: historical Claude answers", flush=True)
        report["claude_common_judge"] = judge(
            provider, cfg, saved, items, log=lambda s: print(s, flush=True)
        )
        report["claude_common_judge_sha256"] = file_sha(
            PROJECT_ROOT / report["claude_common_judge"]["file"]
        )
        report["completed"] = all(
            report[key]["items"] == len(items) and not report[key]["problems"]
            for key in ("codex_judge", "claude_common_judge")
        )
    except BaseException as exc:
        report["interruption"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        answers.answer_question, agent.answer_agentic = original_single, original_agent
        report["completed_utc"] = datetime.now(UTC).isoformat()
        checkpoint()
        with (directory / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False)
        print(f"Saved comparison: {directory / 'result.json'}", flush=True)


if __name__ == "__main__":
    main()
