"""Regressions from the complete frozen-118 run; no external model calls."""

import json
from dataclasses import replace

import pytest

import reglens.agent.run as agent
import reglens.agent.tools as tools
import reglens.eval.judge as judge
from reglens.answer.pipeline import Answer, render
from reglens.answer.research import expand_provisos, guard
from reglens.answer.route import dispatch
from reglens.config import load_config
from reglens.eval.answers import artifact_name, required_calls
from reglens.eval.golden import Citation, GoldenItem
from reglens.llm.ledger import Usage
from reglens.llm.provider import ClaudeCLIProvider, Completion
from reglens.retrieve.search import Filters, Hit


def hit(ref, text, id="one"):
    return Hit(id, "crr3-consolidated", ref, "Maturity", text, "L1", None, 0.9)


def reply(text="No [C1]."):
    return {
        "abstain": False,
        "answer": text,
        "missing_info": False,
        "research_needed": False,
        "missing_requirements": [],
        "claims": [{"text": "No", "kind": "law", "citations": ["C1"]}],
    }


def test_unread_explicit_proviso_overrides_complete_flags_and_escalates():
    data = reply()
    hits = [hit("Art. 162(2)", "M must be calculated, subject to paragraphs 3, 4 and 5.")]
    assert guard("May this EU corporate set M at 2.5 years?", data, hits)
    calls = []
    final, outcome = dispatch(
        "single",
        "lookup",
        0,
        single=lambda: data,
        agent=lambda: calls.append(1) or {"answer": "Exception checked"},
    )
    assert calls == [1] and outcome["attempts"] == ["single", "agent"]
    assert final["answer"] == "Exception checked"


def test_read_provisos_do_not_force_more_research():
    data = reply()
    hits = [
        hit("Art. 162(2)", "subject to paragraph 4"),
        hit("Art. 162(4)", "EU non-large corporates may use the fixed maturity", "four"),
    ]
    assert guard("May it use a fixed M?", data, hits) == []


def test_missing_calculation_component_cannot_claim_complete():
    data = reply("Economic loss includes costs [C1].\nNot covered: the discount rate.")
    assert guard("Which elements enter economic loss when computing realised LGD?", data, [])
    assert data["missing_info"] and data["research_needed"]


@pytest.mark.parametrize(
    "question,text",
    [
        ("What does the guide foreword say?", "Not covered: a wider legal investigation."),
        (
            "Is EUR 80 below the EUR 100 absolute threshold?",
            "Not covered: the denominator. It is not needed for the conclusion.",
        ),
        ("What does this provision require?", "Not covered: date metadata for this version."),
    ],
)
def test_optional_information_does_not_restart_research(question, text):
    data = reply(text)
    assert not guard(question, data, []) and not data["missing_info"]


def test_proviso_expansion_is_bounded_and_preserves_filters(monkeypatch):
    seen = []
    row = tools.Row(
        "four",
        "crr3-consolidated",
        "Art. 162(4)",
        "Maturity",
        "Exception",
        "L1",
        None,
        "article",
        "162",
        "4",
        None,
    )
    monkeypatch.setattr(tools, "_rows", lambda *a, **k: [row])

    def eligible(self, rows):
        seen.append(self.filters)
        return rows

    monkeypatch.setattr(tools.Toolbox, "_eligible", eligible)
    filters = Filters(as_of="2026-01-01", require_known_validity=True, applies_to="LSI")
    hits = [hit("Art. 162(2)", "subject to paragraphs 3, 4 and 5")]
    out = expand_provisos(object(), hits, filters, max_extra=1)
    assert len(out) == 2 and out[1].ref == "Art. 162(4)" and seen == [filters]


def test_an_explicit_date_question_keeps_its_required_date_gap():
    data = reply("Not covered: the version application date.")
    assert guard("What rule applies as of 2026-01-01?", data, [])


def test_fallback_passes_required_gaps_to_the_researcher():
    first = reply("Partly answered") | {
        "missing_info": True,
        "research_needed": True,
        "missing_requirements": ["Find the discount rate"],
    }
    seen = []
    _, outcome = dispatch(
        "single",
        "lookup",
        0,
        single=lambda: first,
        agent=lambda: pytest.fail("must use targeted completion"),
        complete=lambda previous: (
            seen.append(previous["missing_requirements"])
            or {"answer": "The discount rate is supported"}
        ),
    )
    assert seen == [["Find the discount rate"]] and outcome["attempts"] == ["single", "agent"]


def test_definition_delivers_all_windows_of_its_qualifier(monkeypatch):
    definition = tools.Row(
        "d",
        "crr3-consolidated",
        "Art. 142(1)(5a)",
        "IRB",
        "large corporate means sales above EUR 500 million",
        "L1",
        None,
        "article",
        "142",
        "1",
        "(5a)",
    )
    qualifier = tools.Row(
        "q1",
        "crr3-consolidated",
        "Art. 142(1)",
        "IRB",
        "For point (5a), sales are measured on a consolidated basis.",
        "L1",
        None,
        "article",
        "142",
        "1",
        None,
    )
    intro = replace(qualifier, id="q0", text="For the purposes of this chapter ...")
    monkeypatch.setattr(
        tools,
        "_rows",
        lambda conn, where, params, **kw: (
            [definition] if "point IS NOT NULL" in where else [qualifier]
        ),
    )
    monkeypatch.setattr(tools, "resolve_key", lambda *args: [intro, qualifier])
    box = tools.Toolbox(None)
    output = box.get_definition("large corporate")
    assert "consolidated basis" in output and "purposes of this chapter" in output
    assert set(box.last_chunks) == {"d", "q0", "q1"}


def test_evidenced_positive_election_does_not_require_every_unrelated_exception():
    data = reply("**Yes**, the election applies [C1][C2].")
    data["claims"][0]["citations"] = ["C1", "C2"]
    hits = [
        hit("Art. 162(2)", "subject to paragraphs 3, 4 and 5"),
        hit("Art. 162(4)", "EU non-large corporates may elect the fixed M", "four"),
    ]
    assert guard("May this corporate elect the fixed maturity?", data, hits) == []


def test_judge_sees_section_mapping_and_cache_changes_with_evidence():
    item = GoldenItem(
        "v",
        "Which band?",
        "factual",
        "5%",
        [Citation("s", "para. 3")],
        "all",
        "t",
        "easy",
        "me",
        "verified",
    )
    rec = {
        "answer": "5% [C1]",
        "context": [
            {"id": "a", "source_id": "s", "ref": "para. 3", "hierarchy": ["Section 2.4.2"]}
        ],
        "evidence": [{"id": "a", "text": "At least 5%."}],
    }
    prompt = judge.judge_prompt(item, rec["answer"], rec)
    assert "Section 2.4.2" in prompt and "para. 3" in prompt and "At least 5%." in prompt
    changed = rec | {"context": [rec["context"][0] | {"hierarchy": ["Wrong section"]}]}
    assert judge.verdict_key(item, rec["answer"], "m", rec) != judge.verdict_key(
        item, rec["answer"], "m", changed
    )


def test_judge_flags_the_recorded_score_two_criteria_conflict():
    v = {
        "score": 0,
        "missing": [],
        "contradictions": ["extra detail"],
        "rationale": "The rubric's score-2 criteria are met; however, the answer is long.",
    }
    assert any("should be 2" in s for s in judge.consistency_flags(v))


class RepairCLI(ClaudeCLIProvider):
    def __init__(self, text):
        self.text, self.calls = text, []

    def complete(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return Completion(self.text, "test", Usage(100, 20), reported_cost_usd=0.02)


def test_format_repair_preserves_facts_and_has_no_research_tools():
    fixed = reply("The floor is 0.05% [C1].")
    raw = json.dumps(fixed)[:-1]  # actual truncation, not a different answer
    provider = RepairCLI(json.dumps(fixed))
    result, tokens, unknown, error = agent.repair_format(
        provider, "floor?", raw, ["truncated JSON"], {}, 1000, 0.05
    )
    assert result == fixed and tokens == 120 and not unknown and not error
    assert provider.calls[0][1]["purpose"] == "agent_format_repair"
    assert "--allowedTools" not in provider.calls[0][1]["extra_args"]
    # The repair may not add even an apparently plausible new fact.
    bad = RepairCLI(json.dumps(reply("The floor is 5% [C1].")))
    assert agent.repair_format(bad, "floor?", raw, ["bad"], {}, 1000, 0.05)[0] is None
    shortened = RepairCLI(json.dumps(reply("The floor is 0.05% [C1].")))
    original = fixed | {"answer": "The floor is 0.05% [C1]. Another required condition applies."}
    assert (
        agent.repair_format(
            shortened, "floor?", json.dumps(original)[:-1], ["bad"], {}, 1000, 0.05
        )[0]
        is None
    )
    assert agent.repair_format(provider, "q", raw, ["bad"], {}, 199999, 0.05) is None


def test_agent_preserves_placeholders_and_withholds_partly_read_answer(monkeypatch):
    row = tools.Row(
        "r",
        "crr3-consolidated",
        "Art. 1(1)",
        "Rule",
        "x" * 2500,
        "L1",
        None,
        "article",
        "1",
        "1",
        None,
    )
    monkeypatch.setattr(agent, "search", lambda *a, **k: [row.hit(0.9)])
    monkeypatch.setattr(agent, "resolve_key", lambda *a: [row])
    trace = [{"tool": "search", "keys": ["CRR Art. 1(1)"], "chunks": {"r": 2500}}]
    final = reply("Name [LEICode]_[ModelType] [CRR Art. 1(1)].")
    final["claims"][0]["citations"] = ["CRR Art. 1(1)"]
    completion = Completion(json.dumps(final), "test", Usage(100, 20), reported_cost_usd=0.02)
    monkeypatch.setattr(agent, "_run_once", lambda *a, **k: (completion, trace))
    result = agent.answer_agentic(None, RepairCLI("{}"), load_config(), "Name format?")
    assert result.answer == "Name [LEICode]_[ModelType] [C1]."
    trace[0]["chunks"] = {"r": 100}
    trace[0]["truncated"] = ["CRR Art. 1(1)"]
    result = agent.answer_agentic(None, RepairCLI("{}"), load_config(), "Name format?")
    assert result.unverified and not result.answer and result.raw_output and result.partial_cids
    assert "No verified answer" in render(result)


def test_unknown_attempt_usage_survives_fallback():
    bad = Answer("q", False, "", "", [], [], "", errors=["timeout"], usage_unknown_calls=1)
    good = Answer("q", False, "", "bounded answer", [], [], "", usage_tokens=20)
    _, outcome = dispatch("agent", "chain", 0, agent=lambda: bad, single=lambda: good)
    assert outcome["usage_unknown_calls"] == 1 and outcome["attempt_errors"]


def test_estimate_includes_known_cached_fallback(tmp_path):
    item = GoldenItem("one", "q", "factual", "a", [], "all", "t", "easy", "me", "verified")
    dirs = {m: tmp_path / m for m in ("single", "agent")}
    for d in dirs.values():
        d.mkdir()
    (dirs["single"] / artifact_name(item)).write_text(
        json.dumps({"answer": "partial", "missing_info": True, "research_needed": True})
    )
    routes = {item.id: {"route": "single"}}
    assert required_calls([item], dirs, routes=routes) == [(item.id, "agent")]
    (dirs["agent"] / artifact_name(item)).write_text('{"answer":"complete"}')
    assert required_calls([item], dirs, routes=routes) == []
