import json
from dataclasses import replace

import pytest

import reglens.eval.judge as j
from reglens.config import load_config
from reglens.eval.answers import file_sha
from reglens.eval.golden import Citation, GoldenItem
from reglens.llm.ledger import Usage
from reglens.llm.provider import Completion

MODEL = load_config().model("bulk")


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
def run(tmp_path, monkeypatch):
    """A run manifest whose items point at answer artifacts written by `put`."""
    monkeypatch.setattr(j, "JUDGE_DIR", tmp_path / "judge")
    monkeypatch.setattr(j, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(j, "PROJECT_ROOT", tmp_path)
    (tmp_path / "runs").mkdir()
    manifest = {"run_id": "r1", "kind": "routed", "items": []}

    def put(id, abstained, answer="The floor is 0,05 % [C1].", route="single", **extra):
        path = tmp_path / "answers" / f"{id}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"abstained": abstained, "answer": answer} | extra), "utf-8")
        manifest["items"].append({"id": id, "route": route, "artifact": f"answers/{id}.json",
                                  "artifact_sha256": file_sha(path)})
        return path

    return manifest, put


def test_grades_exactly_the_run(run):
    manifest, put = run
    put("a", False, route="agent")
    put("b", True)  # in-scope abstention -> 0 without a call
    put("o", True)  # out-of-scope abstention -> 2 without a call
    put("u", False, answer="", unverified=True, errors=["invalid model output"])
    items = [item("a"), item("b"), item("o", "out_of_scope"), item("u"), item("missing")]
    p = j.plan(manifest, items, MODEL)
    assert p["needs_call"] == ["a"] and set(p["deterministic"]) == {"b", "o", "u"}
    assert p["problems"] == ["missing: not in run"]

    fake = FakeJudge('```json\n{"score": 2, "missing": [], "contradictions": [], '
                     '"rationale": "matches"}\n```')
    s = j.judge(fake, load_config(), manifest, items, log=lambda m: None)
    assert len(fake.calls) == 1
    prompt, kw = fake.calls[0]
    assert "Reference answer:\n0.05%" in prompt and kw["tier"] == "bulk"
    assert {r["id"]: r["score"] for r in s["per_item"]} == {"a": 2, "b": 0, "o": 2, "u": 0}
    assert {r["id"]: r["route"] for r in s["per_item"]}["a"] == "agent"
    assert s["run_id"] == "r1" and s["out_of_scope_declined"] == "1/1"

    fake2 = FakeJudge("{}")
    j.judge(fake2, load_config(), manifest, items, log=lambda m: None)
    assert fake2.calls == []  # same answers: verdicts reused


def test_changed_answer_or_reference_is_graded_again(run):
    manifest, put = run
    put("a", False)
    j.judge(FakeJudge('{"score": 1, "rationale": "x"}'), load_config(), manifest, [item("a")],
            log=lambda m: None)
    assert j.plan(manifest, [item("a")], MODEL)["cached"] == ["a"]
    reworded = replace(item("a"), expected_answer="0,05 % for corporates")
    assert j.plan(manifest, [reworded], MODEL)["needs_call"] == ["a"]

    manifest["items"].clear()
    put("a", False, answer="A regenerated answer [C1].")  # new run, new answer: new verdict
    assert j.plan(manifest, [item("a")], MODEL)["needs_call"] == ["a"]


def test_artifact_changed_after_the_run_is_not_graded(run):
    manifest, put = run
    path = put("a", False)
    path.write_text(json.dumps({"abstained": False, "answer": "edited later"}), "utf-8")
    assert j.plan(manifest, [item("a")], MODEL)["problems"] == [
        "a: answer artifact changed since the run"]


def test_bad_judge_output_not_cached(run):
    manifest, put = run
    put("a", False)
    s = j.judge(FakeJudge('{"score": 7}'), load_config(), manifest, [item("a")],
                log=lambda m: None)
    assert s["per_item"] == [] and j.plan(manifest, [item("a")], MODEL)["needs_call"] == ["a"]
