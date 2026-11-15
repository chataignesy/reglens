"""Prepare source/artifact-bound review requests without issuing practitioner decisions."""

import hashlib
import json

from reglens.config import PROJECT_ROOT
from reglens.eval.answers import file_sha
from reglens.index.db import connect


def main():
    baseline = PROJECT_ROOT / "docs/results/codex-frozen118-2026-11-14.json"
    items = {i["id"]: i for i in json.loads(baseline.read_text(encoding="utf-8"))["items"]}
    questions = {
        "mh-006": {
            "issue": "Whether the analogous own-LGD/CCF analysis clause is mandatory for this "
                     "question specifically asking for PD back-testing and historical submission.",
            "proposed_for_review": "Treat the own-LGD/CCF clause as optional context unless "
                                  "the practitioner finds it indispensable to the actual question. "
                                  "Legal truth and answer-scope necessity are distinct.",
            "alternatives": ["Keep it mandatory and explain why it is necessary to the PD question",
                             "Make it optional in a separately versioned future rubric"],
            "source_ids": ["crr3-consolidated:article:185::(b)",
                           "ecb-validation-reporting:section:b0:Section 2.2:"],
        },
        "mh-014": {
            "issue": "Whether the supplied eligible-guarantee assumption, covered/uncovered split "
                     "and PD/LGD scope are sufficient; whether CCF discussion is unasked.",
            "proposed_for_review": "The completed Codex baseline already gives full credit. "
                                  "Retain that raw verdict; check whether future rubrics should "
                                  "label CCF background optional for this PD/LGD question.",
            "alternatives": ["Accept the answer within its supplied eligibility assumption",
                             "Identify a specific unsupported qualification with source evidence"],
            "source_ids": ["crr3-consolidated:article:159a::",
                           "crr3-consolidated:article:163:1:",
                           "crr3-consolidated:article:164:4:"],
        },
    }
    packet = {"status": "awaiting_independent_practitioner", "reviewer": None,
              "prepared_by": "Codex; automated preparation, not practitioner adjudication",
              "baseline_sha256": file_sha(baseline), "cases": []}
    with connect() as conn:
        for cid, review in questions.items():
            item = items[cid]
            artifact = PROJECT_ROOT / item["entry"]["artifact"]
            assert file_sha(artifact) == item["entry"]["artifact_sha256"]
            sources = []
            for chunk_id in review.pop("source_ids"):
                row = conn.execute(
                    "SELECT id,cite,body,source_sha256,version FROM chunks WHERE id=%s", [chunk_id]
                ).fetchone()
                if row:
                    sources.append({"chunk_id": row[0], "citation": row[1],
                                    "body_sha256": hashlib.sha256(row[2].encode()).hexdigest(),
                                    "source_sha256": row[3], "version": row[4]})
                else:
                    sources.append({"chunk_id": chunk_id,
                                    "status": "resolve reference before review"})
            packet["cases"].append({
                "id": cid, "question": item["question"], "frozen_reference": item["reference"],
                "grading_notes": item["grading_notes"], "answer": item["answer"],
                "raw_grade": item["grade"], "artifact": str(artifact),
                "artifact_sha256": file_sha(artifact), "sources": sources, **review,
                "practitioner_decision": None, "practitioner_reason": None,
                "decision_options": ["accepted", "rejected", "needs_evidence"],
            })
    path = PROJECT_ROOT / "docs/review/practitioner-packets-2026-11-14.json"
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if any(c.get("practitioner_decision") is not None for c in previous["cases"]):
            raise ValueError("Do not overwrite a practitioner decision")
    with path.open("w", encoding="utf-8") as stream:
        json.dump(packet, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(path)


if __name__ == "__main__":
    main()
