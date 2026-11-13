import json
import subprocess
from dataclasses import replace

import pytest

from reglens.config import load_config
from reglens.llm.ledger import Ledger
from reglens.llm.provider import AnthropicAPIProvider, ClaudeCLIProvider, LLMError, get_provider

# Trimmed real `claude -p --output-format json` output.
SAMPLE = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": "ok",
    "stop_reason": "end_turn",
    "total_cost_usd": 0.0012,
    "usage": {
        "input_tokens": 394,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 4,
    },
    "modelUsage": {
        "claude-haiku-5-5": {
            "inputTokens": 394,
            "outputTokens": 4,
            "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0,
            "costUSD": 0.0012,
        }
    },
}


@pytest.fixture
def cfg(tmp_path):
    return replace(load_config(), billing="subscription", ledger_path=tmp_path / "ledger.jsonl")


def fake_runner(stdout, returncode=0, calls=None):
    def run(cmd, **kwargs):
        if calls is not None:
            calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="boom")

    return run


def test_complete_parses_result_and_logs_usage(cfg):
    calls = []
    provider = ClaudeCLIProvider(cfg, runner=fake_runner(json.dumps(SAMPLE), calls=calls))
    out = provider.complete("hi", purpose="probe", tier="bulk", effort="low")

    assert out.text == "ok"
    assert out.model == cfg.model("bulk")
    assert out.usage.total_tokens == 398

    cmd, kwargs = calls[0]
    assert cmd[cmd.index("--model") + 1] == cfg.model("bulk")
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--effort") + 1] == "low"
    assert kwargs["input"] == "hi"  # prompt goes via stdin

    [entry] = Ledger(cfg).entries()
    assert entry["purpose"] == "probe"
    assert entry["total_tokens"] == 398
    assert entry["reported_cost_usd"] == 0.0012


def test_one_ledger_entry_per_model_used(cfg):
    sample = dict(SAMPLE)
    sample["modelUsage"] = {
        "claude-sonnet-5-5": {"inputTokens": 1000, "outputTokens": 100},
        "claude-haiku-5-5": {"inputTokens": 50, "outputTokens": 5},
    }
    result = ClaudeCLIProvider(cfg, runner=fake_runner(json.dumps(sample))).complete("q", purpose="p")
    assert {e["model"] for e in Ledger(cfg).entries()} == {"claude-sonnet-5-5", "claude-haiku-5-5"}
    assert result.usage.total_tokens == sum(e["total_tokens"] for e in Ledger(cfg).entries()) == 1155


def test_failed_call_still_logs_its_usage(cfg):
    """Review D9: a call stopped at its budget cap spent tokens; the ledger must show them."""
    bad = {"is_error": True, "subtype": "error_max_budget_usd",
           "usage": {"input_tokens": 1000, "output_tokens": 100}}
    with pytest.raises(LLMError) as err:
        ClaudeCLIProvider(cfg, runner=fake_runner(json.dumps(bad))).complete("q", purpose="p")
    assert err.value.tokens == 1100
    [entry] = Ledger(cfg).entries()
    assert entry["outcome"] == "error_max_budget_usd" and entry["total_tokens"] == 1100


def test_failed_call_without_usage_is_unknown_not_zero(cfg):
    bad = {"is_error": True, "subtype": "error_during_execution"}
    with pytest.raises(LLMError) as err:
        ClaudeCLIProvider(cfg, runner=fake_runner(json.dumps(bad))).complete("q", purpose="p")
    assert err.value.tokens is None
    [entry] = Ledger(cfg).entries()
    assert entry["usage_known"] is False and entry["outcome"] == "error_during_execution"


def test_non_json_output_raises(cfg):
    with pytest.raises(LLMError, match="non-JSON"):
        ClaudeCLIProvider(cfg, runner=fake_runner("not json", returncode=1)).complete(
            "q", purpose="p"
        )
    assert Ledger(cfg).entries()[0]["usage_known"] is False


def test_get_provider_by_billing(cfg):
    assert isinstance(get_provider(cfg), ClaudeCLIProvider)
    api = get_provider(replace(cfg, billing="api"), api_key="sk-test-not-real")
    assert isinstance(api, AnthropicAPIProvider)


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeClient:
    """Stands in for anthropic.Anthropic(): records the request, returns a canned response."""

    def __init__(self, stop_reason="end_turn"):
        self.calls = []
        response = _Obj(
            model="claude-sonnet-5-5",
            stop_reason=stop_reason,
            stop_details=_Obj(category="cyber") if stop_reason == "refusal" else None,
            content=[_Obj(type="thinking", thinking=""), _Obj(type="text", text="{\"a\": 1}")],
            usage=_Obj(input_tokens=900, output_tokens=120, cache_read_input_tokens=0,
                       cache_creation_input_tokens=800),
        )

        def create(**kwargs):
            self.calls.append(kwargs)
            return response

        self.beta = _Obj(messages=_Obj(create=create))
        self.messages = _Obj(create=create)


def test_api_provider_request_shape_and_ledger(cfg):
    client = FakeClient()
    p = AnthropicAPIProvider(replace(cfg, billing="api"), client=client)
    out = p.complete("hi", purpose="answer", system="SYS", tier="dev", effort="medium")
    req = client.calls[0]
    assert req["model"] == cfg.model("dev")
    assert req["system"][0]["text"] == "SYS" and req["system"][0]["cache_control"]
    assert req["output_config"] == {"effort": "medium"}
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in req  # adaptive thinking is the model default
    assert out.text == '{"a": 1}' and out.usage.total_tokens == 1820
    [entry] = Ledger(cfg).entries()
    assert entry["purpose"] == "answer" and entry["total_tokens"] == 1820


def test_api_provider_refusal_raises(cfg):
    p = AnthropicAPIProvider(replace(cfg, billing="api"), client=FakeClient("refusal"))
    with pytest.raises(LLMError, match="declined"):
        p.complete("hi", purpose="answer")
