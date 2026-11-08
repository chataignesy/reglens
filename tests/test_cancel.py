"""Cancellation (review 2026-11-08: F5): stopping a question stops its work."""

import sys
import threading
import time

import pytest

from reglens.cancel import Cancelled, CancelToken, cancellable_runner
from reglens.config import load_config
from reglens.llm.provider import AnthropicAPIProvider, ClaudeCLIProvider


def test_cancel_kills_a_running_subprocess():
    token = CancelToken()
    run = cancellable_runner(token, poll_s=0.05)
    threading.Timer(0.3, token.cancel).start()
    start = time.monotonic()
    with pytest.raises(Cancelled):
        run([sys.executable, "-c", "import time; time.sleep(30)"], input="")
    assert time.monotonic() - start < 5  # killed, not waited for


def test_runner_returns_output_when_not_cancelled():
    out = cancellable_runner(CancelToken())([sys.executable, "-c", "print(input())"], input="hi\n")
    assert out.returncode == 0 and out.stdout.strip() == "hi"


def test_cancelled_providers_start_no_new_call(tmp_path):
    from dataclasses import replace

    cfg = replace(load_config(), ledger_path=tmp_path / "ledger.jsonl")
    token = CancelToken()
    calls = []
    cli = ClaudeCLIProvider(cfg, runner=lambda *a, **k: calls.append(a)).with_cancel(token)
    client = type("C", (), {})()
    api = AnthropicAPIProvider(cfg, client=client, fallback=False).with_cancel(token)
    token.cancel()
    with pytest.raises(Cancelled):
        cli.complete("q", purpose="p")
    with pytest.raises(Cancelled):
        api.complete("q", purpose="p")
    assert calls == []


def test_standalone_mcp_server_has_no_process_wide_cap(monkeypatch):
    """Review D8: a desktop MCP client keeps one server across questions."""
    import reglens.agent.mcp_server as mcp
    from reglens.agent.tools import Toolbox

    monkeypatch.delenv("REGLENS_MAX_TOOL_CALLS", raising=False)
    monkeypatch.setattr(mcp, "_box", None)
    monkeypatch.setattr("reglens.index.db.connect", lambda: None)
    box = mcp.box()
    assert box.max_calls is None and all(box._budget() is None for _ in range(50))
    capped = Toolbox(None, max_calls=2)
    assert [capped._budget() is None for _ in range(3)] == [True, True, False]
    monkeypatch.setattr(mcp, "_box", None)
    monkeypatch.setenv("REGLENS_MAX_TOOL_CALLS", "3")
    assert mcp.box().max_calls == 3  # the agent's per-question server keeps its budget


def test_killed_call_is_logged_as_unknown_usage(tmp_path):
    from dataclasses import replace

    from reglens.llm.ledger import Ledger

    cfg = replace(load_config(), ledger_path=tmp_path / "ledger.jsonl")
    token = CancelToken()

    def runner(*a, **k):
        token.cancel()
        raise Cancelled()

    cli = ClaudeCLIProvider(cfg, runner=runner)
    cli.cancel = CancelToken()  # not yet cancelled when the call starts
    with pytest.raises(Cancelled):
        cli.complete("q", purpose="answer")
    [entry] = Ledger(cfg).entries()
    assert entry["outcome"] == "cancelled" and entry["usage_known"] is False
