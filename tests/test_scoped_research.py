import json

import pytest

from reglens.agent.api_loop import _completeness_note
from reglens.answer.pipeline import Answer
from reglens.answer.research import completion_note
from reglens.answer.route import dispatch
from reglens.answer.schema import parse_reply


def reply(**extra):
    return {
        "answer": "The specified guide removed CCF estimation [C1].",
        "abstain": False,
        "missing_info": False,
        "research_needed": False,
        "missing_requirements": [],
        "claims": [{"text": "CCF content removed", "kind": "supervisory", "citations": ["C1"]}],
        **extra,
    }


def test_optional_checklist_uncertainty_does_not_trigger_api_completion():
    data = reply(
        research_checks=[
            {
                "aspect": "temporal",
                "status": "unresolved",
                "reason": "Current legal intervals not annotated",
            }
        ]
    )
    assert _completeness_note(json.dumps(data), []) is None
    assert completion_note(data) is None


@pytest.mark.parametrize("as_record", [False, True])
def test_unresolvable_required_gap_remains_visible_without_agent_cost(as_record):
    answer = Answer(
        "Current applicability?",
        False,
        "",
        "Cannot establish current status",
        [],
        [],
        "",
        missing_info=True,
        research_needed=False,
        missing_requirements=["Verified legal intervals are not in this corpus"],
    )
    candidate = answer.to_dict() if as_record else answer
    calls = []
    final, outcome = dispatch(
        "single",
        "one lookup",
        0,
        single=lambda: candidate,
        agent=lambda: calls.append("unexpected"),
    )
    assert final is candidate and not calls
    assert outcome["attempts"] == ["single"]
    assert (final["missing_info"] if as_record else final.missing_info) is True


def test_real_required_date_gap_still_requests_targeted_research():
    data = reply(
        missing_info=True,
        research_needed=True,
        missing_requirements=["Find the transition that applies on the requested date"],
    )
    assert "requested date" in _completeness_note(json.dumps(data), [])
    full = {"answer": "Transition found", "usage_tokens": 10}
    final, outcome = dispatch("single", "lookup", 0, single=lambda: data, agent=lambda: full)
    assert final is full and outcome["attempts"] == ["single", "agent"]


def test_partial_cited_text_still_requires_a_full_read():
    data = reply()
    trace = [{"keys": ["C1"], "truncated": ["C1"]}]
    assert "Read them in full" in _completeness_note(json.dumps(data), trace)


@pytest.mark.parametrize(
    "changes",
    [
        {"research_needed": True},
        {"research_needed": "yes"},
        {"missing_info": True},
        {"missing_requirements": ["Unanswered rule"]},
        {"missing_info": True, "missing_requirements": [""]},
    ],
)
def test_inconsistent_gap_contract_is_rejected(changes):
    _, problems = parse_reply(json.dumps(reply(**changes)))
    assert problems
