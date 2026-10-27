"""Usage ledger: every LLM call is appended to data/ledger.jsonl.

Tokens are the primary measure. With `billing: subscription` the EUR figure is an
API-equivalent estimate for comparison only; with `billing: api` it is the real cost.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from reglens.config import Config, ModelPrice


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
        )

    @classmethod
    def from_response(cls, usage: Any) -> Usage:
        """Build from an Anthropic `response.usage` object or a plain dict
        (e.g. the `usage` field of `claude -p --output-format json`)."""

        def get(name: str) -> int:
            value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            return int(value or 0)

        return cls(
            input_tokens=get("input_tokens"),
            output_tokens=get("output_tokens"),
            cache_read_input_tokens=get("cache_read_input_tokens"),
            cache_creation_input_tokens=get("cache_creation_input_tokens"),
        )


def cost_usd(
    price: ModelPrice,
    usage: Usage,
    *,
    cache_write_multiplier: float,
    batch_discount: float = 1.0,
) -> float:
    """Estimated USD cost of one call. Pass batch_discount<1 for Batch API calls."""
    prompt_tokens = (
        usage.input_tokens + usage.cache_read_input_tokens + usage.cache_creation_input_tokens
    )
    in_rate, out_rate = price.input, price.output
    if price.long_threshold_tokens and prompt_tokens > price.long_threshold_tokens:
        in_rate = price.long_input or in_rate
        out_rate = price.long_output or out_rate

    total = (
        usage.input_tokens * in_rate
        + usage.cache_creation_input_tokens * in_rate * cache_write_multiplier
        + usage.cache_read_input_tokens * price.cache_read
        + usage.output_tokens * out_rate
    ) / 1_000_000
    return total * batch_discount


class Ledger:
    def __init__(self, config: Config):
        self.config = config
        self.path = config.ledger_path

    def estimate_eur(self, model: str, usage: Usage, *, batch: bool = False) -> float | None:
        """EUR at API list prices (API-equivalent under a subscription); None if unpriced."""
        if model not in self.config.prices:
            return None
        usd = cost_usd(
            self.config.price(model),
            usage,
            cache_write_multiplier=self.config.cache_write_multiplier,
            batch_discount=self.config.batch_discount if batch else 1.0,
        )
        return usd * self.config.budget.usd_to_eur

    def record(
        self,
        model: str,
        usage: Usage | Any,
        *,
        purpose: str,
        batch: bool = False,
        phase: int | None = None,
        reported_cost_usd: float | None = None,
    ) -> dict:
        """Append one call to the ledger and return the stored entry.

        `reported_cost_usd` is the provider's own figure (e.g. `claude -p`'s costUSD), kept
        next to our list-price estimate for comparison.
        """
        if not isinstance(usage, Usage):
            usage = Usage.from_response(usage)
        eur = self.estimate_eur(model, usage, batch=batch)
        entry = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "phase": self.config.budget.current_phase if phase is None else phase,
            "purpose": purpose,
            "model": model,
            "billing": self.config.billing,
            "batch": batch,
            **asdict(usage),
            "total_tokens": usage.total_tokens,
            "cost_eur": None if eur is None else round(eur, 6),
            "reported_cost_usd": reported_cost_usd,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def summary(self, by: str = "phase") -> dict[Any, dict[str, float]]:
        """Calls, tokens and EUR, grouped by 'phase', 'model' or 'purpose'.

        `input_tokens` includes cache reads and writes; `cached_tokens` is cache reads only.
        """
        groups: dict[Any, dict[str, float]] = defaultdict(
            lambda: {
                "calls": 0,
                "input_tokens": 0,
                "cached_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_eur": 0.0,
            }
        )
        for e in self.entries():
            g = groups[e[by]]
            g["calls"] += 1
            g["input_tokens"] += (
                e["input_tokens"] + e["cache_read_input_tokens"] + e["cache_creation_input_tokens"]
            )
            g["cached_tokens"] += e["cache_read_input_tokens"]
            g["output_tokens"] += e["output_tokens"]
            g["total_tokens"] += e["total_tokens"]
            g["cost_eur"] += e["cost_eur"] or 0.0
        return dict(groups)

    def total_tokens(self) -> int:
        return sum(e["total_tokens"] for e in self.entries())

    def total_eur(self) -> float:
        return sum(e["cost_eur"] or 0.0 for e in self.entries())
