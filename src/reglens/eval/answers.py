"""Answer-level evaluation on the golden set (deterministic metrics, no LLM judge yet).

Metrics per run:
- abstention accuracy: out-of-scope items abstain, in-scope items answer
- citation recall: share of expected citations (or accepted alternatives) the answer cites
- supported rate: share of claims passing the deterministic citation check
- tokens: from the provider usage of each call

Answers are cached in data/evals/answers/<prompt version>/<item id>.json, so re-running an
unchanged set costs no tokens; delete the folder (or bump PROMPT_VERSION) to re-ask.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from reglens.answer.pipeline import Answer, answer_question
from reglens.answer.prompts import SYSTEM
from reglens.answer.verify import check_answer
from reglens.config import PROJECT_ROOT, Config
from reglens.eval.golden import GoldenItem
from reglens.eval.retrieval import normalize_refs, refs_match

ANSWER_DIR = PROJECT_ROOT / "data" / "evals" / "answers"
PROMPT_VERSION = hashlib.sha256(SYSTEM.encode()).hexdigest()[:8]


def answer_version(agent: bool = False) -> str:
    """Cache namespace: the single-pass prompt hash, or 'agent-<hash of agent code>'."""
    if not agent:
        return PROMPT_VERSION
    from reglens.agent import run, tools

    src = run.AGENT_SYSTEM + open(tools.__file__, encoding="utf-8").read()
    src += open(run.__file__, encoding="utf-8").read()  # key resolution changes answers too
    repeat = int(os.environ.get("REGLENS_REPEAT", "1"))  # repeat runs get their own cache
    suffix = f"-r{repeat}" if repeat > 1 else ""
    return "agent-" + hashlib.sha256(src.encode()).hexdigest()[:8] + suffix


def _cited_refs(record: dict) -> list[tuple[str, str]]:
    ctx = record["context"]
    cited = {c for cl in record["claims"] for c in cl["citations"]}
    out = []
    for i, h in enumerate(ctx, 1):
        if f"C{i}" in cited:
            refs = normalize_refs(h["ref"])
            out.append((h["source_id"], refs[0] if refs else h["ref"]))
    return out


def citation_recall(item: GoldenItem, record: dict) -> float | None:
    cited = _cited_refs(record)
    wanted = [
        [(c.source, r) for r in normalize_refs(c.ref)]
        + [(a.source, r) for a in c.alternatives for r in normalize_refs(a.ref)]
        for c in item.expected_citations
    ]
    wanted = [w for w in wanted if w]
    if not wanted:
        return None
    found = sum(
        any(s == ws and refs_match(wr, r) for ws, wr in w for s, r in cited) for w in wanted
    )
    return found / len(wanted)


def run(
    conn,
    provider,
    config: Config,
    items: list[GoldenItem],
    *,
    log=print,
    agent: bool = False,
    routes: dict[str, str] | None = None,
) -> dict:
    """`routes` (item id -> 'agent' | 'single', from the router eval) picks the mode per item;
    each mode keeps its own cache, so routed runs reuse earlier single-pass and agent answers."""
    from reglens.agent.run import answer_agentic

    modes = {
        False: (ANSWER_DIR / answer_version(False), answer_question),
        True: (ANSWER_DIR / answer_version(True), answer_agentic),
    }
    version = "routed" if routes is not None else answer_version(agent)
    rows, new_tokens = [], 0
    for n, item in enumerate(items, 1):

        def answer(use_agent: bool, item: GoldenItem = item, n: int = n) -> dict:
            nonlocal new_tokens
            out_dir, answer_fn = modes[use_agent]
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{item.id}.json"
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
            ans: Answer = answer_fn(conn, provider, config, item.question)
            check = check_answer(ans)  # annotates claims first, so the record stores their checks
            record = ans.to_dict() | {"check": check, "id": item.id}
            path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            new_tokens += ans.usage_tokens
            log(f"  [{n}/{len(items)}] {item.id}: {ans.usage_tokens:,} tokens")
            return record

        use_agent = routes.get(item.id) == "agent" if routes is not None else agent
        record = answer(use_agent)
        mode = "agent" if use_agent else "single"
        if routes is not None and not use_agent and record.get("missing_info"):
            first = record.get("usage_tokens", 0)  # as in answer_routed: agent after a gap
            record = answer(True)
            record = record | {"usage_tokens": record.get("usage_tokens", 0) + first}
            mode = "fallback"
        oos = item.type == "out_of_scope"
        rows.append(
            {
                "id": item.id,
                "type": item.type,
                "mode": mode,
                "abstained": record["abstained"],
                "abstain_correct": record["abstained"] == oos,
                "citation_recall": None if oos else citation_recall(item, record),
                "supported_rate": record["check"]["supported_rate"],
                "tokens": record.get("usage_tokens", 0),
                "errors": record.get("errors", []),
            }
        )

    def mean(key, subset):
        vals = [r[key] for r in subset if r[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    ins = [r for r in rows if r["type"] != "out_of_scope"]
    oos = [r for r in rows if r["type"] == "out_of_scope"]
    summary = {
        "prompt_version": version,
        "model": config.model((config.answer or {}).get("tier", "dev")),
        "items": len(rows),
        "abstain_on_out_of_scope": round(sum(r["abstained"] for r in oos) / len(oos), 3)
        if oos
        else None,
        "answered_in_scope": round(sum(not r["abstained"] for r in ins) / len(ins), 3)
        if ins
        else None,
        "citation_recall": mean("citation_recall", ins),
        "supported_rate": mean("supported_rate", ins),
        "avg_tokens": round(sum(r["tokens"] for r in rows) / max(len(rows), 1)),
        "new_tokens_this_run": new_tokens,
        "errors": [r["id"] for r in rows if r["errors"]],
        "per_item": rows,
    }
    path = PROJECT_ROOT / "data" / "evals" / f"answers-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["file"] = str(path.relative_to(PROJECT_ROOT))
    return summary
