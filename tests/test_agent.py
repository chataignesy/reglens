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
    delivered = [{"tool": "search", "keys": ["CRR Art. 151(8)", "CRR Art. 161(1)"]}]
    monkeypatch.setattr(run, "_read_trace", lambda path: delivered)
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


def test_shortened_and_combined_keys_resolve(monkeypatch):
    """Prose often shortens a key or lists two in one bracket; both must map to passages."""
    monkeypatch.setattr(run, "resolve_key", lambda conn, key: [ROWS[key]] if key in ROWS else [])
    received = ["CRR Art. 151(8)", "CRR Art. 161(1)"]
    context, mapping = run._resolve(
        None, ["CRR Art. 151(8)", "Art. 161(1)", "CRR Art. 151(8); CRR Art. 161(1)", "para. 9"],
        received,
    )
    assert [h.id for h in context] == ["c1", "c2"]  # one context entry per chunk
    assert mapping["Art. 161(1)"] == ["C2"]
    assert mapping["CRR Art. 151(8); CRR Art. 161(1)"] == ["C1", "C2"]
    assert mapping["para. 9"] == ["C?"]
    assert run._match_received("EBA Art. 161(1)", received) is None  # name words must match


def test_mcp_tool_calls_are_traced(monkeypatch, tmp_path):
    import reglens.agent.mcp_server as srv

    class Box:
        calls = 0

        def search(self, query, k, source):
            self.calls += 1
            return "[CRR Art. 181(1)] (law)\ntext\n\n[EBA GL downturn LGD para. 36] (supervisory)\nx"

    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("REGLENS_TRACE_FILE", str(trace))
    monkeypatch.setattr(srv, "_box", Box())
    srv.search("downturn LGD", 6, None)
    entry = json.loads(trace.read_text(encoding="utf-8"))
    assert entry["tool"] == "search" and entry["call"] == 1
    assert entry["keys"] == ["CRR Art. 181(1)", "EBA GL downturn LGD para. 36"]


def test_agent_retries_when_no_tool_was_called(monkeypatch):
    top = Hit("c1", "crr3-consolidated", "Art. 151(8)", "", "", "L1", None, 0.9)
    monkeypatch.setattr(run, "search", lambda *a, **k: [top])
    monkeypatch.setattr(run, "_read_trace", lambda path: [])
    calls = []

    class Fake(FakeCLI):
        def complete(self, prompt, **kw):
            calls.append(1)
            return super().complete(prompt, **kw)

    ans = run.answer_agentic(None, Fake('{"abstain": true}'), load_config(), "F-IRB?")
    assert len(calls) == 2 and ans.usage_tokens == 2 * 38900
    assert ans.errors == ["agent made no tool calls (RegLens MCP tools unavailable?)"]


def test_snippets_point_to_get_passage(monkeypatch):
    import reglens.agent.tools as tools

    long_row = Row("c9", "crr3-consolidated", "Art. 181(1)", "LGD", "x" * 3000, "L1",
                   "02013R0575-20260626", "article", "181", "1", None)
    monkeypatch.setattr(tools, "resolve_key", lambda conn, key: [long_row])
    box = tools.Toolbox(None, snippet_chars=100, passage_chars=4000)
    snippet = box._out([long_row], snippets=True)
    assert "truncated; get_passage('CRR Art. 181(1)')" in snippet and len(snippet) < 300
    full = box.get_passage("CRR Art. 181(1)")
    assert "truncated" not in full and full.count("x") == 3000
    assert box.calls == 1


def test_keys_fall_back_to_the_enclosing_passage_and_expand_ranges(monkeypatch):
    para = {"CRR Art. 151(8)": ROWS["CRR Art. 151(8)"], "CRR Art. 161(1)": ROWS["CRR Art. 161(1)"]}
    monkeypatch.setattr(run, "resolve_key", lambda conn, key: [para[key]] if key in para else [])
    context, mapping = run._resolve(None, ["CRR Art. 151(8)(c)(ii)", "CRR Art. 999(1)(a)"])
    assert mapping["CRR Art. 151(8)(c)(ii)"] == ["C1"]  # point -> paragraph passage
    assert mapping["CRR Art. 999(1)(a)"] == ["C?"]
    _, m2 = run._resolve(None, ["CRR Art. 161(1)(b)-(c)"])
    assert m2["CRR Art. 161(1)(b)-(c)"] == ["C1"]  # a range of points -> the paragraph
    assert run._expand_range("EBA GL DoD paras. 71-73") == [
        "EBA GL DoD para. 71", "EBA GL DoD para. 72", "EBA GL DoD para. 73"]
    assert run._expand_range("EBA GL DoD para. 71") == ["EBA GL DoD para. 71"]
