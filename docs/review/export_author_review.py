"""Verify and publish existing author-review decisions without creating new adjudications."""

import json
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.eval.answers import file_sha
from reglens.eval.artifacts import adjudications, digest

RECORDS = {
    "mh-006": "f0084f855058a422327746cb2fba9386e0dbe005f4cfc2ecc462560c0634c121",
    "mh-014": "0d645f414ee5ef5f7d9e78f9db21c988f922c0f5a90a24e44e4e68ab205632f3",
}


def main():
    baseline = PROJECT_ROOT / "docs/results/codex-frozen118-2026-11-14.json"
    original = {i["id"]: i for i in json.loads(baseline.read_text(encoding="utf-8"))["items"]}
    packet_path = PROJECT_ROOT / "docs/review/practitioner-packets-2026-11-14.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert file_sha(baseline) == packet["baseline_sha256"]
    reviews = adjudications()
    cases = []
    for case in packet["cases"]:
        cid, expected = case["id"], RECORDS[case["id"]]
        assert file_sha(Path(case["artifact"])) == case["artifact_sha256"]
        record = next(r for r in reviews[case["artifact_sha256"]] if digest(r) == expected)
        assert record["decision"] == "accepted"
        assert "Author review, NOT independent" in record["reviewer"]
        path = PROJECT_ROOT / "data/evals/adjudications" / f"{expected}.json"
        assert digest(json.loads(path.read_text(encoding="utf-8"))) == expected
        assert original[cid]["entry"]["artifact_sha256"] == record["artifact_sha256"]
        assert original[cid]["grade"]["score"] == {"mh-006": 1, "mh-014": 2}[cid]
        cases.append(
            {
                "id": cid,
                "record_id": expected,
                "record_file_sha256": file_sha(path),
                "original_automated_score": original[cid]["grade"]["score"],
                "adjudication": record,
            }
        )
    review = PROJECT_ROOT / "docs/review/AI-PRE-REVIEW-mh006-mh014-2026-11-15.md"
    result = {
        "status": "completed_author_practitioner_review",
        "review_type": (
            "project-author practitioner review with Claude assistance; stage 1 not blind"
        ),
        "independent_validation": False,
        "scope": "Two exact original baseline answer artifacts; not later paired-run answers",
        "source_review_commit": "246e8e98bd96744b613593ce90b091e925e9b273",
        "review_document_sha256": file_sha(review),
        "baseline_report_sha256": file_sha(baseline),
        "historical_scores_and_references_changed": False,
        "new_rubric_version_applied": False,
        "deferred_recommendations": [
            "In a future rubric version, make analogous own-LGD/CCF analysis optional for mh-006",
            "Optional source-edition metadata clarification for the historical ECB instructions",
        ],
        "holdout": "out of scope at the user's request",
        "cases": cases,
    }
    path = PROJECT_ROOT / "docs/review/author-practitioner-adjudications-2026-11-15.json"
    if path.exists():
        assert json.loads(path.read_text(encoding="utf-8")) == result
    else:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    print(f"Verified two accepted author-review decisions; unchanged raw scores 1 and 2. {path}")


if __name__ == "__main__":
    main()
