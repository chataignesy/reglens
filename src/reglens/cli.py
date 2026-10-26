"""Command line: `reglens cost` and `reglens estimate`."""

from __future__ import annotations

import argparse

from reglens.config import load_config
from reglens.llm.ledger import Ledger, Usage


def _cmd_cost(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    ledger = Ledger(cfg)
    rows = ledger.summary(by=args.by)
    budget = cfg.budget

    print(f"{args.by:<24}{'calls':>8}{'in tok':>12}{'out tok':>12}{'EUR':>10}")
    for key in sorted(rows, key=str):
        r = rows[key]
        print(
            f"{str(key):<24}{r['calls']:>8}{r['input_tokens']:>12,}"
            f"{r['output_tokens']:>12,}{r['cost_eur']:>10.2f}"
        )

    total = ledger.total_eur()
    phase = budget.current_phase
    phase_spent = ledger.summary(by="phase").get(phase, {}).get("cost_eur", 0.0)
    phase_budget = budget.phases_eur.get(phase, 0.0)
    print()
    print(
        f"Total: EUR {total:.2f} of target {budget.target_eur:.0f}"
        f" (ceiling {budget.ceiling_eur:.0f})"
    )
    print(f"Phase {phase}: EUR {phase_spent:.2f} of EUR {phase_budget:.0f}")
    if total > budget.ceiling_eur:
        print("!! Over the hard ceiling — stop paid runs.")
    elif total > budget.target_eur or phase_spent > phase_budget:
        print("! Over budget target — review before more paid runs.")


def _cmd_estimate(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    model = args.model or cfg.model(args.tier)
    usage = Usage(input_tokens=args.input, output_tokens=args.output)
    per_call = Ledger(cfg).estimate_eur(model, usage, batch=args.batch)
    total = per_call * args.calls
    print(f"{model}: EUR {per_call:.4f} per call x {args.calls} = EUR {total:.2f}")
    if total > cfg.budget.approval_threshold_eur:
        print(f"Above EUR {cfg.budget.approval_threshold_eur:.0f} — needs approval before running.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="reglens")
    parser.add_argument("--config", help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    cost = sub.add_parser("cost", help="summarise API spend from the ledger")
    cost.add_argument("--by", choices=["phase", "model", "purpose"], default="phase")
    cost.set_defaults(func=_cmd_cost)

    est = sub.add_parser("estimate", help="estimate the cost of a planned run")
    est.add_argument("--tier", choices=["bulk", "dev", "milestone"])
    est.add_argument("--model", help="explicit model ID (overrides --tier)")
    est.add_argument("--input", type=int, required=True, help="input tokens per call")
    est.add_argument("--output", type=int, required=True, help="output tokens per call")
    est.add_argument("--calls", type=int, default=1)
    est.add_argument("--batch", action="store_true", help="apply Batch API discount")
    est.set_defaults(func=_cmd_estimate)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
