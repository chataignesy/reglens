"""Neutral references stay discoverable without automatically creating answer gaps."""

import pytest

from reglens.answer.research import article_provisos, guard
from reglens.answer.route import dispatch
from reglens.retrieve.search import Hit


def hit(text):
    return Hit("h", "crr3-consolidated", "Art. 164(4a)", "", text, "L1", None, 1)


def complete():
    return {
        "answer": "The floor is 5% [C1].",
        "claims": [{"citations": ["C1"]}],
        "missing_info": False,
        "research_needed": False,
        "missing_requirements": [],
    }


def test_neutral_reference_is_discoverable_but_does_not_force_agent_cost():
    h = hit("Calculate values in accordance with Article 230.")
    assert article_provisos(h) == [("230", None)]
    data = complete()
    assert guard("What input floor applies?", data, [h]) == []
    result, out = dispatch(
        "single",
        "one rule",
        0,
        single=lambda: data,
        agent=lambda: pytest.fail("Unasked background must not escalate"),
    )
    assert result is data and out["attempts"] == ["single"]


@pytest.mark.parametrize(
    "relation", ["Subject to", "Without prejudice to", "By way of derogation from"]
)
def test_qualifying_provision_still_requires_reading(relation):
    h = hit(f"{relation} Article 230(2), the floor applies.")
    data = complete()
    assert guard("Does the floor apply?", data, [h])
    assert data["research_needed"] and "230(2)" in data["missing_requirements"][0]


def test_a_required_calculation_gap_still_escalates_with_neutral_reference():
    data = complete() | {
        "missing_info": True,
        "research_needed": True,
        "missing_requirements": ["Find the valuation formula needed to calculate it"],
    }
    guard("Calculate the collateral value", data, [hit("In accordance with Article 230.")])
    calls = []
    _, out = dispatch(
        "single",
        "lookup",
        0,
        single=lambda: data,
        agent=lambda: calls.append(1) or {"answer": "Formula found"},
    )
    assert calls == [1] and out["attempts"] == ["single", "agent"]
