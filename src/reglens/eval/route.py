"""Router eval: does the Haiku router send multi-hop and comparison questions to the agent and
everything else to single-pass? Out-of-scope items are skipped (the retrieval gate handles
them). Decisions are cached per (router prompt version, item id).
"""

from __future__ import annotations

import json
from datetime import datetime

from reglens.answer.route import ROUTER_VERSION, route_question
from reglens.config import PROJECT_ROOT
from reglens.eval.golden import GoldenItem
from reglens.llm.provider import LLMProvider

ROUTE_DIR = PROJECT_ROOT / "data" / "evals" / "routes" / ROUTER_VERSION
AGENT_TYPES = ("multi_hop", "comparison")


def expected_route(item: GoldenItem) -> str:
    return "agent" if item.type in AGENT_TYPES else "single"


def routable(items: list[GoldenItem]) -> list[GoldenItem]:
    return [i for i in items if i.type != "out_of_scope"]


def cached_routes() -> dict[str, str]:
    """item id -> route, for every cached decision of the current router version."""
    out = {}
    for p in ROUTE_DIR.glob("*.json"):
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))["route"]
    return out


def run(provider: LLMProvider, items: list[GoldenItem], *, log=print) -> dict:
    ROUTE_DIR.mkdir(parents=True, exist_ok=True)
    rows, new_tokens = [], 0
    for n, item in enumerate(routable(items), 1):
        path = ROUTE_DIR / f"{item.id}.json"
        if path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
        else:
            route, reason, tokens = route_question(provider, item.question)
            rec = {"route": route, "reason": reason, "tokens": tokens}
            path.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
            new_tokens += tokens
            log(f"  [{n}] {item.id}: {route} ({tokens:,} tokens)")
        rows.append(rec | {"id": item.id, "type": item.type, "expected": expected_route(item)})

    def count(route, expected):
        return sum(r["route"] == route and r["expected"] == expected for r in rows)

    agent_exp = sum(r["expected"] == "agent" for r in rows)
    agent_got = sum(r["route"] == "agent" for r in rows)
    summary = {
        "router_version": ROUTER_VERSION,
        "items": len(rows),
        "accuracy": round(sum(r["route"] == r["expected"] for r in rows) / len(rows), 3)
        if rows
        else None,
        "agent_recall": round(count("agent", "agent") / agent_exp, 3) if agent_exp else None,
        "agent_precision": round(count("agent", "agent") / agent_got, 3) if agent_got else None,
        "confusion": {
            f"{e}->{g}": count(g, e) for e in ("single", "agent") for g in ("single", "agent")
        },
        "new_tokens_this_run": new_tokens,
        "misrouted": [
            {k: r[k] for k in ("id", "type", "route", "reason")}
            for r in rows
            if r["route"] != r["expected"]
        ],
    }
    path = PROJECT_ROOT / "data" / "evals" / f"routes-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(summary | {"per_item": rows}, indent=2), encoding="utf-8")
    summary["path"] = str(path)
    return summary
