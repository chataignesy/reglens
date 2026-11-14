"""Audit and publish a completed focused run without model calls or historical mutations."""

import argparse
import json
from collections import Counter
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.eval.answers import file_sha


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--baseline", type=Path,
                        default=PROJECT_ROOT / "docs/results/codex-frozen118-2026-11-14.json")
    parser.add_argument("--output", type=Path,
                        default=PROJECT_ROOT / "docs/results/codex-completeness8-2026-11-14")
    args = parser.parse_args()
    report = read(args.result)
    if not report.get("completed"):
        raise ValueError("Only a completed evaluation can be published")
    manifest_path = PROJECT_ROOT / report["answers"]["file"]
    assert file_sha(manifest_path) == report["manifest_sha256"]
    manifest = read(manifest_path)
    baseline_path = args.baseline
    baseline = {r["id"]: r for r in read(baseline_path)["items"]}
    grades = {r["id"]: r for r in report["judge"]["per_item"]}
    metrics = {r["id"]: r for r in report["answers"]["per_item"]}
    items, attempts = [], 0
    for entry in manifest["items"]:
        for attempt in entry["attempt_artifacts"]:
            assert file_sha(PROJECT_ROOT / attempt["artifact"]) == attempt["artifact_sha256"]
            attempts += 1
        artifact = PROJECT_ROOT / entry["artifact"]
        assert file_sha(artifact) == entry["artifact_sha256"]
        answer = read(artifact)
        old = baseline[entry["id"]]
        old_answer = old["answer"] if isinstance(old["answer"], dict) else old
        items.append({
            "id": entry["id"], "question": old["question"], "entry": entry,
            "answer": answer, "grade": grades[entry["id"]],
            "metrics": metrics[entry["id"]],
            "baseline": {k: old[k] for k in ["grade", "entry", "metrics"]} | {
                k: old_answer.get(k) for k in ["missing_info", "missing_requirements"]},
        })
    for call in report["calls"]:
        path = PROJECT_ROOT / call["artifact"]
        assert file_sha(path) == call["artifact_sha256"]
        assert read(path)["response"]["tokens"] == call["tokens"]
    receipts = report["ledger_receipts"]
    assert len(receipts) == len(report["calls"])
    assert all(r.get("usage_known", True) and r["outcome"] == "ok" for r in receipts)
    tokens = sum(r["total_tokens"] for r in receipts)
    assert tokens == report["new_tokens"] == sum(c["tokens"] for c in report["calls"])
    assert tokens <= report["budget"]
    for rel, expected in report["identity"]["source_hashes"].items():
        assert file_sha(PROJECT_ROOT / "src/reglens" / rel) == expected
    old_score = sum(i["baseline"]["grade"]["score"] for i in items) / (2 * len(items))
    new_score = sum(i["grade"]["score"] for i in items) / (2 * len(items))
    by_purpose = Counter()
    phase_seconds = Counter()
    for receipt in receipts:
        by_purpose[receipt["purpose"]] += receipt["total_tokens"]
    for call in report["calls"]:
        phase_seconds[call["phase"]] += call["seconds"]
    summary = {
        "disclaimer": "Personal project; not legal or regulatory advice.",
        "result_path": str(args.result), "result_sha256": file_sha(args.result),
        "run_id": manifest["run_id"], "baseline_sha256": file_sha(baseline_path),
        "snapshot_id": manifest["dataset"]["sha256"],
        "baseline_mean": old_score, "current_mean": new_score,
        "baseline_answer_route_tokens": sum(i["baseline"]["entry"]["tokens"] for i in items),
        "current_answer_route_tokens": report["answers"]["total_tokens"],
        "current_reports_incomplete": [i["id"] for i in items
                                       if i["answer"].get("missing_info")],
        "silent_partials": [i["id"] for i in items if i["grade"]["score"] == 1
                            and not i["answer"].get("missing_info")],
        "current_score_counts": dict(Counter(i["grade"]["score"] for i in items)),
        "known_tokens": tokens, "unknown_usage_calls": 0, "calls": len(receipts),
        "budget": report["budget"],
        "tokens_by_purpose": dict(by_purpose), "active_call_seconds": dict(phase_seconds),
        "audit": {"attempt_artifacts_verified": attempts,
                  "call_artifacts_verified": len(report["calls"]),
                  "manifest_verified": True, "source_hashes_verified": True},
        "score_status": report["judge"]["score_status"],
        "judge_model": report["judge"]["judge_model"],
        "judge_prompt": report["judge"]["judge_prompt"], "items": items,
    }
    base = args.output
    with base.with_suffix(".json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    lines = [
        "# Focused Codex coverage evaluation — 14 November 2026", "",
        "Personal project; not affiliated with an employer or supervisor; "
        "not legal or regulatory advice.", "",
        f"Completed {len(items)} fresh routed answers against unchanged frozen references. "
        f"Automated mean score: **{old_score:.2%} → {new_score:.2%}** on this selected "
        "development cohort. This is not a full benchmark or an independent holdout.", "",
        f"Usage: **{tokens:,} known tokens** of the {report['budget']:,}-token reserve; "
        f"{len(receipts)} calls; "
        "zero unknown-usage calls. All answer attempts, model-call artifacts and source hashes "
        "were verified. Claude remains the default configuration.", "",
        "| Question | Saved score | New score | Route / attempts | Missing-info flag |",
        "|---|---:|---:|---|---|",
    ]
    for item in items:
        entry = item["entry"]
        lines.append(f"| {item['id']} | {item['baseline']['grade']['score']} | "
                     f"{item['grade']['score']} | {' → '.join(entry['attempts'])} | "
                     f"{item['answer'].get('missing_info', False)} |")
    lines += ["", "Scores use 0/1/2; the mean divides by two. Grades are automated and "
              "unreviewed by a practitioner. Citation checks and gap flags do not "
              "certify completeness.",
              "", "## Remaining omissions", ""]
    omitted = False
    for item in items:
        if item["grade"].get("missing"):
            omitted = True
            lines.append(f"- **{item['id']}**: " + "; ".join(item["grade"]["missing"]))
    if not omitted:
        lines.append("The automated judge reported no missing key facts.")
    lines += ["", "## Cost and verification", "", "| Purpose | Tokens |", "|---|---:|"]
    lines += [f"| {purpose} | {used:,} |" for purpose, used in by_purpose.items()]
    lines += ["", f"Active model-call time: {sum(phase_seconds.values()):.1f} seconds. "
              f"Mechanical checks: {report['answers']['check_pass_rate']:.1%}; "
              f"citation-group recall: {report['answers']['citation_recall']:.1%}.", "",
              ("The two controls are `lgd-007` (an adjacent cost-component list) and `app-001` "
              "(a foreword-bound answer where additional applicability research is optional). "
              "Compare their attempts and tokens as well as scores; a retained full score "
              "does not establish that added work was necessary." if len(items) == 8 else
              "This two-case check targets cure conditions and economic-loss research specificity. "
              "It does not rerun the other cases or provide an independent holdout."), "",
              "No product code was changed during this run. Historical answers, references "
              "and published scores remain unchanged. Fresh routes and isolated answer caches "
              "were used. Judge verdict caching follows the existing exact-content identity; "
              "purpose totals show actual new grading usage.", "",
              "[All answers, grades, baseline comparisons and audit counts]"
              f"({base.name}.json).", "",
              f"Run: `{manifest['run_id']}`. Raw result: `{args.result}`.", ""]
    with base.with_suffix(".md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    print(json.dumps({k: v for k, v in summary.items() if k != "items"}, indent=2))


if __name__ == "__main__":
    main()
