import json

import pytest

from reglens.agent import api_loop, mcp_server
from reglens.agent.contracts import _ARGS, TOOL_SCHEMAS
from reglens.agent.tools import Row, Toolbox, trace_entry
from reglens.cancel import Cancelled


def test_sdk_and_mcp_script_have_identical_evidence_and_limits(monkeypatch, tmp_path):
    row = Row(
        "id",
        "crr3-consolidated",
        "Art. 1",
        "Rule",
        "x" * 3000,
        "L1",
        "v1",
        "article",
        "1",
        None,
        None,
    )
    monkeypatch.setattr(
        Toolbox, "search", lambda self, *args: self._budget() or self._out([row], snippets=True)
    )
    monkeypatch.setattr(
        Toolbox, "get_passage", lambda self, *args: self._budget() or self._out([row])
    )
    sdk, mcp = Toolbox(None, max_calls=2), Toolbox(None, max_calls=2)
    monkeypatch.setattr(mcp_server, "_box", mcp)
    path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("REGLENS_TRACE_FILE", str(path))
    script = [
        ("search", {"query": "rule"}, ("rule",)),
        ("get_passage", {"citation_key": "CRR Art. 1"}, ("CRR Art. 1",)),
        ("search", {"query": "more"}, ("more",)),
    ]
    expected = []
    for name, args, positional in script:
        out, values = api_loop._run_tool(sdk, name, args)
        assert mcp_server._call(name, *positional) == out
        expected.append(trace_entry(sdk.calls, name, values, out, sdk.last_chunks))
    assert [json.loads(line) for line in path.read_text().splitlines()] == expected
    assert "truncated" in expected[0] and not expected[2]["chunks"]
    assert set(_ARGS) == {s["name"] for s in TOOL_SCHEMAS}


def test_bad_arguments_and_cancellation_are_shared(monkeypatch):
    box = Toolbox(None)
    for args in ({"query": "q", "k": -1}, {"query": "q", "k": True}, {"bad": "q"}):
        assert api_loop._run_tool(box, "search", args)[0].startswith("Tool error")
        assert box.last_chunks == {}

    def cancelled(*args):
        raise Cancelled()

    monkeypatch.setattr(box, "search", cancelled)
    with pytest.raises(Cancelled):
        api_loop._run_tool(box, "search", {"query": "q"})


def test_parallel_mcp_calls_keep_budget_and_trace_together(monkeypatch, tmp_path):
    import concurrent.futures
    import time

    def search(box, query, *args):
        if note := box._budget():
            return note
        time.sleep(0.03)
        row = Row(
            query,
            "crr3-consolidated",
            "Art. 1",
            "Rule",
            query,
            "L1",
            "v1",
            "article",
            "1",
            None,
            None,
        )
        return box._out([row])

    monkeypatch.setattr(Toolbox, "search", search)
    monkeypatch.setattr(mcp_server, "_box", Toolbox(None, max_calls=2))
    path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("REGLENS_TRACE_FILE", str(path))
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda q: mcp_server._call("search", q), ["first", "second"]))
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    assert [e["call"] for e in entries] == [1, 2]
    assert all(e["chunks"] == {e["args"][0]: len(e["args"][0])} for e in entries)
