"""Post-rerun regressions: reliability, history integrity, scope and dependency coverage."""

import json
from dataclasses import replace

import pytest

import reglens.agent.run as agent
import reglens.agent.tools as tools
import reglens.eval.answers as ea
from reglens.answer.pipeline import Answer, answer_question
from reglens.answer.research import article_provisos, expand_provisos, guard
from reglens.answer.route import dispatch, gate_abstains
from reglens.answer.schema import parse_reply
from reglens.answer.scope import refusal_reason
from reglens.config import load_config
from reglens.eval.answer_cache import cached, save
from reglens.eval.golden import Citation, GoldenItem
from reglens.llm.provider import LLMError
from reglens.retrieve.search import Hit


@pytest.mark.parametrize("as_dict", [False, True])
@pytest.mark.parametrize("text,unverified", [("", False), (" \n", False), ("bad", True)])
def test_unusable_answers_fall_back_even_without_errors(as_dict, text, unverified):
    bad = Answer("q", False, "", text, [], [], "", usage_tokens=91_497, unverified=unverified)
    good = Answer("q", False, "", "usable", [], [], "", usage_tokens=20)
    if as_dict:
        bad, good = bad.to_dict(), good.to_dict()
    final, outcome = dispatch("agent", "chain", 2, agent=lambda: bad, single=lambda: good)
    assert final is good
    assert outcome["tokens"] == 91_519 and outcome["attempts"] == ["agent", "single"]
    assert outcome["attempt_errors"]


def test_service_retry_preserves_legacy_artifact_and_all_attempts(tmp_path):
    index = tmp_path / "q.json"
    original = b'{"answer":"","errors":["session limit reached"],"usage_unknown_calls":1}'
    index.write_bytes(original)
    assert cached(index) is None
    outage = {"answer": "", "errors": ["timeout"], "retryable_error": True}
    outage_path = save(index, outage)
    assert cached(index) is None and outage_path.exists()
    success = {"answer": "fixed", "errors": [], "usage_tokens": 20}
    path = save(index, success)
    assert index.read_bytes() == original
    assert cached(index) == (success, path)
    assert json.loads(outage_path.read_bytes()) == outage
    # Genuine evidence/model failures must not be selectively resampled.
    failure = {"answer": "", "errors": ["cost cap"], "retryable_error": False}
    failed_path = save(index, failure)
    assert cached(index) == (failure, failed_path)
    assert path.exists() and json.loads(path.read_bytes()) == success
    failed_path.write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        cached(index)


@pytest.mark.parametrize("planned", ["single", "agent"])
def test_provider_outage_does_not_start_another_strategy(planned):
    outage = Answer("q", False, "", "", [], [], "", errors=["session limit"],
                    retryable_error=True, usage_unknown_calls=1)
    calls = []

    def attempt(mode):
        calls.append(mode)
        return outage

    final, outcome = dispatch(planned, "plan", 0, agent=lambda: attempt("agent"),
                              single=lambda: attempt("single"))
    assert final is outage and calls == [planned]
    assert outcome["usage_unknown_calls"] == 1


def test_eval_retry_and_metrics_keep_original_manifest_verifiable(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ea, "ANSWER_DIR", tmp_path / "answers")
    monkeypatch.setattr(ea, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(ea, "answer_version", lambda *a: "single-test")
    item = GoldenItem("q", "q?", "factual", "a", [Citation("crr3-consolidated", "Art. 1")],
                      "all", "t", "easy", "me", "verified")
    calls = []

    def answer(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise LLMError("timeout", tokens=100, usage_known=False, retryable=True)
        return Answer("q", False, "", "usable", [], [], "", usage_tokens=20)

    monkeypatch.setattr(ea, "answer_question", answer)
    first = ea.run(None, None, load_config(), [item], log=lambda _: None)
    assert first["answered_in_scope"] == 0 and first["scope_compliance"] == 0
    assert first["new_tokens_this_run"] == 100 and first["new_usage_unknown_calls"] == 1
    manifest_path = tmp_path / first["file"]
    original = manifest_path.read_bytes()
    entry = json.loads(original)["items"][0]
    old_answer = tmp_path / entry["artifact"]
    old_hash = ea.file_sha(old_answer)
    dirs = {"single": tmp_path / "answers" / "single-test"}
    assert ea.required_calls([item], dirs) == [("q", "single")]
    second = ea.run(None, None, load_config(), [item], log=lambda _: None)
    assert second["answered_in_scope"] == 1 and second["new_tokens_this_run"] == 20
    assert manifest_path.read_bytes() == original and ea.file_sha(old_answer) == old_hash
    third = ea.run(None, None, load_config(), [item], log=lambda _: None)
    assert len(calls) == 2 and third["new_tokens_this_run"] == 0


@pytest.mark.parametrize("mode", ["single", "agent", "routed"])
def test_excluded_calculation_refuses_before_search_or_model(monkeypatch, mode):
    def unexpected(*a, **k):
        pytest.fail("Excluded calculation must not start retrieval or a model call")

    monkeypatch.setattr("reglens.answer.pipeline.search", unexpected)
    monkeypatch.setattr(agent, "search", unexpected)
    monkeypatch.setattr("reglens.answer.route.search", unexpected)
    question = "How is the risk weight of a senior securitisation tranche calculated under SEC-IRBA?"
    if mode == "routed":
        assert gate_abstains(None, load_config(), question)
        from reglens.answer.route import answer_routed

        ans = answer_routed(None, None, load_config(), question)
    else:
        fn = agent.answer_agentic if mode == "agent" else answer_question
        ans = fn(None, None, load_config(), question)
    assert ans.abstained and not ans.answer and not ans.claims and ans.usage_tokens == 0
    assert refusal_reason("Does the CRR output floor include SEC-IRBA risk weights?") is None


def test_structured_gap_is_detected_without_matching_prose():
    data = {
        "abstain": False, "answer": "Only part of the outcome is established.",
        "missing_info": False, "research_needed": False, "missing_requirements": [],
        "answer_requirements": [
            {"requirement": "Treatment of the covered portion", "status": "unresolved",
             "citations": [], "retrievable": True},
        ],
    }
    assert guard("Do input floors apply to the covered and uncovered portions?", data, [])
    assert data["missing_info"] and data["research_needed"]
    assert "Treatment of the covered portion" in data["missing_requirements"]
    assert all("optional" not in r for r in data["missing_requirements"])


def test_malformed_answer_requirements_rejected():
    data = {"abstain": True, "answer_requirements": [{"status": "supported"}]}
    assert parse_reply(json.dumps(data))[1]


def test_explicit_cross_article_dependency_uses_same_source_only():
    hit = Hit("h", "s", "Art. 10(1)", "", "Subject to Article 12(2).", "L1", None, 1)
    assert article_provisos(hit) == [("12", "2")]
    data = {"answer": "Applies [C1]", "claims": [{"citations": ["C1"]}]}
    assert guard("Does it apply?", data, [hit])
    external = replace(hit, text="Subject to Article 12(2) of Regulation (EU) 999/2000.")
    assert article_provisos(external) == []


def test_reverse_exception_expansion_preserves_full_units_filters_and_bounds(monkeypatch):
    base = Hit("h", "crr3-consolidated", "Art. 164(4)", "", "General floor", "L1", None, 1)
    exemption = tools.Row("ex", base.source_id, "Art. 159a", "", "floors shall not apply",
                          "L1", None, "article", "159a", None, None)
    from reglens.retrieve.search import Filters

    filters = Filters(applies_to="LSI")
    queries, seen = [], []

    def rows(conn, where, params, **kwargs):
        queries.append((where, params))
        return [exemption]

    def eligible(self, rows):
        seen.append(self.filters)
        return rows

    monkeypatch.setattr(tools, "_rows", rows)
    monkeypatch.setattr(tools.Toolbox, "_eligible", eligible)
    monkeypatch.setattr(tools, "resolve_key", lambda *a: [exemption])
    out = expand_provisos(object(), [base], filters, max_extra=1)
    assert [h.id for h in out] == ["h", "ex"]
    assert any("e.target_article = ANY" in q for q, _ in queries)
    assert all(f == filters for f in seen)
    assert expand_provisos(object(), [base], filters, max_extra=0) == [base]


def test_blank_agent_completion_is_marked_unverified(monkeypatch):
    from test_frozen118_review import RepairCLI

    from reglens.llm.ledger import Usage
    from reglens.llm.provider import Completion

    monkeypatch.setattr(agent, "search", lambda *a, **k: [
        Hit("h", "s", "Art. 1", "", "Rule", "L1", None, 1),
    ])
    monkeypatch.setattr(agent, "_run_once", lambda *a, **k: (
        Completion(" \n", "test", Usage(10, 2)), [{"tool": "search", "keys": []}],
    ))
    ans = agent.answer_agentic(None, RepairCLI(""), load_config(), "Question?")
    assert ans.unverified and ans.errors == ["agent returned empty answer text"]
    assert ans.usage_tokens == 12
