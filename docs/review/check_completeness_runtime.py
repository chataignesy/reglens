"""Read-only SQL/retrieval checks and warm context-expansion timings. No model calls."""

import argparse
import json
import os
import statistics
import time
from datetime import UTC, datetime

from reglens.agent.tools import _rows, definition_rows
from reglens.answer.context_plan import expand_context, requested_gaps
from reglens.answer.research import guard
from reglens.config import PROJECT_ROOT
from reglens.eval.answers import file_sha
from reglens.eval.fingerprint import AGENT_FILES
from reglens.eval.snapshots import load
from reglens.index.db import connect
from reglens.retrieve.search import Filters, search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    os.environ["REGLENS_INFERENCE_URL"] = "http://127.0.0.1:18001"
    snapshot = PROJECT_ROOT / (
        "evals/frozen/20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b.json"
    )
    _, items = load(snapshot)
    result = {
        "disclaimer": "Personal project; not affiliated with an employer or supervisor; "
        "not legal or regulatory advice.",
        "utc": datetime.now(UTC).isoformat(),
        "snapshot_sha256": file_sha(snapshot),
        "source_hashes": {
            p: file_sha(PROJECT_ROOT / "src/reglens" / p) for p in sorted(set(AGENT_FILES))
        },
        "retrieval": [],
    }
    with connect() as conn:
        for item in items:
            if item.id not in {"pd-003", "app-001", "cmp-001"}:
                continue
            start = time.perf_counter()
            hits = search(conn, item.question, k=8)
            retrieval_seconds = time.perf_counter() - start
            samples = []
            for _ in range(7):
                start = time.perf_counter()
                expanded = expand_context(conn, item.question, hits)
                samples.append(time.perf_counter() - start)
            assert len(expanded) - len(hits) <= 4
            assert sum(len(h.text) for h in expanded[len(hits) :]) <= 12000
            if item.id == "app-001":
                assert not requested_gaps(conn, item.question, expanded)
                assert {"para. 1", "para. 2", "para. 3"} <= {
                    h.ref for h in expanded if h.title == "Foreword"
                }
            if item.id == "pd-003":
                assert any("two years" in h.text for h in expanded)
                assert any(
                    h.source_id == "crr3-consolidated" and h.ref == "Art. 180(2)" for h in expanded
                )
            if item.id == "cmp-001":
                assert any(
                    h.source_id == "crr3-amending-act" and "1(86)" in h.ref for h in expanded
                )
            result["retrieval"].append(
                {
                    "id": item.id,
                    "retrieval_seconds": retrieval_seconds,
                    "warm_expansion_seconds": samples,
                    "warm_expansion_median_ms": statistics.median(samples) * 1000,
                    "added": [h.id for h in expanded[len(hits) :]],
                    "evidence": [{"id": h.id, "ref": h.ref, "title": h.title} for h in expanded],
                }
            )
        gap = {
            "missing_info": True,
            "research_needed": False,
            "missing_requirements": [
                "The definition of 'large corporates' is needed for classification."
            ],
        }
        assert definition_rows(conn, "large corporates")
        assert guard("May this corporate use fixed M?", gap, [], conn=conn)
        assert gap["research_needed"] is True
        result["definition_gap"] = gap
        restricted = {
            "missing_info": True,
            "research_needed": False,
            "missing_requirements": ["The definition of 'large corporates' is needed."],
        }
        # A valid corpus definition must not escape an explicit source restriction.
        assert not guard(
            "May this corporate use fixed M?",
            restricted,
            [],
            conn=conn,
            filters=Filters(source_ids=["ecb-guide-internal-models"]),
        )
        parent_hits = [
            r.hit(1)
            for r in _rows(
                conn,
                "source_id = %s AND article = %s AND paragraph = %s AND point = %s",
                ["crr3-consolidated", "180", "1", "(h)"],
            )
        ]
        restricted_hits = expand_context(
            conn, "PD history", parent_hits, Filters(source_ids=["ecb-guide-internal-models"])
        )
        assert restricted_hits == parent_hits
        result["filter_preservation"] = "passed"
    with (PROJECT_ROOT / args.output).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(
        json.dumps(
            {
                "checks": "passed",
                "output": args.output,
                "median_expansion_ms": {
                    r["id"]: round(r["warm_expansion_median_ms"], 2) for r in result["retrieval"]
                },
            }
        )
    )


if __name__ == "__main__":
    main()
