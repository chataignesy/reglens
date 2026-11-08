import json

import pytest

from reglens.gap import match as m
from reglens.gap.evaluate import evaluate
from reglens.gap.gaps import Gap, load_gaps
from reglens.gap.policy import parse_policy
from reglens.gap.register import Obligation

POLICY = """# Demo policy

## 15. Internal audit

15.1 Internal Audit reviews the Model Validation team every three years
as part of the audit plan.

## Annex — tests

| Parameter | Test | Green |
|---|---|---|
| PD | AUC | ≥ 0.7 |
"""


def ob(i, key="CRR Art. 191", relevant=True, topic="internal-audit"):
    return Obligation(i, key, "crr3-consolidated", key[4:], "c", "L1", "all", "internal audit",
                      f"Obligation {i}.", "q", True, topic, "shall", relevant)


def test_policy_clauses_join_wrapped_lines_and_annex_rows():
    clauses = parse_policy(POLICY)
    assert [c.id for c in clauses] == ["§15.1", "Annex 1"]
    assert clauses[0].text.endswith("every three years as part of the audit plan.")
    assert clauses[0].section == "15. Internal audit"
    assert clauses[1].text == "PD | AUC | ≥ 0.7"


def test_parse_verdicts_checks_quotes_and_reports_skipped():
    clauses = parse_policy(POLICY)
    batch = [ob("OB-1"), ob("OB-2"), ob("OB-3")]
    reply = json.dumps({"verdicts": [
        {"id": "OB-1", "status": "contradicted", "clauses": ["§15.1"],
         "quote": "reviews the Model Validation team every three years", "rationale": "3y > 1y"},
        {"id": "OB-2", "status": "covered", "clauses": ["§15.1", "§99"],
         "quote": "audits everything monthly", "rationale": "invented quote"},
    ]})
    v1, v2, v3 = m.parse_verdicts(batch, reply, clauses)
    assert v1.status == "contradicted" and v1.quote_ok and v1.clauses == ["§15.1"]
    assert v2.clauses == ["§15.1"] and not v2.quote_ok  # unknown clause dropped, quote not found
    assert v3.status == "unassessed"  # skipped obligations are reported, not assumed covered


def test_batches_group_relevant_obligations_by_topic():
    obs = [ob("OB-1"), ob("OB-2", topic="pd"), ob("OB-3"), ob("OB-4", relevant=False)]
    assert [[o.id for o in b] for b in m.batches(obs, size=1)] == [["OB-1"], ["OB-3"], ["OB-2"]]


def test_evaluate_recall_type_accuracy_and_other_findings():
    gaps = [Gap("G1", "contradicted", "15", "audit", ["CRR Art. 191"], ["OB-1"]),
            Gap("G2", "missing", "9", "floors", ["CRR Art. 164(4)"], ["OB-2", "OB-3"])]
    verdicts = [m.Verdict("OB-1", "contradicted", ["§15.1"], "", True, ""),
                m.Verdict("OB-2", "covered", [], "", True, ""),
                m.Verdict("OB-3", "partial", [], "", True, ""),
                m.Verdict("OB-4", "missing", [], "", True, ""),
                m.Verdict("OB-5", "other_document", [], "", True, "")]
    s = evaluate(gaps, verdicts)
    assert s["recall"] == 1.0 and s["type_accuracy"] == 0.5
    assert s["by_type"]["contradicted"] == "1/1" and s["other_findings"] == 1


def test_gap_links_must_exist_under_refs(tmp_path):
    path = tmp_path / "gaps.yaml"
    path.write_text('- {id: G1, type: missing, section: "15", finding: x, '
                    'refs: ["CRR Art. 191"], obligations: [OB-9]}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="OB-9"):
        load_gaps([ob("OB-1")], path)
    path.write_text('- {id: G1, type: missing, section: "15", finding: x, '
                    'refs: ["CRR Art. 191"]}\n', encoding="utf-8")
    assert load_gaps([ob("OB-1"), ob("OB-2", relevant=False)], path)[0].obligations == ["OB-1"]


# review 2026-11-08: F6 (conservative verdicts), F9 (recall over all gaps)


def test_verdicts_without_evidence_or_with_invalid_status_are_unassessed():
    clauses = parse_policy(POLICY)
    batch = [ob("OB-1"), ob("OB-2"), ob("OB-3"), ob("OB-4"), ob("OB-5")]
    reply = json.dumps({"verdicts": [
        {"id": "OB-1", "status": "covered"},  # no clause, no quote
        {"id": "OB-2", "status": "partial", "clauses": ["§99"], "quote": "x"},  # unknown clause
        {"id": "OB-3", "status": "covered", "clauses": ["§15.1"], "quote": ""},  # no quote
        {"id": "OB-4", "status": "mostly fine", "clauses": ["§15.1"]},  # invented status
        {"id": "OB-5", "status": "missing", "rationale": "not addressed"},  # needs no evidence
    ]})
    v = {x.obligation_id: x for x in m.parse_verdicts(batch, reply, clauses)}
    for oid in ("OB-1", "OB-2", "OB-3", "OB-4"):
        assert v[oid].status == "unassessed" and v[oid].evidence == "invalid", oid
        assert v[oid].rationale.startswith("invalid output")
    assert "§99" in v["OB-2"].rationale
    assert v["OB-5"].status == "missing" and v["OB-5"].evidence == "none_required"


def test_rescore_applies_current_rules_to_a_saved_run():
    clauses = parse_policy(POLICY)
    rows = [
        {"obligation_id": "OB-1", "status": "covered", "clauses": [], "quote": "",
         "rationale": "old lenient verdict"},
        {"obligation_id": "OB-2", "status": "contradicted", "clauses": ["§15.1"],
         "quote": "every three years", "rationale": "3y"},
    ]
    v1, v2 = m.rescore(rows, clauses)
    assert v1.status == "unassessed" and v2.status == "contradicted" and v2.evidence == "verified"


def test_recall_counts_unassessed_gaps_as_not_found():
    gaps = [Gap("G1", "contradicted", "15", "audit", ["CRR Art. 191"], ["OB-1"]),
            Gap("G2", "missing", "9", "floors", ["CRR Art. 164(4)"], ["OB-2"])]
    partial_run = [m.Verdict("OB-1", "contradicted", ["§15.1"], "q", True, "")]  # G2 not run
    s = evaluate(gaps, partial_run)
    assert s["recall"] == 0.5 and s["recall_of_assessed"] == 1.0
    assert s["complete"] is False and s["gaps_assessed"] == 1
    assert s["by_type"]["missing"] == "0/1"
