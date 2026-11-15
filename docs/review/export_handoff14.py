"""Audit both paired arms and compare quality/cost without changing old evidence."""

import argparse
import json
from collections import Counter
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.eval.answers import file_sha


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect(path):
    report = read(path)
    assert report["completed"] and not report["judge"]["problems"]
    manifest_path = PROJECT_ROOT / report["answers"]["file"]
    assert file_sha(manifest_path) == report["manifest_sha256"]
    manifest = read(manifest_path)
    grades = {r["id"]: r for r in report["judge"]["per_item"]}
    metrics = {r["id"]: r for r in report["answers"]["per_item"]}
    items, attempts = {}, 0
    for entry in manifest["items"]:
        for attempt in entry["attempt_artifacts"]:
            assert file_sha(PROJECT_ROOT / attempt["artifact"]) == attempt["artifact_sha256"]
            attempts += 1
        answer = read(PROJECT_ROOT / entry["artifact"])
        items[entry["id"]] = {"entry": entry, "grade": grades[entry["id"]],
                              "metrics": metrics[entry["id"]],
                              "answer": answer["answer"], "claims": answer["claims"],
                              "missing_info": answer["missing_info"],
                              "missing_requirements": answer.get("missing_requirements", []),
                              "trace": answer.get("trace", []),
                              "context": answer["context"]}
    for call in report["calls"]:
        assert file_sha(PROJECT_ROOT / call["artifact"]) == call["artifact_sha256"]
    receipts = report["ledger_receipts"]
    assert len(receipts) == len(report["calls"])
    unknown = sum(not r.get("usage_known", True) for r in receipts)
    failed = [c for c in report["calls"] if c.get("error")]
    if unknown or failed:
        assert report.get("resumptions"), "Failed calls need an explicit recorded resumption"
    for call, receipt in zip(report["calls"], receipts, strict=True):
        if receipt.get("usage_known", True):
            assert call["tokens"] == receipt["total_tokens"]
        else:
            assert call.get("error") and call.get("tokens") is None
    tokens = sum(r["total_tokens"] for r in receipts)
    assert tokens == report["new_tokens"] <= report["budget"]
    for rel, expected in report["identity"]["source_hashes"].items():
        assert file_sha(PROJECT_ROOT / "src/reglens" / rel) == expected
    purposes, seconds = Counter(), Counter()
    for receipt in receipts:
        purposes[receipt["purpose"]] += receipt["total_tokens"]
    for call in report["calls"]:
        seconds[call["phase"]] += call["seconds"]
    return {"result": str(path), "result_sha256": file_sha(path),
            "identity": report["identity"], "run_id": manifest["run_id"],
            "known_tokens": tokens, "calls": len(receipts), "tokens_by_purpose": dict(purposes),
            "unknown_usage_calls": unknown, "failed_calls": failed,
            "resumptions": report.get("resumptions", []),
            "active_seconds": dict(seconds), "answer_summary": report["answers"],
            "judge_summary": report["judge"], "items": items,
            "audit": {"attempt_artifacts_verified": attempts,
                      "model_call_artifacts_verified": len(receipts)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("llm", type=Path)
    parser.add_argument("single_first", type=Path)
    args = parser.parse_args()
    llm, candidate = collect(args.llm), collect(args.single_first)
    assert llm["identity"]["routing_strategy"] == "llm"
    assert candidate["identity"]["routing_strategy"] == "single_first"
    for key in ["source_hashes", "snapshot_sha256", "config_sha256", "corpus_generation"]:
        assert llm["identity"][key] == candidate["identity"][key]
    assert set(llm["items"]) == set(candidate["items"]) and len(llm["items"]) == 14
    cohort = PROJECT_ROOT / "evals/cohorts/handoff-remaining14-2026-11-14.json"
    assert set(read(cohort)["ids"]) == set(llm["items"])
    left = {k: v for k, v in llm["identity"]["effective_answer_settings"].items() if k != "routing"}
    right = {k: v for k, v in candidate["identity"]["effective_answer_settings"].items()
             if k != "routing"}
    assert left == right
    assert llm["known_tokens"] + candidate["known_tokens"] <= 3_000_000
    differences = []
    for cid, old in llm["items"].items():
        new = candidate["items"][cid]
        assert old["entry"]["question_sha"] == new["entry"]["question_sha"]
        differences.append({"id": cid, "llm_score": old["grade"]["score"],
                            "single_first_score": new["grade"]["score"],
                            "score_change": new["grade"]["score"] - old["grade"]["score"],
                            "llm_answer_route_tokens": old["entry"]["tokens"],
                            "single_first_answer_route_tokens": new["entry"]["tokens"]})
    regressions = [d["id"] for d in differences if d["score_change"] < 0]
    output = {"basis": "paired fresh development runs; automated, not practitioner review",
              "cohort_sha256": file_sha(cohort),
              "default_routing": "llm; candidate remains opt-in pending independent/wider evidence",
              "known_tokens_total": llm["known_tokens"] + candidate["known_tokens"],
              "unknown_usage_calls_total": (llm["unknown_usage_calls"]
                                             + candidate["unknown_usage_calls"]),
              "score_regressions": regressions, "differences": differences,
              "llm": llm, "single_first": candidate}
    base = PROJECT_ROOT / "docs/results/handoff-routing14-2026-11-15"
    with base.with_suffix(".json").open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    a, b = llm["judge_summary"], candidate["judge_summary"]
    at, bt = llm["answer_summary"]["total_tokens"], candidate["answer_summary"]["total_tokens"]
    lines = ["# Broader verification and routing comparison — 15 November 2026", "",
             "Personal project; not affiliated with an employer or supervisor; "
             "not legal or regulatory advice.", "",
             "Two fresh arms on 14 identical frozen development questions: 13 in scope and "
             "one out-of-scope control. The product, corpus, model and references match; routing "
             "strategy differs. One trajectory per arm; this is not an independent holdout.", "",
             "| Metric | LLM routing | Single-first |", "|---|---:|---:|",
             f"| In-scope automated mean | {a['correctness_in_scope']:.1%} | "
             f"{b['correctness_in_scope']:.1%} |",
             f"| Full / partial / wrong | {a['fully_correct']} / {a['partly_correct']} / "
             f"{a['wrong']} | {b['fully_correct']} / {b['partly_correct']} / {b['wrong']} |",
             f"| Correct refusals | {a['out_of_scope_declined']} | {b['out_of_scope_declined']} |",
             f"| Routing + answer tokens | {at:,} | {bt:,} |",
             f"| Known total tokens, including grading | {llm['known_tokens']:,} | "
             f"{candidate['known_tokens']:,} |", "",
             f"Routing + answer change: {(bt / at - 1):+.1%} for completed answer attempts. "
             f"Known total usage: {output['known_tokens_total']:,} against the approved 3M "
             f"reserve, plus {output['unknown_usage_calls_total']} request(s) with unreported "
             "usage. Known totals are lower bounds when usage is unknown. Every model-call "
             "and answer-attempt artifact was verified, including failed calls.", "",
             "| Case | LLM score | Single-first score | LLM tokens | Single-first tokens |",
             "|---|---:|---:|---:|---:|"]
    for row in differences:
        lines.append(f"| {row['id']} | {row['llm_score']} | {row['single_first_score']} | "
                     f"{row['llm_answer_route_tokens']:,} | "
                     f"{row['single_first_answer_route_tokens']:,} |")
    lines += ["", "## Interpretation and limits", "",
              "The default remains LLM routing. Single-first is an opt-in policy with the same "
              "scope/retrieval gate and bounded required-gap fallback; it is not a completeness "
              "guarantee. Grade differences may reflect sampling as well as routing. Policy "
              "agreement with question-type labels is not an answer-quality metric.", "",
              "Score regressions under the unchanged rubric: " + (", ".join(regressions) or "none")
              + ". Missing-fact lists, contradictions, gap flags, citations, traces and source "
              "references are retained in the machine-readable report. Exact-content judge "
              "caching uses the existing identity; token totals count only actual new calls.", "",
              "mh-006/mh-014 retain their frozen references and raw grades. Independent "
              "practitioner review and a separately authored sealed holdout remain pending "
              "at the user's request. No full benchmark was rerun.", "",
              "The LLM arm was interrupted by subscription quota and explicitly resumed by "
              "the user. Completed answers were reused; the rejected request remains preserved "
              "as unknown usage, never zero. No product code changed between attempts or arms.", "",
              "[All answers, grades, usage and audits](handoff-routing14-2026-11-15.json).", ""]
    with base.with_suffix(".md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    print(json.dumps({k: v for k, v in output.items() if k not in ["llm", "single_first"]},
                     indent=2))


if __name__ == "__main__":
    main()
