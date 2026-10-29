import json
from dataclasses import replace
from datetime import date

from reglens.answer.pipeline import Answer, Claim, answer_question, as_of_statement, render
from reglens.answer.verify import _norm_numbers, check_answer
from reglens.config import load_config
from reglens.llm.ledger import Usage
from reglens.llm.provider import Completion
from reglens.retrieve.search import Hit

CRR_HIT = Hit("crr:178:1", "crr3-consolidated", "Art. 178(1)", "Default",
              "CRR › Art. 178 Default › Art. 178(1)\nmore than 90 days past due", "L1",
              "02013R0575-20260626", 0.9)
GL_HIT = Hit("dod:71", "eba-gl-dod", "para. 71", "Guidelines",
             "EBA GL definition of default › para. 71\nat least 3 months have passed", "L3",
             "2026-10-27", 0.8)


def _answer(claims):
    return Answer("q", False, "", "x [C1]", claims, [CRR_HIT, GL_HIT], "As of …")


def test_numbers_normalised():
    assert _norm_numbers("floor of 0,05 % and 30%") == {"0.05", "30"}
    assert _norm_numbers("0.050%") == {"0.05"}
    assert _norm_numbers("M of 2,5 years") == {"2.5"}
    assert _norm_numbers("more than 90 days") == {"90"}
    assert _norm_numbers("at least three months") == {"3"}
    assert _norm_numbers("CRR › Part Ten › three categories") == set()


def test_numbers_from_question_allowed():
    ans = _answer([Claim("EUR 120 past due for 95 days exceeds 90 days.", ["C1"], "interpretation")])
    ans.question = "An obligor owes EUR 120 for 95 days. Default?"
    check_answer(ans)
    assert ans.claims[0].check == "ok"


def test_verifier_flags():
    claims = [
        Claim("Default after more than 90 days past due.", ["C1"], "law"),
        Claim("Probation of at least 3 months.", ["C2"], "supervisory"),
        Claim("Probation of at least 6 months.", ["C2"], "supervisory"),
        Claim("Probation of at least 3 months.", ["C2"], "law"),
        Claim("Uncited claim.", [], "law"),
        Claim("Cites a missing passage.", ["C9"], "law"),
    ]
    summary = check_answer(_answer(claims))
    assert [c.check.split("(")[0] for c in claims] == [
        "ok", "ok", "unsupported_number", "kind_mismatch", "no_citation", "unknown_citation"
    ]
    assert summary["ok"] == 2 and summary["claims"] == 6


def test_citation_recall_with_alternatives():
    from reglens.eval.answers import citation_recall
    from reglens.eval.golden import Citation, GoldenItem

    item = GoldenItem("x", "q", "factual", "a", [
        Citation("crr3-consolidated", "Art. 178(1)(b)"),
        Citation("eba-gl-dod", "para. 72", (Citation("ecb-guide-internal-models", "para. 172"),)),
    ], "all", "t", "easy", "me", "verified")
    record = {
        "context": [{"source_id": "crr3-consolidated", "ref": "Art. 178(1)"},
                    {"source_id": "ecb-guide-internal-models", "ref": "para. 172"},
                    {"source_id": "eba-gl-dod", "ref": "para. 99"}],
        "claims": [{"citations": ["C1", "C2"]}],
    }
    assert citation_recall(item, record) == 1.0  # direct hit + accepted alternative
    record["claims"] = [{"citations": ["C3"]}]
    assert citation_recall(item, record) == 0.0


def test_as_of_from_versions():
    s = as_of_statement([CRR_HIT, GL_HIT], date(2026, 10, 28))
    assert s == ("As of 28 Oct 2026; CRR consolidated version of 26 Jun 2026; "
                 "other sources retrieved 27 Oct 2026")


class FakeProvider:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def complete(self, prompt, **kw):
        self.calls += 1
        return Completion(self.text, "claude-sonnet-5-5", Usage(100, 50))


def test_pipeline_gate_and_parse(monkeypatch):
    cfg = load_config()
    import reglens.answer.pipeline as p

    monkeypatch.setattr(p, "search", lambda *a, **k: [replace(CRR_HIT, score=0.001)])
    fake = FakeProvider("{}")
    ans = answer_question(None, fake, cfg, "AML?", today=date(2026, 10, 28))
    assert ans.abstained and fake.calls == 0  # gate: no LLM call

    monkeypatch.setattr(p, "search", lambda *a, **k: [CRR_HIT, GL_HIT])
    out = {"abstain": False, "answer": "Default after 90 days [C1].",
           "claims": [{"text": "more than 90 days past due", "citations": ["C1"], "kind": "law"}]}
    fake = FakeProvider("```json\n" + json.dumps(out) + "\n```")
    ans = answer_question(None, fake, cfg, "When is default?", today=date(2026, 10, 28))
    assert not ans.abstained and ans.claims[0].citations == ["C1"]
    check_answer(ans)
    md = render(ans)
    assert "[C1] CRR Art. 178(1) — law" in md
    assert "not legal or regulatory advice" in md
