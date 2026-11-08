"""Runtime review 2026-11-08: R1 (partial reads), R2 (judge consistency), R3 (signals)."""

import json
from dataclasses import replace

from test_api_loop import FakeClient, _Obj, _response, _tool_use

import reglens.agent.api_loop as loop
from reglens.agent.tools import Row, Toolbox, partial_reads, trace_entry
from reglens.answer.pipeline import Answer, Claim
from reglens.answer.verify import check_answer
from reglens.config import load_config
from reglens.eval.judge import consistency_flags
from reglens.llm.provider import AnthropicAPIProvider
from reglens.retrieve.search import Hit

KEY = "EBA GL downturn LGD (GL/2019/03) para. 30"
LONG = Row("p30", "eba-gl-downturn-lgd", "para. 30", "GL", "x" * 2500, "L3", "v", "paragraph",
           "b1", "30", None, KEY)


# R1


def test_snippet_only_passages_are_partial_reads():
    snippet = Toolbox(None, snippet_chars=2000)._out([LONG], snippets=True)
    full = Toolbox(None)._out([LONG])
    seen = [trace_entry(1, "search", ["q"], snippet)]
    assert seen[0]["truncated"] == [KEY] and partial_reads(seen) == {KEY}
    seen.append(trace_entry(2, "get_passage", [KEY], full))
    assert partial_reads(seen) == set()  # read in full afterwards


def test_claims_on_partially_read_passages_fail_the_mechanical_check():
    hit = Hit("p30", "eba-gl-downturn-lgd", "para. 30", "GL", "t 5 %", "L3", None, 1.0)
    ans = Answer("q", False, "", "a [C1]", [Claim("5 %", ["C1"], "supervisory")], [hit], "")
    ans.partial_cids = ["C1"]
    check_answer(ans)
    assert ans.claims[0].check == "partial_read"


def test_api_loop_gives_one_round_to_read_what_the_answer_relies_on(monkeypatch, tmp_path):
    cfg = replace(load_config(), billing="api", ledger_path=tmp_path / "ledger.jsonl")
    monkeypatch.setattr(Toolbox, "search", lambda self, query, k=6, source=None: (
        self._budget() or self._out([LONG], snippets=True)))
    monkeypatch.setattr(Toolbox, "get_passage", lambda self, key: (
        self._budget() or self._out([LONG])))
    draft = {"abstain": False, "answer": f"Downturn LGD [{KEY}].",
             "claims": [{"text": "t", "citations": [KEY], "kind": "supervisory"}]}
    client = FakeClient([
        _response("tool_use", [_tool_use(1)]),
        _response("end_turn", [_Obj(type="text", text=json.dumps(draft))]),
        _response("tool_use", [_tool_use(2, name="get_passage", citation_key=KEY)]),
        _response("end_turn", [_Obj(type="text", text=json.dumps(draft))]),
    ])
    events = []
    text, trace, *_ = loop.run_api_agent(
        None, AnthropicAPIProvider(cfg, client=client), "q", system="S", tier="dev",
        effort=None, max_calls=10, max_turns=13, max_tokens=200_000, progress=events.append)
    assert [t["tool"] for t in trace] == ["search", "get_passage"] and len(client.calls) == 4
    nudge = client.calls[2]["messages"][-1]["content"][-1]["text"]
    assert "truncated snippets" in nudge and KEY in nudge
    assert any(e["stage"] == "completing" for e in events)
    assert partial_reads(trace) == set()


def test_completeness_round_is_used_only_once(monkeypatch, tmp_path):
    cfg = replace(load_config(), billing="api", ledger_path=tmp_path / "ledger.jsonl")
    gap = {"abstain": False, "missing_info": True, "answer": "Partly [k].",
           "claims": [{"text": "t", "citations": ["k"], "kind": "law"}]}
    client = FakeClient([_response("end_turn", [_Obj(type="text", text=json.dumps(gap))])])
    text, *_ = loop.run_api_agent(
        None, AnthropicAPIProvider(cfg, client=client), "q", system="S", tier="dev",
        effort=None, max_calls=10, max_turns=13, max_tokens=200_000)
    assert len(client.calls) == 2 and json.loads(text)["missing_info"] is True


# R2


def test_judge_verdicts_that_disagree_with_themselves_are_flagged():
    pd002 = {"score": 2, "missing": [], "contradictions": [],
             "rationale": "Omits the defaulted retail fact, so it should be 1 rather than 2."}
    assert consistency_flags(pd002) == ["rationale says the score should be 1"]
    assert consistency_flags({"score": 2, "missing": ["the 5% floor"], "contradictions": [],
                              "rationale": ""}) == ["score 2 but key facts listed as missing"]
    assert consistency_flags({"score": 1, "missing": ["x"], "contradictions": [],
                              "rationale": "partly"}) == []
