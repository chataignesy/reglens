"""No-model regressions from the fresh completeness evaluation."""

import json
from dataclasses import replace

from reglens.answer.research import guard
from reglens.retrieve.search import Hit


def hit(cid, ref, text):
    return Hit(cid, "eba-gl-dod", ref, "Guidelines", text, "L3", None, 1)


def draft(answer):
    return {"answer": answer, "abstain": False, "missing_info": False,
            "research_needed": False, "missing_requirements": [],
            "claims": [{"text": answer, "kind": "supervisory", "citations": ["C1"]}]}


def waiting_hits():
    return [
        hit("rule", "para. 42", "For a distressed restructuring, the probation period "
            "is at least one year."),
        hit("conditions", "para. 43", "An exposure may be reclassified after the period "
            "referred to in the previous paragraph, where all of the following conditions "
            "are met:\n(a) a material payment has been made;\n"
            "(b) there are no past-due amounts;\n(c) no concerns remain about full repayment."),
    ]


def test_time_rule_requires_linked_conditions_even_when_answer_never_mentions_them():
    hits = waiting_hits()
    data = draft("The probation period is at least one year [C1].")
    gaps = guard("How long is the probation period for a distressed restructuring?", data, hits)
    assert gaps and data["missing_info"]
    assert any("payment" in g or "repayment" in g for g in gaps)
    full = draft("At least one year, with a material payment, no past-due amounts, "
                 "and no concerns about full repayment [C1][C2].")
    assert not guard("How long is the probation period for a distressed restructuring?", full, hits)


def test_unrelated_adjacent_conditions_and_explicitly_excluded_scenarios_do_not_escalate():
    hits = waiting_hits()
    for question in ["What is the publication date?", "How long is the observation period?",
                     "What is the probation period, not under distressed restructuring?"]:
        assert not guard(question, draft("The period is one year [C1]."), hits)
    distant = [hits[0], replace(hits[1], ref="para. 47")]
    assert not guard("How long is the distressed restructuring probation period?",
                     draft("At least one year [C1]."), distant)


def test_one_document_cannot_crowd_the_time_rule_anchor_out_of_the_probe():
    distractions = [replace(waiting_hits()[0], id=f"other-{n}", ref=f"para. {n}",
                            source_id="ecb-guide-internal-models",
                            text="The subject defaulted distressed restructuring probation "
                            "period may be long.") for n in range(10, 14)]
    assert guard("How long is the probation period for a defaulted exposure subject to "
                 "distressed restructuring?", draft("One year [C5]."),
                 [*distractions, *waiting_hits()])


def test_incidental_words_in_a_condition_explanation_do_not_cover_its_predicate():
    hits = waiting_hits()
    hits[1].text = (
        "After the period referred to in the previous paragraph, all of the following "
        "conditions must be met:\n(a) a material payment has been made; the amount can "
        "reflect restructuring measures;\n(b) there are no past-due amounts;\n"
        "(c) no concerns remain about full repayment."
    )
    gaps = guard("How long is the distressed restructuring probation period?",
                 draft("One year after restructuring measures [C1]."), hits)
    assert any("(a)" in g and "material payment" in g for g in gaps)
    assert any("(b)" in g and "past-due" in g for g in gaps)


def test_broad_neighbours_are_discovery_candidates_not_mandatory_reads(monkeypatch):
    from reglens.agent import tools
    from reglens.answer import required_evidence as evidence

    anchor = tools.Row("anchor", "test", "para. 2", "Guide",
                       "Economic loss should include discounted recoveries.", "L3", None,
                       "paragraph", "b0", "2", None, cite="Test para. 2",
                       hierarchy=["Guide", "LGD", "Economic loss", "Definition"])
    peer = replace(anchor, id="peer", paragraph="3", ref="para. 3", cite="Test para. 3",
                   text="Economic loss should also reflect a specialised netting treatment.")
    def query(conn, where, params, **kwargs):
        if where == "id = %s":
            return [anchor]
        if where == "cite = %s":
            return [r for r in [anchor, peer] if r.cite == params[0]]
        return [anchor, peer]
    monkeypatch.setattr(tools, "_rows", query)
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rows: rows)
    question = "Which elements enter economic loss?"
    assert any(peer in g for g in evidence.evidence_units(object(), question, [anchor.hit()]))
    assert not guard(question, draft("Economic loss includes discounted recoveries [C1]."),
                     [anchor.hit()], conn=object())


def test_single_pass_rewrites_omissions_from_delivered_evidence_within_two_calls(monkeypatch):
    from reglens.answer import pipeline
    from reglens.config import load_config
    from reglens.llm.ledger import Usage
    from reglens.llm.provider import Completion

    hits = waiting_hits()
    monkeypatch.setattr(pipeline, "search", lambda *a, **k: hits)
    first = draft("The probation period is at least one year [C1].")
    final = draft("At least one year, with a material payment, no past-due amounts "
                  "and no concerns about full repayment [C1][C2].")
    class Provider:
        def __init__(self):
            self.purposes = []
        def complete(self, prompt, **kwargs):
            self.purposes.append(kwargs["purpose"])
            return Completion(json.dumps(first if len(self.purposes) == 1 else final),
                              "fixture", Usage(100, 50))
    provider = Provider()
    result = pipeline.answer_question(None, provider, load_config(),
                                     "How long is the distressed restructuring probation period?")
    assert provider.purposes == ["answer", "answer_completion"]
    assert not result.missing_info and result.usage_tokens == 300
    assert any(t["tool"] == "answer_completion" for t in result.trace)


def test_unresolved_omission_after_second_draft_stays_visible_without_a_third_call(monkeypatch):
    from reglens.answer import pipeline
    from reglens.config import load_config
    from reglens.llm.ledger import Usage
    from reglens.llm.provider import Completion

    monkeypatch.setattr(pipeline, "search", lambda *a, **k: waiting_hits())
    calls = []
    class Provider:
        def complete(self, prompt, **kwargs):
            calls.append(kwargs["purpose"])
            return Completion(json.dumps(draft("At least one year [C1].")),
                              "fixture", Usage(100, 50))
    result = pipeline.answer_question(None, Provider(), load_config(),
                                     "How long is the distressed restructuring probation period?")
    assert len(calls) == 2
    assert result.missing_info and result.research_needed and result.missing_requirements


def test_contract_repair_and_coverage_rewrite_share_the_same_second_call(monkeypatch):
    from reglens.answer import pipeline
    from reglens.config import load_config
    from reglens.llm.ledger import Usage
    from reglens.llm.provider import Completion

    monkeypatch.setattr(pipeline, "search", lambda *a, **k: waiting_hits())
    calls = []
    class Provider:
        def complete(self, prompt, **kwargs):
            calls.append(kwargs["purpose"])
            text = "not JSON" if len(calls) == 1 else json.dumps(draft("One year [C1]."))
            return Completion(text, "fixture", Usage(100, 50))
    result = pipeline.answer_question(None, Provider(), load_config(),
                                     "How long is the distressed restructuring probation period?")
    assert calls == ["answer", "answer_retry"]
    assert result.missing_info and not result.unverified
