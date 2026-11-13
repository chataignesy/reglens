"""Resume grading only; preserve interrupted attempts, saved answers and original reports."""

import argparse
import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from run_codex_claude_smoke import BudgetStop, WitnessLedger

from reglens.config import PROJECT_ROOT, load_config
from reglens.eval.answers import RUNS_DIR, file_sha
from reglens.eval.judge import judge, plan
from reglens.eval.snapshots import load
from reglens.llm.codex import CodexCLIProvider
from reglens.llm.provider import LLMError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    original = json.loads(args.source.read_text(encoding="utf-8"))
    cfg = load_config(PROJECT_ROOT / "config.codex.yaml")
    if file_sha(PROJECT_ROOT / "config.codex.yaml") != original["config_sha256"]:
        raise ValueError("Provider/model configuration changed since generation")
    frozen, all_items = load(
        PROJECT_ROOT / f"evals/frozen/{original['plan']['snapshot_sha256']}.json"
    )
    by_id = {i.id: i for i in all_items}
    items = [by_id[id] for id in original["plan"]["ids"]]
    manifests = {}
    for label, path, expected in [
        ("codex", original["codex"]["file"], original["codex_manifest_sha256"]),
        ("claude", original["claude_saved_manifest"], original["claude_saved_manifest_sha256"]),
    ]:
        path = PROJECT_ROOT / path
        if file_sha(path) != expected:
            raise ValueError("Source manifest changed")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest["dataset"]["snapshot"] != frozen:
            raise ValueError("Frozen references changed")
        for e in manifest["items"]:
            if file_sha(PROJECT_ROOT / e["artifact"]) != e["artifact_sha256"]:
                raise ValueError("Saved answer changed")
        manifests[label] = manifest
        print(label, plan(manifest, items, cfg.model("bulk")), flush=True)
    print(
        "Known prior tokens:",
        original["new_tokens"],
        "planning cap:",
        original["approved_budget"],
        flush=True,
    )
    if not args.live:
        return
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    directory = PROJECT_ROOT / "data/evals/comparisons" / f"{stamp}-smoke30-grade-resume"
    directory.mkdir(parents=True, exist_ok=False)
    result = copy.deepcopy(original)
    result["resumed_from"] = {"path": str(args.source.resolve()), "sha256": file_sha(args.source)}
    result["original_interruption"] = result.pop("interruption", None)
    result["grading_resumed_utc"] = datetime.now(UTC).isoformat()
    result["grading_manifests"] = {}
    prior_receipts = copy.deepcopy(original["ledger_receipts"])
    prior_calls = copy.deepcopy(original["calls"])
    ledger = WitnessLedger(cfg)
    phase = {"value": ""}

    def save_progress():
        result["ledger_receipts"] = prior_receipts + ledger.receipts
        result["new_tokens"] = sum(r["total_tokens"] for r in result["ledger_receipts"])
        result["unknown_usage_calls"] = sum(
            r.get("usage_known") is False for r in result["ledger_receipts"]
        )
        (directory / "progress.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    class MeasuredJudge(CodexCLIProvider):
        def complete(self, prompt, **kwargs):
            spent = original["new_tokens"] + sum(r["total_tokens"] for r in ledger.receipts)
            if spent + len(prompt) // 3 + 20_000 > original["approved_budget"]:
                raise BudgetStop("Remaining comparison planning budget exhausted")
            call = {
                "phase": phase["value"],
                "purpose": kwargs["purpose"],
                "started_utc": datetime.now(UTC).isoformat(),
            }
            result["calls"].append(call)
            start = time.perf_counter()
            try:
                completion = super().complete(prompt, **kwargs)
                call["tokens"] = completion.usage.total_tokens
                return completion
            except LLMError as exc:
                call["error"] = str(exc)
                if not exc.usage_known:
                    raise BudgetStop("Unknown grading usage; preserve and stop") from exc
                raise
            finally:
                call["seconds"] = time.perf_counter() - start
                save_progress()

    result["calls"] = prior_calls
    provider = MeasuredJudge(cfg, ledger)
    start = time.perf_counter()
    try:
        for label, key in [("codex", "codex_judge"), ("claude", "claude_common_judge")]:
            source = manifests[label]
            clone = copy.deepcopy(source)
            clone["run_id"] = f"{stamp}-{label}-smoke30-grading-resume"
            clone["kind"] = "grading-only-saved-answer-replay"
            clone["source_run"] = source["run_id"]
            clone["grading_only"] = True
            path = RUNS_DIR / f"{clone['run_id']}.json"
            with path.open("x", encoding="utf-8") as stream:
                json.dump(clone, stream, indent=2, ensure_ascii=False)
            result["grading_manifests"][label] = {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha(path),
                "source_run": source["run_id"],
                "same_answer_entries": clone["items"] == source["items"],
            }
            phase["value"] = f"grade_{label}_resumed"
            print("Grading saved", label, "answers", flush=True)
            result[key] = judge(
                provider, cfg, clone, items, log=lambda message: print(message, flush=True)
            )
            result[key + "_sha256"] = file_sha(PROJECT_ROOT / result[key]["file"])
            save_progress()
        result["completed"] = all(
            result[key]["items"] == 30 and not result[key]["problems"]
            for key in ["codex_judge", "claude_common_judge"]
        )
    except BaseException as exc:
        result["completed"] = False
        result["interruption"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        result["resumed_grading_seconds"] = time.perf_counter() - start
        result["completed_utc"] = datetime.now(UTC).isoformat()
        save_progress()
        with (directory / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
        print("Saved", directory / "result.json", flush=True)


if __name__ == "__main__":
    main()
