"""Free audit of amendment recovery, all frozen routes and review-packet identity."""

import json
from pathlib import Path

from reglens.agent.tools import _rows
from reglens.answer.context_plan import expand_context
from reglens.answer.pipeline import Answer, Claim
from reglens.answer.research import guard
from reglens.answer.verify import check_answer
from reglens.eval.answers import file_sha
from reglens.eval.route import cached_routes
from reglens.eval.snapshots import load
from reglens.index.db import connect


def main():
    snapshot = Path("evals/frozen") / (
        "20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b.json"
    )
    _, items = load(snapshot)
    routes = cached_routes(items, strategy="single_first")
    assert len(routes) == 118 and all(r["tokens"] == 0 for r in routes.values())
    baseline_path = Path("docs/results/codex-frozen118-2026-11-14.json")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    with connect() as conn:
        child = _rows(conn, "id = %s", ["crr3-amending-act:article:1::(86)(a)"])[0]
        hits = expand_context(conn, "Which CRR3 provision changed the corporate PD floor?",
                              [child.hit(1)])
        parent = next(i for i, h in enumerate(hits, 1) if h.ref == "Art. 1(86)")
        claim = Claim("CRR Article 160(1) now has a PD floor of 0.05%", ["C1"], "law")
        ans = Answer("Which provision changed the floor?", False, "", "", [claim], hits, "")
        before = check_answer(ans)
        assert before["problems"] == {"unsupported_number": 1}
        gaps = guard(ans.question, {"answer": claim.text, "claims": [
            {"text": claim.text, "citations": claim.citations}]}, hits, conn=conn)
        assert any(g.startswith("Review required citation context") for g in gaps)
        claim.citations.append(f"C{parent}")
        after = check_answer(ans)
        assert after["supported_rate"] == 1
    packet = json.loads(Path("docs/review/practitioner-packets-2026-11-14.json").read_text())
    assert packet["status"] == "awaiting_independent_practitioner"
    assert packet["baseline_sha256"] == file_sha(baseline_path)
    for case in packet["cases"]:
        assert file_sha(Path(case["artifact"])) == case["artifact_sha256"]
        assert case["practitioner_decision"] is None
        assert all("body_sha256" in s for s in case["sources"])
    out = {"basis": "SQL/structural audit; no model calls or new answer-quality grades",
           "snapshot_file_sha256": file_sha(snapshot), "baseline_sha256": file_sha(baseline_path),
           "single_first_routes": len(routes), "policy_router_tokens": 0,
           "historical_router_tokens": baseline["tokens_by_purpose"]["route"],
           "amendment_context": {"delivered": [h.ref for h in hits], "before": before,
                                 "after": after, "guard": gaps},
           "practitioner_packets_verified": 2,
           "independent_practitioner_and_holdout": "pending external people; not fabricated",
           "live_paired_evaluation": "awaiting 3M-token budget approval"}
    path = Path("docs/review/remaining-handoff-local-2026-11-14.json")
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
