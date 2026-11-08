"""Gap-analysis eval against the planted gaps (docs/synthetic-policy/gaps.yaml).

- recall: share of ALL planted gaps where at least one linked obligation is flagged partial,
  missing or contradicted (exit criterion: >= 0.85). A gap whose obligations were not assessed
  counts as not found; `gaps_assessed` and `complete` say how much of the run was assessed
  (review F9: a partial run must not show a full score);
- type accuracy: share of found gaps where a linked obligation gets exactly the planted type;
- other findings: flagged obligations not linked to any planted gap. A short synthetic policy
  cannot cover every obligation, so most are expected; a reviewer samples them.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.gap.gaps import Gap
from reglens.gap.match import FINDINGS, Verdict

GAP_RESULTS = PROJECT_ROOT / "data" / "gap"
DEMO_RESULT = PROJECT_ROOT / "docs" / "synthetic-policy" / "coverage-demo.json"
EXPORT_COLUMNS = [
    "obligation_id", "status", "clauses", "rationale", "source", "obligation", "topic",
    "quote", "reviewer_status", "reviewer_comment",
]


def list_runs() -> list[dict]:
    """Saved gap runs, newest local run first, then the committed demo run (review F7: the
    demo no longer hides local runs; which one is shown is explicit and labelled)."""
    runs = []
    for p in sorted(GAP_RESULTS.glob("gap-*.json"), reverse=True):
        stamp = datetime.strptime(p.stem.removeprefix("gap-"), "%Y%m%d-%H%M%S")
        runs.append({"id": p.stem, "label": f"Local run, {stamp:%d %b %Y %H:%M}",
                     "is_demo": False, "path": p})
    if DEMO_RESULT.exists():
        runs.append({"id": "demo", "label": "Committed demo run (synthetic policy)",
                     "is_demo": True, "path": DEMO_RESULT})
    return runs


def find_run(run_id: str | None = None) -> dict | None:
    """A run by id; without one, the newest local run, else the demo."""
    runs = list_runs()
    if run_id is None:
        return runs[0] if runs else None
    return next((r for r in runs if r["id"] == run_id), None)


def evaluate(gaps: list[Gap], verdicts: list[Verdict]) -> dict:
    by_ob = {v.obligation_id: v for v in verdicts}
    per_gap, linked = [], set()
    for g in gaps:
        linked |= set(g.obligations)
        vs = [by_ob[o] for o in g.obligations if o in by_ob]
        flagged = [v for v in vs if v.status in FINDINGS]
        per_gap.append(
            {
                "id": g.id, "type": g.type, "assessed": len(vs), "found": bool(flagged),
                "type_match": any(v.status == g.type for v in vs),
                "statuses": {v.obligation_id: v.status for v in vs},
            }
        )
    for r in per_gap:  # a gap counts as assessed only if a linked obligation got a verdict
        r["assessed"] = sum(s != "unassessed" for s in r["statuses"].values())
    assessed = [r for r in per_gap if r["assessed"]]
    found = [r for r in assessed if r["found"]]
    other = [v for v in verdicts if v.status in FINDINGS and v.obligation_id not in linked]
    return {
        "gaps": len(gaps),
        "gaps_assessed": len(assessed),
        "complete": len(assessed) == len(gaps),
        "recall": round(len(found) / len(gaps), 3) if gaps else None,
        "recall_of_assessed": round(len(found) / len(assessed), 3) if assessed else None,
        "type_accuracy": round(sum(r["type_match"] for r in found) / len(found), 3)
        if found
        else None,
        "by_type": {
            t: f"{sum(r['found'] for r in per_gap if r['type'] == t)}/"
            f"{sum(1 for r in per_gap if r['type'] == t)}"
            for t in ("missing", "partial", "contradicted")
        },
        "statuses": dict(Counter(v.status for v in verdicts).most_common()),
        "other_findings": len(other),
        "quotes_not_verbatim": sum(v.evidence == "not_verbatim" for v in verdicts),
        "invalid_verdicts": sum(v.evidence == "invalid" for v in verdicts),
        "per_gap": per_gap,
    }


def save(summary: dict, rows: list[dict]) -> tuple[Path, Path]:
    GAP_RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    js = GAP_RESULTS / f"gap-{stamp}.json"
    js.write_text(json.dumps(summary | {"rows": rows}, indent=2, ensure_ascii=False), "utf-8")
    cs = GAP_RESULTS / f"coverage-{stamp}.csv"
    with cs.open("w", newline="", encoding="utf-8-sig") as f:  # BOM: opens cleanly in Excel
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["obligation_id"])
        w.writeheader()
        for r in rows:
            w.writerow(r | {"clauses": ", ".join(r.get("clauses", []))})
    return js, cs
