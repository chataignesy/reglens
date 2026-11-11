"""Repeated PDF list numbers must not receive credit for an unrelated section."""

from reglens.agent.tools import Row
from reglens.answer.pipeline import Answer, Claim
from reglens.eval.answers import citation_recall
from reglens.eval.citations import credit
from reglens.eval.golden import Citation, GoldenItem
from reglens.eval.retrieval import normalize_refs

SOURCE = "ecb-validation-reporting"


def test_same_paragraph_in_wrong_section_and_legacy_missing_hierarchy_get_zero():
    expected = Citation(SOURCE, "Section 2.4.2, para. 3")
    assert credit(expected, [(SOURCE, "Instructions", "para.3")]) == 0
    assert (
        credit(
            expected,
            [
                (
                    SOURCE,
                    "Instructions",
                    "para.3",
                    ["2.9 Credit conversion factor", "2.9.5 Qualitative validation tools"],
                )
            ],
        )
        == 0
    )
    assert credit(expected, [(SOURCE, "Instructions", "para.3", ["2.4.20 Different section"])]) == 0
    assert (
        credit(
            expected,
            [
                (
                    SOURCE,
                    "Instructions",
                    "para.3",
                    ["2.4 General information", "2.4.2 Validation information"],
                )
            ],
        )
        == 1
    )


def test_qualified_range_still_requires_all_members():
    expected = Citation(SOURCE, "Section 2.4.2, paras. 3-4")
    assert normalize_refs(expected.ref) == ["para.3", "para.4"]
    got = [(SOURCE, "Instructions", "para.3", ["2.4.2 Validation information"])]
    assert credit(expected, got) == 0.5
    got.append((SOURCE, "Instructions", "para.4", ["2.4.2 Validation information"]))
    assert credit(expected, got) == 1


def test_agent_answer_keeps_section_evidence_for_answer_level_scoring():
    row = Row(
        "id",
        SOURCE,
        "para. 3",
        "Instructions",
        "Major deficiency",
        "supervisory",
        "2019",
        "paragraph",
        None,
        "3",
        None,
        hierarchy=["2.4 General information", "2.4.2 Validation information"],
    )
    answer = Answer(
        "Q", False, "", "Major [C1]", [Claim("Major", ["C1"], "supervisory")], [row.hit()], ""
    )
    item = GoldenItem(
        "test",
        "Q",
        "factual",
        "Major",
        [Citation(SOURCE, "Section 2.4.2, para. 3")],
        "all",
        "validation",
        "easy",
        "test",
        "verified",
    )
    assert citation_recall(item, answer.to_dict()) == 1
    answer.context[0].hierarchy = ["2.9.5 Unrelated statistics"]
    assert citation_recall(item, answer.to_dict()) == 0
