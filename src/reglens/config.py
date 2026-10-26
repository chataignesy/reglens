"""Load config.yaml: model tiers, prices and budget."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float
    long_threshold_tokens: int | None = None
    long_input: float | None = None
    long_output: float | None = None


@dataclass(frozen=True)
class Budget:
    usd_to_eur: float
    target_eur: float
    ceiling_eur: float
    approval_threshold_eur: float
    approval_threshold_tokens: int
    current_phase: int
    phases_eur: dict[int, float]


BILLING_MODES = {"subscription", "api"}


@dataclass(frozen=True)
class Config:
    billing: str
    tiers: dict[str, str]
    default_tier: str
    prices: dict[str, ModelPrice]
    cache_write_multiplier: float
    batch_discount: float
    budget: Budget
    ledger_path: Path

    def model(self, tier: str | None = None) -> str:
        """Model ID for a tier ('bulk', 'dev', 'milestone'); default tier if None."""
        tier = tier or self.default_tier
        if tier not in self.tiers:
            raise KeyError(f"Unknown model tier {tier!r}; known: {sorted(self.tiers)}")
        return self.tiers[tier]

    def price(self, model: str) -> ModelPrice:
        if model not in self.prices:
            raise KeyError(f"No pricing configured for model {model!r}")
        return self.prices[model]


def _parse_price(raw: dict) -> ModelPrice:
    long = raw.get("long_context") or {}
    return ModelPrice(
        input=float(raw["input"]),
        output=float(raw["output"]),
        cache_read=float(raw["cache_read"]),
        long_threshold_tokens=long.get("threshold_tokens"),
        long_input=long.get("input"),
        long_output=long.get("output"),
    )


def load_config(path: str | Path | None = None) -> Config:
    """Load config from `path`, $REGLENS_CONFIG, or the project's config.yaml."""
    path = Path(path or os.environ.get("REGLENS_CONFIG") or DEFAULT_CONFIG)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    models = raw["models"]
    rules = raw["pricing_rules"]
    b = raw["budget"]
    ledger_path = Path(raw["ledger_path"])
    if not ledger_path.is_absolute():
        ledger_path = path.parent / ledger_path

    billing = raw.get("billing", "api")
    if billing not in BILLING_MODES:
        raise ValueError(f"billing must be one of {sorted(BILLING_MODES)}, got {billing!r}")

    cfg = Config(
        billing=billing,
        tiers=dict(models["tiers"]),
        default_tier=models["default_tier"],
        prices={name: _parse_price(p) for name, p in raw["pricing"].items()},
        cache_write_multiplier=float(rules["cache_write_multiplier"]),
        batch_discount=float(rules["batch_discount"]),
        budget=Budget(
            usd_to_eur=float(b["usd_to_eur"]),
            target_eur=float(b["target_eur"]),
            ceiling_eur=float(b["ceiling_eur"]),
            approval_threshold_eur=float(b["approval_threshold_eur"]),
            approval_threshold_tokens=int(b["approval_threshold_tokens"]),
            current_phase=int(b["current_phase"]),
            phases_eur={int(k): float(v) for k, v in b["phases_eur"].items()},
        ),
        ledger_path=ledger_path,
    )
    missing = [m for m in cfg.tiers.values() if m not in cfg.prices]
    if missing:
        raise ValueError(f"Tier models without pricing: {missing}")
    return cfg
