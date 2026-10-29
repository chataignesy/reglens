import json
from dataclasses import replace
from datetime import date

import reglens.agent.run as run
from reglens.agent.tools import Row, citation_key, source_by_name
from reglens.answer.verify import check_answer
from reglens.config import load_config
from reglens.llm.ledger import Usage
from reglens.llm.provider import Completion
from reglens.retrieve.search import Hit

ROWS = {
    "CRR Art. 151(8)": Row("c1", "crr3-consolidated", "Art. 151(8)", "Treatment", "CRR › Art. 151(8)\n"
                           "large corporates shall use LGD values set out in Article 161(1)", "L1",
                           "02013R0575-20260626", "article", "151", "8", None),
    "CRR Art. 161(1)": Row("c2", "crr3-consolidated", "Art. 161(1)", "LGD", "CRR › Art. 161(1)\n"
                           "senior exposures to corporates which are not financial sector entities: 40 %",
                           "L1", "02013R0575-20260626", "article", "161", "1", None),
}


def test_keys_and_sources():
    assert source_by_name("CRR").id == "crr3-consolidated"
    assert citation_key("eba-qa-credit-risk", "Q&A 2014_1297", None, "qa") == "EBA Q&A 2014_1297"
    assert citation_key("ecb-guide-internal-models", "para. 309", "Credit risk", "paragraph") == (
        "ECB guide to internal models, Credit risk, para. 309")


class FakeCLI:
    def __init__(self, reply):
        self.reply, self.kwargs = reply, None

    def complete(self, prompt, **kw):
        self.kwargs = kw
        return Completion(self.reply, "claude-sonnet-5-5", Usage(20000, 900, 15000, 3000))


def test_agent_resolves_keys_and_bounds(monkeypatch):
    top = Hit("c1", "crr3-consolidated", "Art. 151(8)", "", "", "L1", None, 0.9)
    monkeypatch.setattr(run, "search", lambda *a, **k: [top])
    monkeypatch.setattr(run, "resolve_key", lambda conn, key: [ROWS[key]] if key in ROWS else [])
    reply = {
        "abstain": False,
        "answer": "Supervisory LGD applies [CRR Art. 151(8)]: 40 % [CRR Art. 161(1)].",
        "claims": [
            {"text": "Large corporates use the Art. 161(1) LGD values.", "citations": ["CRR Art. 151(8)"], "kind": "law"},
            {"text": "The LGD is 40 %.", "citations": ["CRR Art. 161(1)"], "kind": "law"},
            {"text": "Made-up claim.", "citations": ["CRR Art. 999(1)"], "kind": "law"},
        ],
    }
    fake = FakeCLI(json.dumps(reply))
    cfg = replace(load_config(), agent={"max_calls": 5, "max_budget_usd": 0.3})
    ans = run.answer_agentic(None, fake, cfg, "F-IRB large corporate?", today=date(2026, 10, 29))

    args = fake.kwargs["extra_args"]
    assert args[args.index("--max-budget-usd") + 1] == "0.3"
    assert "mcp__reglens__follow_reference" in args[args.index("--allowedTools") + 1]
    assert "about 5 calls" in fake.kwargs["system"]
    assert ans.answer == "Supervisory LGD applies [C1]: 40 % [C2]."
    assert [c.citations for c in ans.claims] == [["C1"], ["C2"], ["C?"]]
    check_answer(ans)
    assert [c.check for c in ans.claims] == ["ok", "ok", "unknown_citation"]
    assert ans.as_of.startswith("As of 29 Oct 2026; CRR consolidated version of 26 Jun 2026")


def test_agent_gate_skips_llm(monkeypatch):
    monkeypatch.setattr(run, "search", lambda *a, **k: [
        Hit("x", "crr3-consolidated", "Art. 1", "", "", "L1", None, 0.001)])
    fake = FakeCLI("{}")
    ans = run.answer_agentic(None, fake, load_config(), "AML due diligence?")
    assert ans.abstained and fake.kwargs is None
