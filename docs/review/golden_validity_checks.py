"""Reproducible offline evidence inventory; does not decide semantic correctness."""

import hashlib
import json
from collections import Counter
from dataclasses import asdict

from reglens.config import PROJECT_ROOT
from reglens.eval.answers import citation_recall
from reglens.eval.citations import credit, in_section, part_of, section_of
from reglens.eval.golden import load_golden
from reglens.eval.retrieval import normalize_refs, refs_match
from reglens.eval.snapshots import question_key
from reglens.index import db
from reglens.index.generations import current

OUT = PROJECT_ROOT / "data/evals/golden-validity"


def scorer_probes(conn, items):
    by_id = {i.id: i for i in items}
    bad = next(
        r
        for r in conn.execute(
            "SELECT id,title,body FROM chunks WHERE source_id='ecb-validation-reporting' "
            "AND ref='para. 3' ORDER BY id"
        )
        if r[2].startswith("EAD -")
    )
    intro = conn.execute(
        "SELECT id,title,body FROM chunks WHERE "
        "source_id='crr3-consolidated' AND article='142' AND paragraph='1' "
        "AND point IS NULL ORDER BY id LIMIT 1"
    ).fetchone()
    record = {
        "claims": [{"citations": ["C1"]}],
        "context": [
            {"source_id": "crr3-consolidated", "ref": "Art. 183(1)", "title": "Requirements"}
        ],
    }
    return {
        "val004_unrelated_passage_credit": {
            "chunk_id": bad[0],
            "starts_with": bad[2][:70],
            "credit_for_grade_definition": credit(
                by_id["val-004"].expected_citations[0],
                [("ecb-validation-reporting", bad[1], "para.3")],
            ),
        },
        "scope001_intro_only_credit": {
            "chunk_id": intro[0],
            "text": intro[2],
            "credit_for_large_corporate_definition": credit(
                by_id["scope-001"].expected_citations[0],
                [("crr3-consolidated", intro[1], "art.142(1)")],
            ),
        },
        "mh023_missing_qa_credit": {
            "qa_normalized": normalize_refs("Q&A 2016_2593"),
            "only_article183_retrieved_citation_recall": citation_recall(by_id["mh-023"], record),
        },
        "cmp002_unscorable": not normalize_refs(by_id["cmp-002"].expected_citations[0].ref),
        "dod004_170_alternative_credit": credit(
            by_id["dod-004"].expected_citations[0],
            [("ecb-guide-internal-models", "Credit risk", "para.170")],
        ),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = load_golden()
    lock = json.loads((PROJECT_ROOT / "sources.lock.json").read_text())
    provenance = {}
    for key, entry in lock.items():
        path = PROJECT_ROOT / entry["file"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        provenance[key] = {
            "file": entry["file"],
            "official_url": entry["url"],
            "expected_sha256": entry["sha256"],
            "actual_sha256": actual,
            "matches_lock": actual == entry["sha256"],
        }
    inventory, problems = [], []
    with db.connect() as conn:
        metadata = conn.execute(
            "SELECT id,source_id,ref,title,source_sha256,kind,hierarchy FROM chunks"
        ).fetchall()
        generation = current(conn)
        probes = scorer_probes(conn, items)
        for item in items:
            evidence = []
            for cite in item.expected_citations:
                for alternative, c in enumerate((cite, *cite.alternatives)):
                    normalized = normalize_refs(c.ref)
                    part = part_of(c.ref)
                    section = section_of(c.ref)
                    matched = []
                    for row in metadata:
                        if row[1] != c.source or (part and (row[3] or "").lower() != part):
                            continue
                        if section and not in_section(section, row[6]):
                            continue
                        refs = normalize_refs(row[2])
                        exact = question_key(row[2]) == question_key(c.ref)
                        title = not normalized and c.ref.lower() == (row[3] or "").lower()
                        if (
                            exact
                            or title
                            or any(refs_match(a, b) for a in normalized for b in refs)
                        ):
                            matched.append(row)
                    ids = [r[0] for r in matched]
                    passages = (
                        conn.execute(
                            "SELECT id,ref,title,text FROM chunks WHERE id=ANY(%s) ORDER BY id",
                            (ids,),
                        ).fetchall()
                        if ids
                        else []
                    )
                    evidence.append(
                        {
                            "source": c.source,
                            "ref": c.ref,
                            "alternative": bool(alternative),
                            "evaluable_by_current_scorer": bool(normalized),
                            "passages": [
                                dict(zip(("id", "ref", "title", "text"), r, strict=True))
                                for r in passages
                            ],
                            "source_hash_matches_lock": all(
                                r[4] == lock[c.source]["sha256"] for r in matched
                            )
                            if c.source in lock and matched
                            else None,
                        }
                    )
                    if not matched or not normalized:
                        problems.append(
                            {
                                "id": item.id,
                                "source": c.source,
                                "ref": c.ref,
                                "matched": len(matched),
                                "evaluable": bool(normalized),
                            }
                        )
            packet = {"item": asdict(item), "evidence": evidence}
            (OUT / f"{item.id}.json").write_text(
                json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            inventory.append(
                {
                    "id": item.id,
                    "type": item.type,
                    "status": item.status,
                    "primary_citations": len(item.expected_citations),
                    "evidence_characters": sum(
                        len(p["text"]) for e in evidence for p in e["passages"]
                    ),
                }
            )
    report = {
        "generation": generation,
        "total": len(items),
        "statuses": dict(Counter(i.status for i in items)),
        "authors": dict(Counter(i.author for i in items)),
        "types": dict(Counter(i.type for i in items)),
        "duplicate_questions": [
            q for q, n in Counter(question_key(i.question) for i in items).items() if n > 1
        ],
        "input_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((PROJECT_ROOT / "evals/golden").glob("*.jsonl"))
        },
        "raw_source_provenance": provenance,
        "citation_problems": problems,
        "scorer_probes": probes,
        "items": inventory,
    }
    (OUT / "inventory.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"items", "raw_source_provenance"}},
            indent=2,
        )
    )
    print(
        "Raw hash checks:",
        sum(p["matches_lock"] for p in provenance.values()),
        "/",
        len(provenance),
    )


if __name__ == "__main__":
    main()
