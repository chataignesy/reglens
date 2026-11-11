from dataclasses import replace

from reglens.gap.match import select_clauses
from reglens.gap.policy import Clause
from reglens.gap.register import Obligation, assign_ids, id_lookup


def obligation(id="OB-0001", text="The institution shall validate annually."):
    return Obligation(
        id,
        "CRR Art. 185",
        "crr3-consolidated",
        "Art. 185",
        "c1",
        "L1",
        "all",
        "institution",
        text,
        "validate annually",
        True,
        "validation",
        "shall",
    )


def test_ids_survive_insertion_reordering_and_quote_correction():
    a, b = obligation(), obligation("OB-0002", "The institution shall document deviations.")
    assign_ids([a, b])
    ids = a.id, b.id
    b.quote = "a different verified quotation"
    inserted = obligation("", "A new requirement")
    assign_ids([inserted, b, a])
    assert (a.id, b.id) == ids
    assert id_lookup([a, b])["OB-0001"] is a
    changed = replace(a, obligation="The institution shall validate monthly.")
    assign_ids([changed])
    assert changed.id != a.id


def test_long_policy_selection_is_bounded_and_does_not_claim_full_coverage():
    clauses = [
        Clause(f"§{i}", "scope" if i == 0 else "model validation", "validation " * 100)
        for i in range(100)
    ]
    selected, complete = select_clauses([obligation()], clauses, max_chars=5000)
    assert not complete and sum(len(c.render()) + 1 for c in selected) <= 5000
    assert clauses[0] in selected
    assert select_clauses([obligation()], clauses[:2], max_chars=5000) == (clauses[:2], True)
