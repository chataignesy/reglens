"""Export a completed Codex full benchmark without any model calls.

Personal project; not affiliated with an employer or supervisor; not legal/regulatory advice.
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.eval.answers import file_sha
from reglens.eval.snapshots import items_from_payload

DISCLAIMER = (
    "Personal project; not affiliated with an employer or supervisor; "
    "not legal or regulatory advice."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", required=True, help="New output stem relative to project root")
    args = parser.parse_args()
    result_path = args.result.resolve()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if not result["completed"]:
        raise ValueError("This exporter requires completed answers and grading")
    manifest_path = PROJECT_ROOT / result["answers"]["file"]
    if file_sha(manifest_path) != result["manifest_sha256"]:
        raise ValueError("Answer manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = {i.id: i for i in items_from_payload(manifest["dataset"]["snapshot"])}
    grades = {g["id"]: g for g in result["judge"]["per_item"]}
    metrics = {r["id"]: r for r in result["answers"]["per_item"]}
    if not len(items) == len(manifest["items"]) == len(grades) == 118:
        raise ValueError("Expected all 118 frozen questions, answers and grades")
    rows = []
    for entry in manifest["items"]:
        item = items[entry["id"]]
        path = PROJECT_ROOT / entry["artifact"]
        if file_sha(path) != entry["artifact_sha256"]:
            raise ValueError(f"Answer artifact changed: {item.id}")
        answer = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "id": item.id,
                "type": item.type,
                "topic": item.topic,
                "question": item.question,
                "reference": item.expected_answer,
                "grading_notes": item.grading_notes,
                "entry": entry,
                "answer": answer["answer"],
                "abstained": answer["abstained"],
                "abstain_reason": answer["abstain_reason"],
                "claims": answer["claims"],
                "missing_info": answer["missing_info"],
                "missing_requirements": answer["missing_requirements"],
                "answer_requirements": answer.get("answer_requirements", []),
                "errors": answer["errors"],
                "unverified": answer.get("unverified", False),
                "citation_map": [
                    {k: h.get(k) for k in ("id", "source_id", "ref", "title", "hierarchy")}
                    for h in answer["context"]
                ],
                "grade": grades[item.id],
                "metrics": metrics[item.id],
            }
        )
    ins = [r for r in rows if r["type"] != "out_of_scope"]
    oos = [r for r in rows if r["type"] == "out_of_scope"]
    score_counts = Counter(r["grade"]["score"] for r in ins)
    purposes = Counter()
    call_seconds = Counter()
    unknown_calls = sum(not r.get("usage_known", True) for r in result["ledger_receipts"])
    for receipt in result["ledger_receipts"]:
        purposes[receipt["purpose"]] += receipt["total_tokens"]
    for call in result["calls"]:
        call_seconds[call["phase"]] += call.get("seconds", 0)
    counts = Counter(r["entry"]["route"] for r in rows)
    by_type = {}
    for kind in sorted({r["type"] for r in rows}):
        subset = [r for r in rows if r["type"] == kind]
        by_type[kind] = {
            "questions": len(subset),
            "mean_score": sum(r["grade"]["score"] for r in subset) / (2 * len(subset)),
            "full": sum(r["grade"]["score"] == 2 for r in subset),
            "partial": sum(r["grade"]["score"] == 1 for r in subset),
            "wrong": sum(r["grade"]["score"] == 0 for r in subset),
        }
    paired = []
    prior_path = PROJECT_ROOT / "docs/results/codex-claude-smoke30-2026-11-13.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in rows}
    for pair in prior["pairs"]:
        current = by_id[pair["id"]]
        paired.append(
            {
                "id": pair["id"],
                "type": pair["type"],
                "current_codex": current["grade"]["score"],
                "prior_codex": pair["codex"]["grade"]["score"],
                "saved_claude": pair["claude"]["grade"]["score"],
            }
        )
    export = {
        "disclaimer": DISCLAIMER,
        "result_path": str(result_path.relative_to(PROJECT_ROOT)),
        "result_sha256": file_sha(result_path),
        "run": result,
        "items": rows,
        "score_counts_in_scope": dict(score_counts),
        "tokens_by_purpose": dict(purposes),
        "usage_unknown_calls": unknown_calls,
        "active_model_call_seconds_by_phase": dict(call_seconds),
        "routes": dict(counts),
        "by_type": by_type,
        "prior_smoke30_sha256": file_sha(prior_path),
        "overlap_30_scores": paired,
        "comparison_caveat": "Overlap scores reuse saved grades; code, routing and generation "
        "differ. The judge model and prompt match, but this is not a controlled "
        "provider-only comparison or an independent holdout.",
    }
    stem = PROJECT_ROOT / args.output
    for suffix in (".json", ".csv", ".md"):
        if stem.with_suffix(suffix).exists():
            raise FileExistsError(stem.with_suffix(suffix))
    with stem.with_suffix(".json").open("x", encoding="utf-8") as stream:
        json.dump(export, stream, indent=2, ensure_ascii=False)
    with stem.with_suffix(".csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "id",
                "type",
                "route",
                "attempts",
                "score",
                "tokens",
                "citation_recall",
                "mechanical_pass_rate",
                "missing_info",
                "missing",
                "contradictions",
                "disclaimer",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["id"],
                    row["type"],
                    row["entry"]["route"],
                    ",".join(row["entry"].get("attempts", [])),
                    row["grade"]["score"],
                    row["metrics"]["tokens"],
                    row["metrics"]["citation_recall"],
                    row["metrics"]["check_pass_rate"],
                    row["missing_info"],
                    "; ".join(row["grade"].get("missing", [])),
                    "; ".join(row["grade"].get("contradictions", [])),
                    DISCLAIMER,
                ]
            )
    grade = result["judge"]
    text = [
        "# Full frozen118 benchmark with Codex",
        "",
        DISCLAIMER,
        "",
        f"Run: `{result['answers']['run_id']}`. All 118 questions have answer records and grades.",
        "Fresh Codex routing and a separate answer cache; no pilot answers reused. "
        "The frozen references and product code stayed unchanged during the run.",
        "",
        "## Results",
        "",
        f"- In-scope mean score: **{100 * grade['correctness_in_scope']:.1f}%** "
        f"across {len(ins)} questions.",
        f"- Full / partial / wrong: **{score_counts[2]} / {score_counts[1]} / {score_counts[0]}**.",
        f"- Out-of-scope refusals: **{sum(r['abstained'] for r in oos)}/{len(oos)}**.",
        f"- Citation-group recall: {100 * result['answers']['citation_recall']:.1f}%.",
        "- Mean mechanical claim-check pass rate: "
        f"{100 * result['answers']['check_pass_rate']:.1f}%.",
        f"- New known subscription tokens: **{result['new_tokens']:,}** "
        "of the approved 8,000,000 reserve.",
        f"- Requests with unreported usage: **{unknown_calls}**; known tokens are a lower bound.",
        f"- Score status: `{grade['score_status']}`; no practitioner sign-off is implied.",
        "",
        "## Usage and runtime",
        "",
        "| Purpose | New tokens |",
        "|---|---:|",
    ]
    text += [f"| {p} | {n:,} |" for p, n in purposes.items()]
    text += [
        "",
        f"Final answer-execution phase: {result['answer_phase_seconds']:.1f} seconds. "
        f"Grading phase: {result['grading_phase_seconds']:.1f} seconds. "
        "After an interruption, the final execution phase includes reuse of previously saved work; "
        "it is not the full answer-generation runtime across all attempts. Active model-call time "
        "by phase is recorded separately below and excludes the overnight quota wait, SQL work and "
        "service startup. Subscription token counts are not a monetary "
        "charge estimate; API-equivalent prices for this model remain unconfigured.",
        "",
        "| Phase | Active model-call seconds, all attempts |",
        "|---|---:|",
        *[f"| {phase} | {seconds:.1f} |" for phase, seconds in call_seconds.items()],
        "",
        "The run stopped on a subscription usage-limit rejection and was explicitly resumed after "
        "the reported reset. Completed answers were not regenerated. The rejected call did not "
        "report token usage; its receipt remains unknown rather than being labelled zero cost.",
        "",
        "## Answers needing review",
        "",
        "| ID | Score | Missing or conflicting key facts |",
        "|---|---:|---|",
    ]
    for row in ins:
        if row["grade"]["score"] < 2:
            issues = row["grade"].get("missing", []) + row["grade"].get("contradictions", [])
            detail = "; ".join(issues) or row["grade"].get("rationale", "No usable answer")
            text.append(f"| {row['id']} | {row['grade']['score']} | {detail.replace('|', '/')} |")
    text += [
        "",
        "## Results by question type",
        "",
        "| Type | Questions | Mean score | Full / partial / wrong |",
        "|---|---:|---:|---|",
    ]
    for kind, stats in by_type.items():
        text.append(
            f"| {kind} | {stats['questions']} | {100 * stats['mean_score']:.1f}% | "
            f"{stats['full']} / {stats['partial']} / {stats['wrong']} |"
        )
    overlap = [p for p in paired if p["type"] != "out_of_scope"]
    text += [
        "",
        "## Historical context on the 30-question overlap",
        "",
        "These are saved earlier grades under the same judge model and prompt, compared "
        "with the fresh full-run answers on the overlapping questions. They add no model calls. "
        "Different code, routing, generation dates and model sampling prevent a provider-only "
        "attribution. The questions are already used development examples.",
        "",
        f"There are {len(overlap)} in-scope questions in the overlap.",
        "",
        "| Answer set | Mean in-scope score on the overlap |",
        "|---|---:|",
    ]
    for label, key in [
        ("Current Codex full run", "current_codex"),
        ("Earlier Codex smoke run", "prior_codex"),
        ("Saved Claude answers, earlier common-judge grades", "saved_claude"),
    ]:
        mean = sum(p[key] for p in overlap) / (2 * len(overlap))
        text.append(f"| {label} | {100 * mean:.1f}% |")
    text += [
        "",
        "## Limits and evidence",
        "",
        "This is a development benchmark on questions already used to diagnose the system. "
        "It is not an unseen holdout. The same model family generates and grades answers, so "
        "judge bias and rubric interpretation remain possible. Scores, citation recall and "
        "mechanical checks measure different properties; none certifies legal completeness.",
        "",
        "The suspected rubric-scope issues for mh-006 and mh-014 remain unchanged in the frozen "
        "references. Their raw grades are preserved. The JSON includes all 118 questions, "
        "answers, claim checks, citation maps, grades and artifact hashes. The CSV provides "
        "one row per question. The 30-question overlap contains saved Codex/Claude grades for "
        "context only; changes in code and routing prevent a model-only attribution.",
        "",
        f"Raw result: `{export['result_path']}`.",
        "",
    ]
    with stem.with_suffix(".md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(text))
    print(f"Exported {len(rows)} verified answers and grades to {stem}")


if __name__ == "__main__":
    main()
