from dataclasses import replace

import pytest

from reglens.config import ModelPrice, load_config
from reglens.llm.ledger import Ledger, Usage, cost_usd


@pytest.fixture
def cfg(tmp_path):
    # Real config, but the ledger goes to a temp file.
    return replace(load_config(), ledger_path=tmp_path / "ledger.jsonl")


def test_tiers_resolve_to_priced_models(cfg):
    for tier in ("bulk", "dev", "milestone"):
        assert cfg.price(cfg.model(tier))
    assert cfg.model() == cfg.model(cfg.default_tier)
    with pytest.raises(KeyError):
        cfg.model("nope")


def test_cost_basic_and_batch():
    price = ModelPrice(input=2.0, output=10.0, cache_read=0.2)
    usage = Usage(input_tokens=1_000_000, output_tokens=100_000)
    assert cost_usd(price, usage, cache_write_multiplier=1.25) == pytest.approx(3.0)
    assert cost_usd(price, usage, cache_write_multiplier=1.25, batch_discount=0.5) == (
        pytest.approx(1.5)
    )


def test_cost_cache_read_and_write():
    price = ModelPrice(input=2.0, output=10.0, cache_read=0.2)
    usage = Usage(
        input_tokens=0,
        output_tokens=0,
        cache_read_input_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000,
    )
    assert cost_usd(price, usage, cache_write_multiplier=1.25) == pytest.approx(0.2 + 2.5)


def test_long_context_rates_apply_above_threshold():
    price = ModelPrice(
        input=0.1, output=0.5, cache_read=0.01,
        long_threshold_tokens=100_000, long_input=0.5, long_output=2.5,
    )
    short = Usage(input_tokens=100_000, output_tokens=0)
    long = Usage(input_tokens=100_001, output_tokens=0)
    assert cost_usd(price, short, cache_write_multiplier=1.25) == pytest.approx(0.01)
    assert cost_usd(price, long, cache_write_multiplier=1.25) == pytest.approx(0.0500005)


def test_usage_from_sdk_like_object():
    class FakeUsage:
        input_tokens = 10
        output_tokens = 5
        cache_read_input_tokens = None
        cache_creation_input_tokens = 3

    assert Usage.from_response(FakeUsage()) == Usage(10, 5, 0, 3)
    assert Usage.from_response({"input_tokens": 1, "output_tokens": 2}) == Usage(1, 2)


def test_record_and_summary(cfg):
    ledger = Ledger(cfg)
    ledger.record(cfg.model("dev"), Usage(1000, 100), purpose="smoke-eval")
    ledger.record(cfg.model("bulk"), {"input_tokens": 500, "output_tokens": 50}, purpose="enrich")

    assert len(ledger.entries()) == 2
    by_purpose = ledger.summary(by="purpose")
    assert by_purpose["smoke-eval"]["calls"] == 1
    assert by_purpose["enrich"]["input_tokens"] == 500
    assert ledger.total_tokens() == 1100 + 550
    assert ledger.total_eur() > 0
    assert set(ledger.summary(by="phase")) == {cfg.budget.current_phase}
    assert all(e["billing"] == cfg.billing for e in ledger.entries())


def test_unpriced_model_logs_tokens_without_cost(cfg):
    # e.g. a subscription run reporting a model alias with no configured price
    ledger = Ledger(cfg)
    entry = ledger.record("sonnet", Usage(200, 20, cache_read_input_tokens=1000), purpose="dev")
    assert entry["cost_eur"] is None
    assert entry["total_tokens"] == 1220
    summary = ledger.summary(by="model")["sonnet"]
    assert summary["cached_tokens"] == 1000
    assert summary["cost_eur"] == 0.0
    assert ledger.total_tokens() == 1220


def test_usage_from_claude_cli_json():
    # shape of the `usage` field in `claude -p --output-format json`
    raw = {
        "input_tokens": 12,
        "cache_creation_input_tokens": 3000,
        "cache_read_input_tokens": 15000,
        "output_tokens": 400,
        "service_tier": "standard",
    }
    assert Usage.from_response(raw).total_tokens == 18412
