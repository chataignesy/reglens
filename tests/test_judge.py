import json

import pytest

import reglens.eval.judge as j
from reglens.config import load_config
from reglens.eval.golden import Citation, GoldenItem
from reglens.llm.ledger import Usage
from reglens.llm.provider import Completion


def item(id, type="factual"):
    cites = [] if type == "out_of_scope" else [Citation("crr3-consolidated", "Art. 160(1)")]
    return GoldenItem(id, "What is the PD floor?", type, "0.05%", cites, "all", "t", "easy", "me",
                      "verified")


class FakeJudge:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete(self, prompt, **kw):
        self.calls.append((prompt, kw))
        return Completion(self.reply, "claude-haiku-5-5", Usage(800, 120))


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    answers = tmp_path / "answers"
    (answers / j.PROMPT_VERSION).mkdir(parents=True)
    monkeypatch.setattr(j, "ANSWER_DIR", answers)
    monkeypatch.setattr(j, "JUDGE_DIR", tmp_path / "judge")
    monkeypatch.setattr(j, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data" / "evals").mkdir(parents=True)

    def put(id, abstained, answer="The floor is 0,05 % [C1]."):
        (answers / j.PROMPT_VERSION / f"{id}.json").write_text(
            json.dumps({"abstained": abstained, "answer": answer}), encoding="utf-8")
    return put


def test_plan_and_judge(dirs):
    dirs("a", False)
    dirs("b", True)          # in-scope abstention -> 0 without a call
    dirs("o", True)          # out-of-scope abstention -> 2 without a call
    items = [item("a"), item("b"), item("o", "out_of_scope"), item("missing")]
    p = j.plan(items)
    assert p["needs_call"] == ["a"] and set(p["deterministic"]) == {"b", "o"}
    assert p["no_answer"] == ["missing"]

    fake = FakeJudge('```json\n{"score": 2, "missing": [], "contradictions": [], '
                     '"rationale": "matches"}\n```')
    s = j.judge(fake, load_config(), items, log=lambda m: None)
    assert len(fake.calls) == 1
    prompt, kw = fake.calls[0]
    assert "Reference answer:\n0.05%" in prompt and kw["tier"] == "bulk"
    scores = {r["id"]: r["score"] for r in s["per_item"]}
    assert scores == {"a": 2, "b": 0, "o": 2}
    assert s["correctness_in_scope"] == 0.5  # (2 + 0) / (2 * 2)

    fake2 = FakeJudge("{}")
    j.judge(fake2, load_config(), items, log=lambda m: None)
    assert fake2.calls == []  # everything cached now


def test_changed_reference_invalidates_verdict(dirs):
    from dataclasses import replace

    dirs("a", False)
    fake = FakeJudge('{"score": 1, "missing": [], "contradictions": [], "rationale": "x"}')
    j.judge(fake, load_config(), [item("a")], log=lambda m: None)
    assert j.plan([item("a")])["cached"] == ["a"]
    reworded = replace(item("a"), expected_answer="0,05 % for corporates")
    assert j.plan([reworded])["needs_call"] == ["a"]


def test_bad_judge_output_not_cached(dirs):
    dirs("a", False)
    fake = FakeJudge('{"score": 7}')
    s = j.judge(fake, load_config(), [item("a")], log=lambda m: None)
    assert s["per_item"] == [] and j.plan([item("a")])["needs_call"] == ["a"]
