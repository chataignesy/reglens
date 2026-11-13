"""Verify artifacts and export paired answer comparisons; no model calls."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.eval.answers import citation_recall, file_sha, load_run
from reglens.eval.judge import citation_map
from reglens.eval.snapshots import load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    run = json.loads(args.result.read_text(encoding="utf-8"))
    if not run["completed"]:
        raise ValueError("Comparison is incomplete; do not publish a full-cohort result")
    plan = run["plan"]
    _, items = load(PROJECT_ROOT / f"evals/frozen/{plan['snapshot_sha256']}.json")
    by_id = {i.id: i for i in items}
    codex = load_run(run["codex"]["run_id"])
    for name in ("codex", "codex_judge", "claude_common_judge"):
        key = "codex_manifest_sha256" if name == "codex" else name + "_sha256"
        if file_sha(PROJECT_ROOT / run[name]["file"]) != run[key]:
            raise ValueError(f"Modified run or grading report: {name}")
    claude = json.loads((PROJECT_ROOT / run["claude_saved_manifest"]).read_text(encoding="utf-8"))
    historical = json.loads(
        (PROJECT_ROOT / "docs/results/frozen-118-rerun-2026-11-13.json").read_text(encoding="utf-8")
    )
    original_scores = {i["id"]: i["judge"] for i in historical["per_item"]}
    grades = {
        "codex": {i["id"]: i for i in run["codex_judge"]["per_item"]},
        "claude": {i["id"]: i for i in run["claude_common_judge"]["per_item"]},
    }
    entries = {
        "codex": {i["id"]: i for i in codex["items"]},
        "claude": {i["id"]: i for i in claude["items"]},
    }
    timings = {}
    for timing in run["timings"]:
        timings[timing["id"]] = timings.get(timing["id"], 0) + timing["seconds"]
    pairs = []
    for id in plan["ids"]:
        item = by_id[id]
        pair = {
            "id": id,
            "type": item.type,
            "topic": item.topic,
            "question": item.question,
            "reference": item.expected_answer,
            "grading_notes": item.grading_notes,
            "historical_claude_haiku_grade": original_scores[id],
        }
        for name in ("codex", "claude"):
            entry = entries[name][id]
            path = PROJECT_ROOT / entry["artifact"]
            if file_sha(path) != entry["artifact_sha256"]:
                raise ValueError(f"Modified answer: {name} {id}")
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["question"] != item.question:
                raise ValueError("Different question texts cannot be paired")
            pair[name] = {
                "answer": record["answer"],
                "abstained": record["abstained"],
                "abstain_reason": record.get("abstain_reason"),
                "usable": bool(str(record.get("answer") or "").strip())
                and not record["abstained"]
                and not record.get("unverified"),
                "missing_info": record.get("missing_info", False),
                "missing_requirements": record.get("missing_requirements", []),
                "errors": record.get("errors", []),
                "unverified": record.get("unverified", False),
                "check": record.get("check"),
                "citation_recall": None
                if item.type == "out_of_scope"
                else citation_recall(item, record),
                "citations": citation_map(record),
                "grade": grades[name][id],
                "planned": entry["planned"],
                "route": entry["route"],
                "attempts": entry["attempts"],
                "logical_answer_tokens": entry["tokens"] - entry.get("router_tokens", 0),
                "usage_unknown_calls": entry.get("usage_unknown_calls", 0),
                "artifact": entry["artifact"],
                "artifact_sha256": entry["artifact_sha256"],
            }
        pair["score_difference"] = (
            pair["codex"]["grade"]["score"] - pair["claude"]["grade"]["score"]
        )
        pair["codex_answer_execution_seconds"] = timings.get(id)
        pairs.append(pair)

    def mean(values):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None

    ins = [p for p in pairs if p["type"] != "out_of_scope"]
    oos = [p for p in pairs if p["type"] == "out_of_scope"]
    summary = {}
    for name in ("codex", "claude"):
        summary[name] = {
            "in_scope_items": len(ins),
            "mean_score_fraction": mean([p[name]["grade"]["score"] / 2 for p in ins]),
            "score_distribution": dict(Counter(p[name]["grade"]["score"] for p in ins)),
            "out_of_scope_refusals": sum(p[name]["abstained"] for p in oos),
            "out_of_scope_items": len(oos),
            "usable_in_scope": sum(p[name]["usable"] for p in ins),
            "citation_recall": mean([p[name]["citation_recall"] for p in ins]),
            "mechanical_macro_pass_rate": mean(
                [(p[name]["check"] or {}).get("supported_rate") for p in ins]
            ),
            "logical_answer_tokens": sum(p[name]["logical_answer_tokens"] for p in pairs),
            "reports_incomplete": [p["id"] for p in ins if p[name]["missing_info"]],
            "grade_flags": {
                p["id"]: p[name]["grade"]["flags"] for p in pairs if p[name]["grade"].get("flags")
            },
            "by_type": {
                type: mean([p[name]["grade"]["score"] / 2 for p in ins if p["type"] == type])
                for type in sorted({p["type"] for p in ins})
            },
        }
    paired = {
        "codex_higher": sum(p["score_difference"] > 0 for p in ins),
        "equal": sum(p["score_difference"] == 0 for p in ins),
        "claude_higher": sum(p["score_difference"] < 0 for p in ins),
    }
    out = {
        "source_result": str(args.result.resolve()),
        "source_result_sha256": file_sha(args.result),
        "methodology": plan,
        "summary": summary,
        "paired_in_scope": paired,
        "new_tokens": run["new_tokens"],
        "new_ledger_receipts": run["ledger_receipts"],
        "answer_phase_seconds": run["answer_phase_seconds"],
        "historical_latency_available": False,
        "pairs": pairs,
    }
    base = PROJECT_ROOT / "docs/results/codex-claude-smoke30-2026-11-13"
    with base.with_suffix(".json").open("x", encoding="utf-8") as stream:
        json.dump(out, stream, indent=2, ensure_ascii=False)
    with base.with_suffix(".csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "id",
                "type",
                "codex_score",
                "claude_common_score",
                "claude_old_score",
                "codex_tokens",
                "claude_logical_tokens",
                "codex_incomplete",
                "claude_incomplete",
            ]
        )
        for p in pairs:
            writer.writerow(
                [
                    p["id"],
                    p["type"],
                    p["codex"]["grade"]["score"],
                    p["claude"]["grade"]["score"],
                    p["historical_claude_haiku_grade"]["score"],
                    p["codex"]["logical_answer_tokens"],
                    p["claude"]["logical_answer_tokens"],
                    p["codex"]["missing_info"],
                    p["claude"]["missing_info"],
                ]
            )
    # Data is text, not executable HTML. Escape '<' to prevent an answer closing the script tag.
    data = json.dumps(pairs, ensure_ascii=False).replace("<", "\\u003c")
    html = r"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>RegLens: paired answer review</title><style>
body{font:16px system-ui;margin:24px auto;max-width:1400px;padding:0 20px;color:#17243b}
header{border-bottom:2px solid #256577;margin-bottom:20px}select{max-width:100%;padding:10px}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}
article{background:#f5f8fa;padding:20px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.6 system-ui}h2{color:#215e71}
aside{padding:16px;border:1px solid #c4d4dc;margin-top:16px}.meta{color:#526176}
@media(max-width:800px){.columns{grid-template-columns:1fr}}</style>
<header><h1>RegLens — Codex and saved Claude answers</h1>
<p>30 fixed development questions. Common Codex grader; historical Claude generation.
Code and orchestration differ. These are automated scores, not a controlled model ranking.</p>
<p>Personal open-source project; not affiliated with an employer or supervisor;
not legal advice.</p>
<select id="questions"></select></header><h2 id="question"></h2><p id="meta" class="meta"></p>
<div class="columns"><article><h2>Codex</h2><p id="codexScore"></p><pre id="codex"></pre>
<details><summary>Checks, gaps and citations</summary>
<pre id="codexDetails"></pre></details></article>
<article><h2>Saved Claude</h2><p id="claudeScore"></p><pre id="claude"></pre>
<details><summary>Checks, gaps and citations</summary>
<pre id="claudeDetails"></pre></details></article></div>
<aside><details><summary>Frozen reference and grading guidance</summary><pre id="reference"></pre>
</details></aside><script type="application/json" id="data">__DATA__</script><script>
const pairs=JSON.parse(document.getElementById('data').textContent);
const q=document.getElementById('questions');
for(const [i,p] of pairs.entries()){let o=document.createElement('option');o.value=i;
o.textContent=p.id+' · '+p.type+' · '+p.question;q.appendChild(o)}
function show(){let p=pairs[Number(q.value)];
document.getElementById('question').textContent=p.question;
document.getElementById('meta').textContent=p.id+' · '+p.type+' · '+p.topic;
for(const k of ['codex','claude']){let a=p[k];document.getElementById(k).textContent=
a.abstained?'Refused: '+a.abstain_reason:(a.answer||'No usable answer');
document.getElementById(k+'Score').textContent='Common-judge score: '+a.grade.score+'/2 · '+
a.logical_answer_tokens.toLocaleString()+' logical answer tokens';
document.getElementById(k+'Details').textContent=JSON.stringify({grade:a.grade,
missing_info:a.missing_info,missing_requirements:a.missing_requirements,
citation_recall:a.citation_recall,check:a.check,citations:a.citations},null,2)}
document.getElementById('reference').textContent=p.reference+'\n\n'+p.grading_notes}
q.addEventListener('change',show);show();</script></html>"""
    with base.with_suffix(".html").open("x", encoding="utf-8") as stream:
        stream.write(html.replace("__DATA__", data))
    print(
        json.dumps(
            {
                "summary": summary,
                "paired": paired,
                "new_tokens": run["new_tokens"],
                "output": str(base),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
