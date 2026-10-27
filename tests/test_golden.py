import json

import pytest

from reglens.eval.golden import load_golden

GOOD = {
    "id": "t-001",
    "question": "q?",
    "type": "factual",
    "expected_answer": "a",
    "expected_citations": [{"source": "crr3-consolidated", "ref": "Art. 178"}],
    "applies_to": "all",
    "topic": "definition-of-default",
    "difficulty": "easy",
    "author": "test",
    "status": "draft",
}


def write(tmp_path, *items):
    p = tmp_path / "set.jsonl"
    p.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    return [p]


def test_repo_golden_files_are_valid():
    assert len(load_golden()) >= 3


def test_valid_item(tmp_path):
    [item] = load_golden(write(tmp_path, GOOD))
    assert item.expected_citations[0].ref == "Art. 178"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"type": "guess"}, "type"),
        ({"expected_citations": [{"source": "nope", "ref": "x"}]}, "unknown source"),
        ({"expected_citations": []}, "at least one"),
        ({"type": "out_of_scope"}, "no expected_citations"),
        ({"applies_to": "everyone"}, "applies_to"),
    ],
)
def test_invalid_items(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        load_golden(write(tmp_path, {**GOOD, **change}))


def test_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="Duplicate"):
        load_golden(write(tmp_path, GOOD, GOOD))
