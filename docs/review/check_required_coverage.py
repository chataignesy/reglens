"""Free, read-only corpus probes against saved development answers; never regrade them.

Run from the repository root with .venv/Scripts/python.exe docs/review/check_required_coverage.py.
"""

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import psycopg

from reglens.agent.tools import _rows
from reglens.answer.required_evidence import evidence_units
from reglens.answer.research import guard
from reglens.eval.fingerprint import SINGLE_FILES, code_hash
from reglens.index.db import DEFAULT_URL
from reglens.retrieve.search import Filters

BASELINE = Path("docs/results/codex-frozen118-2026-11-14.json")
OUTPUT = Path("docs/review/required-coverage-local-2026-11-14.json")
TARGETS = {"app-004", "dod-005", "val-001", "lom-001", "mh-012", "irb-007"}
VARIATIONS = {
    "app-004": "Do the definition-of-default guidelines apply to smaller institutions?",
    "dod-005": "Which conditions permit reclassification after distressed restructuring?",
    "val-001": "Which additional validation tools must IRB institutions use beyond back-testing?",
    "lom-001": "What responsibilities does the management body have for credit granting?",
    "mh-012": "Which components enter economic loss for realised LGD?",
    "irb-007": "Which short-term exposures qualify for a maturity floor of one day?",
}


def main():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    results, counts, controls = [], Counter(), []
    with psycopg.connect(DEFAULT_URL) as conn:
        for item in baseline["items"]:
            if item["abstained"]:
                continue
            ids = [r["id"] for r in item["citation_map"]]
            rows = {r.id: r for r in _rows(conn, "id = ANY(%s)", [ids], limit=80)}
            hits = [rows[cid].hit() for cid in ids if cid in rows]
            data = {k: item[k] for k in ["answer", "claims", "missing_info",
                                        "missing_requirements", "answer_requirements"]}
            data["research_needed"] = False
            gaps = guard(item["question"], data, hits, conn=conn)
            score = item["grade"]["score"]
            counts[f"saved_score_{score}_guard_{bool(gaps)}"] += 1
            if score == 2 and gaps:
                controls.append({"id": item["id"], "gaps": gaps})
            if item["id"] not in TARGETS:
                continue
            targets = [g[0].cite for g in evidence_units(conn, item["question"], hits)]
            # New development wording on the same anchors. These are not a holdout.
            negatives = ["What is the publication date?", "Which document was published first?",
                         "Does this apply to my bank?"]
            negative_targets = {
                q: len(evidence_units(conn, q, hits)) for q in negatives
            }
            assert not any(negative_targets.values())
            assert not evidence_units(conn, item["question"], hits, Filters(source_ids=[]))
            assert gaps, item["id"]
            variation_gaps = guard(VARIATIONS[item["id"]], deepcopy(data), hits, conn=conn)
            assert variation_gaps, VARIATIONS[item["id"]]
            results.append({"id": item["id"], "target_keys": targets, "gaps": gaps,
                            "development_variation": VARIATIONS[item["id"]],
                            "variation_gaps": variation_gaps,
                            "negative_probe_targets": negative_targets})
        # Adjacent topic: exercise list structure using an intentionally incomplete synthetic
        # draft. This is a free availability check, not a reference answer or legal assessment.
        adjacent_question = "Which conditions must life insurance policies satisfy for collateral?"
        adjacent_hits = [r.hit() for r in _rows(
            conn, "source_id = %s AND article = %s AND kind = 'article'",
            ["crr3-consolidated", "212"], limit=1,
        )]
        adjacent_data = {
            "answer": "The listed conditions must be met [C1].",
            "claims": [{"text": "Conditions apply", "citations": ["C1"]}],
            "missing_info": False, "research_needed": False,
        }
        adjacent_gaps = guard(adjacent_question, adjacent_data, adjacent_hits, conn=conn)
        assert adjacent_gaps
    report = {
        "basis": "saved development answers/current SQL corpus; no model calls or regrading",
        "answer_code_hash": code_hash(SINGLE_FILES),
        "saved_score_guard_counts": dict(counts), "targets": results,
        "full_credit_answers_flagged_for_review": controls,
        "adjacent_structural_check": {"question": adjacent_question, "gaps": adjacent_gaps},
        "limits": "Lexical omissions and finite structural probes are conservative signals. "
                  "A flag can request unnecessary review; no flag does not certify completeness.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"targets": len(results), "counts": dict(counts),
                      "full_credit_flags": [r["id"] for r in controls], "output": str(OUTPUT)}))


if __name__ == "__main__":
    main()
