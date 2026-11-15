"""Paired 14-case routing/quality check; 3M total reserve. Live mode needs budget approval."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from run_codex_completeness8 import main

from reglens.config import PROJECT_ROOT

COHORT = PROJECT_ROOT / "evals/cohorts/handoff-remaining14-2026-11-14.json"
IDS = set(json.loads(COHORT.read_text(encoding="utf-8"))["ids"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--arm", choices=["llm", "single_first"])
    args = parser.parse_args()
    if args.arm:
        sys.argv = [sys.argv[0], *(["--live"] if args.live else [])]
        main(cohort_ids=IDS, label=f"handoff14-{args.arm}", allowance=1_500_000,
             strategy=args.arm)
    else:
        for arm in ["llm", "single_first"]:
            command = [sys.executable, str(Path(__file__).resolve()), "--arm", arm]
            if args.live:
                command.append("--live")
            result = subprocess.run(command, check=False)
            if result.returncode:
                raise SystemExit(result.returncode)
