"""API agent loop with a fake SDK client: no network, no paid calls."""

import json
from dataclasses import replace
from datetime import date

import pytest

import reglens.agent.api_loop as loop
import reglens.agent.run as run
from reglens.agent.tools import Row, Toolbox
from reglens.config import load_config
from reglens.llm.ledger import Ledger
from reglens.llm.provider import AnthropicAPIProvider
from reglens.retrieve.search import Hit

ROW = Row("c1", "crr3-consolidated", "Art. 151(8)", "Treatment", "CRR › Art. 151(8)\nlarge "
          "corporates shall use LGD values set out in Article 161(1)", "L1",
          "02013R0575-20260626", "article", "151", "8", None)
FINAL = {
    "abstain": False,
    "answer": "Large corporates use supervisory LGD [CRR Art. 151(8)].",
    "claims": [{"text": "Large corporates use Art. 161(1) LGDs.",
                "citations": ["CRR Art. 151(8)"], "kind": "law"}],
}


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _response(stop_reason, content):
    usage = _Obj(input_tokens=1000, output_tokens=100, cache_read_input_tokens=500,
                 cache_creation_input_tokens=0)
    return _Obj(model="claude-sonnet-5-5", stop_reason=stop_reason, content=content, usage=usage)


def _tool_use(i, name="search", **inp):
    return _Obj(type="tool_use", id=f"tu{i}", name=name, input=inp or {"query": "large corporate"})


class FakeClient:
    """Plays back a script of responses; records every request."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

        def create(**kwargs):
            self.calls.append(kwargs)
            return self.script.pop(0) if len(self.script) > 1 else self.script[0]

        self.beta = _Obj(messages=_Obj(create=create))
        self.messages = _Obj(create=create)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    cfg = replace(load_config(), billing="api", ledger_path=tmp_path / "ledger.jsonl")
    monkeypatch.setattr(Toolbox, "search", lambda self, query, k=6, source=None: (
        self._budget() or self._out([ROW], snippets=True)))
    return cfg


def test_loop_runs_tools_and_answers(setup):
    client = FakeClient([
        _response("tool_use", [_Obj(type="text", text="Searching."), _tool_use(1)]),
        _response("end_turn", [_Obj(type="text", text=json.dumps(FINAL))]),
    ])
    provider = AnthropicAPIProvider(setup, client=client)
    text, trace, tokens, model, errors = loop.run_api_agent(
        None, provider, "Own LGD for a large corporate?", system="SYS", tier="dev",
        effort="medium", max_calls=10, max_turns=13, max_tokens=200_000,
    )
    assert json.loads(text) == FINAL and errors == []
    assert [t["tool"] for t in trace] == ["search"] and trace[0]["keys"] == ["CRR Art. 151(8)"]
    assert tokens == 2 * 1600 and model == "claude-sonnet-5-5"
    second = client.calls[1]
    assert {t["name"] for t in second["tools"]} == set(run.TOOLS)
    [result] = [b for b in second["messages"][-1]["content"] if b["type"] == "tool_result"]
    assert result["tool_use_id"] == "tu1" and "CRR Art. 151(8)" in result["content"]
    assert second["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in client.calls[0]["messages"][0]  # the caller's list is untouched
    assert len(Ledger(setup).entries()) == 2  # every model call is logged


def test_call_limit_makes_the_next_turn_final_without_tools(setup):
    client = FakeClient([_response("tool_use", [_tool_use(1)])])  # never stops calling tools
    provider = AnthropicAPIProvider(setup, client=client)
    text, trace, tokens, model, errors = loop.run_api_agent(
        None, provider, "q", system="SYS", tier="dev", effort=None,
        max_calls=2, max_turns=13, max_tokens=200_000,
    )
    assert len(trace) == 2 and len(client.calls) == 3  # 2 tool rounds, then one final turn
    assert "tool_choice" not in client.calls[1]
    final = client.calls[2]
    assert final["tool_choice"] == {"type": "none"}  # tools forbidden on the final turn
    assert final["messages"][-1]["content"][-1]["text"] == loop.STOP_NOTE
    assert text == "" and errors == ["agent asked for tools on its final turn"]


def test_reserve_forces_the_final_turn_before_the_budget(setup):
    """Review F8: the budget is checked before a request, not after it."""
    client = FakeClient([_response("tool_use", [_tool_use(1)]),
                         _response("end_turn", [_Obj(type="text", text=json.dumps(FINAL))])])
    provider = AnthropicAPIProvider(setup, client=client)
    text, _, tokens, _, errors = loop.run_api_agent(
        None, provider, "q", system="SYS", tier="dev", effort=None,
        max_calls=10, max_turns=13, max_tokens=4000)
    # after 1,600 tokens another tool round (~2,080) would eat the 800-token final reserve
    assert client.calls[1]["tool_choice"] == {"type": "none"}
    assert client.calls[1]["messages"][-1]["content"][-1]["text"] == loop.STOP_NOTE
    assert json.loads(text) == FINAL and tokens == 3200 and errors == []


def test_no_request_once_the_budget_is_spent(setup):
    client = FakeClient([_response("tool_use", [_tool_use(1)])])
    provider = AnthropicAPIProvider(setup, client=client)
    text, _, tokens, _, errors = loop.run_api_agent(
        None, provider, "q", system="SYS", tier="dev", effort=None,
        max_calls=10, max_turns=13, max_tokens=1000)
    assert len(client.calls) == 1 and tokens == 1600 and text == ""
    assert errors == ["token budget (1,000) spent before the final answer"]


def test_last_turn_is_final(setup):
    client = FakeClient([_response("tool_use", [_tool_use(1)]),
                         _response("end_turn", [_Obj(type="text", text=json.dumps(FINAL))])])
    provider = AnthropicAPIProvider(setup, client=client)
    loop.run_api_agent(None, provider, "q", system="SYS", tier="dev", effort=None,
                       max_calls=10, max_turns=2, max_tokens=200_000)
    assert client.calls[1]["tool_choice"] == {"type": "none"}


def test_bad_tool_arguments_become_error_results(setup):
    box = Toolbox(None)
    out, _ = loop._run_tool(box, "nope", {})
    assert out.startswith("Unknown tool")


def test_answer_agentic_uses_api_loop(setup, monkeypatch):
    top = Hit("c1", "crr3-consolidated", "Art. 151(8)", "", "", "L1", None, 0.9)
    monkeypatch.setattr(run, "search", lambda *a, **k: [top])
    monkeypatch.setattr(run, "resolve_key", lambda conn, key: [ROW] if key == "CRR Art. 151(8)" else [])
    client = FakeClient([
        _response("tool_use", [_tool_use(1)]),
        _response("end_turn", [_Obj(type="text", text=json.dumps(FINAL))]),
    ])
    ans = run.answer_agentic(None, AnthropicAPIProvider(setup, client=client), setup,
                             "Own LGD for a large corporate?", today=date(2026, 10, 31))
    assert ans.answer == "Large corporates use supervisory LGD [C1]." and ans.errors == []
    assert [c.citations for c in ans.claims] == [["C1"]] and ans.trace[0]["tool"] == "search"
    assert ans.usage_tokens == 3200
