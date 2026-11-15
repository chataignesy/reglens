import json
from dataclasses import replace

import pytest

from reglens.eval.artifacts import digest
from reglens.eval.golden import load_golden
from reglens.eval.snapshots import freeze, load, payload, run_items


def test_frozen_references_survive_reference_edits_and_detect_tampering(tmp_path):
    item = next(i for i in load_golden() if i.status == "verified")
    path = freeze([item], directory=tmp_path)
    data, items = load(path)
    assert items == [item]
    manifest = {"dataset": {"sha256": digest(data), "snapshot": data}}
    changed = replace(item, expected_answer="New reference after the run")
    assert run_items(manifest, [changed])[0].expected_answer == item.expected_answer
    data["items"][0]["expected_answer"] = "tampered"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="hash"):
        load(path)
    with pytest.raises(ValueError, match="changed"):
        run_items(manifest)


def test_snapshot_alternatives_roundtrip_and_repeat_freeze_without_false_tamper(tmp_path):
    item = next(
        i
        for i in load_golden()
        if i.status == "verified" and any(c.alternatives for c in i.expected_citations)
    )
    path = freeze([item], directory=tmp_path)
    before = path.read_bytes()
    assert load(path)[1] == [item]
    assert freeze([item], directory=tmp_path) == path
    assert path.read_bytes() == before


def test_future_holdouts_reject_development_and_historical_questions(tmp_path):
    item = next(i for i in load_golden() if i.status == "verified")
    with pytest.raises(ValueError, match="already used"):
        freeze([item], role="holdout", directory=tmp_path, development=[item], history=tmp_path)
    future = replace(item, id="future-1", question="A new practitioner question, not used before?")
    path = freeze(
        [future],
        role="holdout",
        directory=tmp_path / "frozen",
        development=[item],
        history=tmp_path / "history",
    )
    assert load(path)[0]["role"] == "holdout"
    history = tmp_path / "history"
    history.mkdir()
    (history / "answer.json").write_text(json.dumps({"question": future.question.upper()}))
    with pytest.raises(ValueError, match="already used"):
        freeze(
            [future],
            role="holdout",
            directory=tmp_path / "other",
            development=[item],
            history=history,
        )
    with pytest.raises(ValueError, match="Duplicate normalized"):
        payload([future, replace(future, id="future-2")])
