"""Subscription transport and tool loop tests. No real Codex/model calls."""

import json
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest

from reglens.config import load_config
from reglens.llm.codex import CodexCLIProvider
from reglens.llm.ledger import Ledger
from reglens.llm.provider import LLMError, get_provider


def events(text, usage=None, error=None):
    rows = [{"type": "item.completed", "item": {"type": "agent_message", "text": text}}]
    rows.append({"type": "turn.failed" if error else "turn.completed",
                 "usage": usage or {"input_tokens": 100, "cached_input_tokens": 40,
                                    "output_tokens": 10}})
    if error:
        rows[-1]["error"] = {"message": error}
    return "\n".join(map(json.dumps, rows))


@pytest.fixture
def cfg(tmp_path):
    return replace(load_config("config.codex.yaml"), ledger_path=tmp_path / "ledger.jsonl")


def fake(replies, calls):
    def run(cmd, **kw):
        calls.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, stdout=replies.pop(0), stderr="")
    return run


def test_subscription_auth_is_explicit_and_cache_tokens_not_double_counted(cfg):
    calls = []
    provider = CodexCLIProvider(cfg, runner=fake([events("OK")], calls))
    result = provider.complete("q", purpose="probe", system="Scoped rules", effort="low")
    assert result.usage.total_tokens == 110 and result.usage.input_tokens == 60
    assert result.usage.cache_read_input_tokens == 40
    cmd, kw = calls[0]
    assert '--ignore-user-config' in cmd and '--ephemeral' in cmd
    assert 'forced_login_method="chatgpt"' in cmd and 'features.shell_tool=false' in cmd
    assert 'features.multi_agent=false' in cmd and 'web_search="disabled"' in cmd
    assert kw["input"] == "q" and "q" not in cmd
    [receipt] = Ledger(cfg).entries()
    assert receipt["total_tokens"] == 110 and receipt["cost_eur"] is None
    assert isinstance(get_provider(cfg), CodexCLIProvider)
    with pytest.raises(ValueError):
        get_provider(cfg, api_key="not-a-real-key")
    with pytest.raises(ValueError):
        get_provider(replace(cfg, billing="api"))


def test_failure_retains_known_usage_and_timeout_is_unknown(cfg):
    provider = CodexCLIProvider(cfg, runner=fake([events("", error="Rate limit exceeded")], []))
    with pytest.raises(LLMError) as exc:
        provider.complete("q", purpose="probe")
    assert exc.value.retryable and exc.value.tokens == 110

    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired("codex", 1)

    with pytest.raises(LLMError) as exc:
        CodexCLIProvider(cfg, runner=timeout).complete("q", purpose="probe")
    assert not exc.value.usage_known
    assert Ledger(cfg).entries()[-1]["usage_known"] is False


def test_serialises_tool_history_and_blocks_tools_on_final_turn(cfg):
    calls = []
    text = json.dumps({"tool_calls": [{"name": "search", "arguments": {"query": "floor"}}]})
    provider = CodexCLIProvider(cfg, runner=fake([events(text), events(text)], calls))
    history = [{"role": "assistant", "content": [
        SimpleNamespace(type="text", text="prior result"),
    ]}]
    response, usage, _ = provider.create(history, purpose="agent", tools=[{"name": "search"}])
    assert response.stop_reason == "tool_use" and usage.total_tokens == 110
    assert json.loads(calls[0][1]["input"])["conversation"][0]["content"][0]["text"] == "prior result"
    with pytest.raises(LLMError, match="forbidden"):
        provider.create(history, purpose="agent", tools=[{"name": "search"}],
                        tool_choice={"type": "none"})


def test_native_tool_use_is_not_an_accepted_answer(cfg):
    stdout = json.dumps({"type": "item.completed", "item": {"type": "command_execution"}})
    stdout += "\n" + events("answer")
    with pytest.raises(LLMError, match="unexpected native tool"):
        CodexCLIProvider(cfg, runner=fake([stdout], [])).complete("q", purpose="probe")


def test_missing_usage_cannot_silently_spend_an_unmeasured_agent_budget(cfg):
    stdout = json.dumps({"type": "item.completed", "item": {"type": "agent_message",
                                                             "text": "OK"}})
    with pytest.raises(LLMError, match="did not report usage") as exc:
        CodexCLIProvider(cfg, runner=fake([stdout], [])).complete("q", purpose="probe")
    assert not exc.value.usage_known


def test_missing_cli_is_a_retryable_service_failure(cfg):
    def missing(*a, **kw):
        raise FileNotFoundError("codex")

    with pytest.raises(LLMError, match="Could not start") as exc:
        CodexCLIProvider(cfg, runner=missing).complete("q", purpose="probe")
    assert exc.value.retryable and not exc.value.usage_known


def test_codex_uses_existing_bounded_tool_loop_and_evidence_resolution(cfg, monkeypatch):
    import reglens.agent.run as agent
    from reglens.agent.tools import Row, Toolbox

    row = Row("r", "crr3-consolidated", "Art. 166(8b)", "CCF", "The rule.", "L1", None,
              "article", "166", "8b", None, "CRR Art. 166(8b)")
    monkeypatch.setattr(agent, "search", lambda *a, **k: [row.hit(1)])
    monkeypatch.setattr(agent, "resolve_key", lambda *a: [row])
    monkeypatch.setattr(Toolbox, "search", lambda self, *a: self._budget() or self._out([row]))
    final = {"answer": "The rule [CRR Art. 166(8b)].", "abstain": False,
             "missing_info": False, "research_needed": False, "missing_requirements": [],
             "claims": [{"text": "The rule", "kind": "law", "citations": ["CRR Art. 166(8b)"]}]}
    calls = []
    provider = CodexCLIProvider(cfg, runner=fake([
        events(json.dumps({"tool_calls": [{"name": "search", "arguments": {"query": "CCF"}}]})),
        events(json.dumps(final)),
    ], calls))
    answer = agent.answer_agentic(None, provider, cfg, "What is the CCF rule?")
    assert answer.answer == "The rule [C1]." and answer.usage_tokens == 220
    assert len(calls) == 2 and answer.trace[0]["tool"] == "search"
    assert not answer.errors and not answer.unverified
