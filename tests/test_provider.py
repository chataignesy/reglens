import json
import subprocess
from dataclasses import replace

import pytest

from reglens.config import load_config
from reglens.llm.ledger import Ledger
from reglens.llm.provider import ClaudeCLIProvider, LLMError, get_provider

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
    ClaudeCLIProvider(cfg, runner=fake_runner(json.dumps(sample))).complete("q", purpose="p")
    assert {e["model"] for e in Ledger(cfg).entries()} == {"claude-sonnet-5-5", "claude-haiku-5-5"}


def test_error_result_raises_and_logs_nothing(cfg):
    bad = dict(SAMPLE, is_error=True, subtype="error_during_execution")
    with pytest.raises(LLMError):
        ClaudeCLIProvider(cfg, runner=fake_runner(json.dumps(bad))).complete("q", purpose="p")
    assert Ledger(cfg).entries() == []


def test_non_json_output_raises(cfg):
    with pytest.raises(LLMError, match="non-JSON"):
        ClaudeCLIProvider(cfg, runner=fake_runner("not json", returncode=1)).complete(
            "q", purpose="p"
        )


def test_get_provider_by_billing(cfg):
    assert isinstance(get_provider(cfg), ClaudeCLIProvider)
    with pytest.raises(NotImplementedError):
        get_provider(replace(cfg, billing="api"))
