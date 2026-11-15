"""Answer contract (review 2026-11-08: F10) and the unverified-output state."""

import json
from datetime import date

import reglens.agent.run as agent_run
import reglens.answer.pipeline as p
from reglens.answer.pipeline import Answer, answer_question, render
from reglens.answer.schema import parse_reply, problems
from reglens.api.app import answer_payload
from reglens.config import load_config
from reglens.llm.ledger import Usage
from reglens.llm.provider import Completion
from reglens.retrieve.search import Hit

HIT = Hit("crr:178:1", "crr3-consolidated", "Art. 178(1)", "Default",
          "CRR › Art. 178(1)\nmore than 90 days past due", "L1", "02013R0575-20260626", 0.9)
GOOD = {"abstain": False, "answer": "Default after 90 days [C1].",
        "claims": [{"text": "more than 90 days past due", "citations": ["C1"], "kind": "law"}]}


class Replies:
    def __init__(self, *texts):
        self.texts, self.prompts, self.purposes = list(texts), [], []

    def complete(self, prompt, **kw):
        self.prompts.append(prompt)
        self.purposes.append(kw.get("purpose"))
        return Completion(self.texts.pop(0), "claude-sonnet-5-5", Usage(100, 50))


def test_contract_problems():
    assert problems(GOOD) == []
    assert problems({"abstain": True, "abstain_reason": "out of scope"}) == []
    assert problems([1]) == ["reply is not a JSON object"]
    bad = {"answer": "", "claims": [{"text": "x", "citations": [], "kind": "law"},
                                    {"text": "y", "citations": "C1", "kind": "opinion"}]}
    found = problems(bad)
    assert "empty answer text" in found and "claim 1 cites nothing" in found
    assert any("kind 'opinion'" in f for f in found)
    assert any("not a list of strings" in f for f in found)
    assert problems({"answer": "a", "claims": [
        {"text": "my inference", "citations": [], "kind": "interpretation"}]}) == []
    assert parse_reply("no json here")[1][0].startswith("unparseable model output")


def test_invalid_reply_is_retried_once(monkeypatch):
    monkeypatch.setattr(p, "search", lambda *a, **k: [HIT])
    fake = Replies("Sorry, here is prose instead of JSON.", json.dumps(GOOD))
    ans = answer_question(None, fake, load_config(), "When?", today=date(2026, 11, 8))
    assert not ans.unverified and ans.claims[0].citations == ["C1"]
    assert fake.purposes == ["answer", "answer_retry"]
    assert "could not be used: unparseable" in fake.prompts[1]
    assert ans.usage_tokens == 300  # both calls counted


def test_twice_invalid_is_unverified_not_an_answer(monkeypatch):
    monkeypatch.setattr(p, "search", lambda *a, **k: [HIT])
    raw = "The default is after 90 days (no JSON)."
    fake = Replies(raw, json.dumps({"answer": "x", "claims": []}))
    ans = answer_question(None, fake, load_config(), "When?", today=date(2026, 11, 8))
    assert ans.unverified and ans.answer == "" and ans.claims == []
    assert ans.raw_output.startswith("{") and "no claims" in ans.errors[0]
    assert "No verified answer" in render(ans)
    payload = answer_payload(ans, {"ok": 0, "claims": 0})
    assert payload["unverified"] and payload["answer"] == "" and payload["raw_output"]


def test_agent_invalid_reply_is_unverified(monkeypatch):
    monkeypatch.setattr(agent_run, "search", lambda *a, **k: [HIT])
    monkeypatch.setattr(agent_run, "_read_trace", lambda path: [{"tool": "search", "keys": ["k"]}])
    invalid = '{"answer": "x", "claims": [{"text": "t", "citations": [], "kind": "law"}]}'
    fake = Replies(invalid, invalid)  # one format-only repair also fails the contract
    ans = agent_run.answer_agentic(None, fake, load_config(), "q", today=date(2026, 11, 8))
    assert ans.unverified and ans.answer == "" and "cites nothing" in ans.errors[-1]
    assert fake.purposes == ["agent", "agent_format_repair"] and ans.usage_tokens == 300


def test_valid_answer_payload_is_not_unverified():
    ans = Answer("q", False, "", "a [C1]", [], [HIT], "As of …")
    payload = answer_payload(ans, {"ok": 0, "claims": 0})
    assert payload["unverified"] is False and payload["raw_output"] == ""
