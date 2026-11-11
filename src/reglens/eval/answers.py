"""Answer-level evaluation on the golden set (deterministic metrics; the LLM judge is separate).

Metrics per run:
- abstention accuracy: out-of-scope items abstain, in-scope items answer
- citation recall: credit per expected citation (ranges need all members, parts must match;
  see eval/citations.py)
- mechanical check pass rate: share of claims passing the deterministic citation checks
- tokens: every call, including the router and failed attempts

Caching (F4): answers live in data/evals/answers/<namespace>/<item id>-<question hash>.json,
where the namespace fingerprints the code, model, settings and corpus generation (see
eval/fingerprint.py), so a changed question, prompt, model or corpus is answered again.

Run manifests (D7): every run writes data/evals/runs/<run id>.json listing, per item, the exact
answer artifact (path + SHA-256), the route plan and every attempt. `reglens judge --run <id>`
grades exactly that manifest. Routed runs go through `answer.route.dispatch`, the same
fallback logic the app uses.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from reglens.answer.pipeline import Answer, answer_question
from reglens.answer.route import ROUTER_VERSION, dispatch, gate_abstains
from reglens.answer.verify import check_answer
from reglens.config import PROJECT_ROOT, Config
from reglens.eval.citations import credit
from reglens.eval.fingerprint import namespace, question_hash
from reglens.eval.golden import GoldenItem
from reglens.eval.retrieval import normalize_refs
from reglens.llm.provider import LLMError

ANSWER_DIR = PROJECT_ROOT / "data" / "evals" / "answers"
RUNS_DIR = PROJECT_ROOT / "data" / "evals" / "runs"


def answer_version(config: Config, conn, agent: bool = False) -> str:
    """Cache namespace of one answering mode (see eval/fingerprint.py)."""
    opts = dict(config.answer or {})
    if agent:
        opts |= dict(config.agent or {})
    model = config.model(opts.get("tier", "dev"))
    repeat = int(os.environ.get("REGLENS_REPEAT", "1"))  # repeat runs get their own cache
    suffix = f"-r{repeat}" if repeat > 1 and agent else ""
    return namespace("agent" if agent else "single", conn, model, opts, suffix)


def artifact_name(item: GoldenItem) -> str:
    return f"{item.id}-{question_hash(item.question)}.json"


def file_sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cited(record: dict) -> list[tuple[str, str | None, str]]:
    """(source, part, normalised ref) of every passage the answer cites."""
    cited = {c for cl in record["claims"] for c in cl["citations"]}
    out = []
    for i, h in enumerate(record["context"], 1):
        if f"C{i}" in cited:
            refs = normalize_refs(h["ref"])
            out.append((h["source_id"], h.get("title"), refs[0] if refs else h["ref"]))
    return out


def citation_recall(item: GoldenItem, record: dict) -> float | None:
    got = _cited(record)
    scores = [s for c in item.expected_citations if (s := credit(c, got)) is not None]
    return sum(scores) / len(scores) if scores else None


def run(
    conn,
    provider,
    config: Config,
    items: list[GoldenItem],
    *,
    log=print,
    agent: bool = False,
    routes: dict[str, dict] | None = None,
    label: str = "",
    dataset: dict | None = None,
) -> dict:
    """`routes` (item id -> cached router record) makes this a routed run; otherwise every item
    is answered single-pass, or by the agent with `agent=True`. Writes a run manifest."""
    import re
    from dataclasses import asdict

    from reglens.agent.run import answer_agentic
    from reglens.eval.artifacts import digest
    from reglens.eval.snapshots import items_from_payload, payload

    if label and not re.fullmatch(r"[A-Za-z0-9_-]+", label):
        raise ValueError("Run label must contain only letters, numbers, underscores or dashes")
    frozen = dataset if dataset is not None else payload(items)
    by_id = {i.id: asdict(i) for i in items_from_payload(frozen)}
    if any(by_id.get(i.id) != asdict(i) for i in items):
        raise ValueError("Selected items differ from frozen references")

    modes = {
        "single": (ANSWER_DIR / answer_version(config, conn, False), answer_question),
        "agent": (ANSWER_DIR / answer_version(config, conn, True), answer_agentic),
    }
    kind = "routed" if routes is not None else ("agent" if agent else "single")
    rows, entries, new_tokens = [], [], 0
    for n, item in enumerate(items, 1):

        def answer(mode: str, item: GoldenItem = item, n: int = n) -> dict:
            nonlocal new_tokens
            out_dir, answer_fn = modes[mode]
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / artifact_name(item)
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
            try:
                ans: Answer = answer_fn(conn, provider, config, item.question)
            except LLMError as e:  # one failed item must not stop the run: record it
                ans = Answer(item.question, False, "", "", [], [], "", errors=[str(e)])
            check = check_answer(ans)  # annotates claims first, so the record stores them
            record = ans.to_dict() | {"check": check, "id": item.id, "mode": mode}
            path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            new_tokens += ans.usage_tokens
            log(f"  [{n}/{len(items)}] {item.id} ({mode}): {ans.usage_tokens:,} tokens")
            return record

        if routes is not None and not gate_abstains(conn, config, item.question):
            r = routes.get(item.id) or {"route": "single", "reason": "no cached route"}
            record, outcome = dispatch(
                r["route"],
                r.get("reason", ""),
                int(r.get("tokens", 0)),
                single=lambda: answer("single"),
                agent=lambda: answer("agent"),
            )
        else:  # plain run, or the retrieval gate abstains (no router call, as in the app)
            mode = "agent" if (agent and routes is None) else "single"
            record = answer(mode)
            outcome = {
                "planned": mode,
                "route": mode,
                "reason": "",
                "attempts": [mode],
                "router_tokens": 0,
                "tokens": int(record.get("usage_tokens") or 0),
            }
        path = modes[outcome["route"]][0] / artifact_name(item)
        entries.append(
            {"id": item.id, "type": item.type, "question_sha": question_hash(item.question)}
            | outcome
            | {
                "artifact": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "artifact_sha256": file_sha(path),
                "errors": record.get("errors", []),
                "unverified": bool(record.get("unverified")),
            }
        )
        oos = item.type == "out_of_scope"
        # R3: three separate signals: scope (did it answer what it should?), claim support
        # (the mechanical checks) and completeness (does the answer report gaps?)
        if oos:
            scope = "declined" if record["abstained"] else "answered_out_of_scope"
        else:
            scope = "declined_in_scope" if record["abstained"] else "answered"
        incomplete = not record["abstained"] and (
            bool(record.get("missing_info")) or bool(record.get("partial_cids"))
        )
        rows.append(
            {
                "id": item.id,
                "type": item.type,
                "route": outcome["route"],
                "attempts": outcome["attempts"],
                "scope": scope,
                "reports_incomplete": incomplete,
                "abstained": record["abstained"],
                "abstain_correct": record["abstained"] == oos,
                "citation_recall": None if oos else citation_recall(item, record),
                "check_pass_rate": record["check"]["supported_rate"],
                "tokens": outcome["tokens"],
                "errors": record.get("errors", []),
            }
        )

    def mean(key, subset):
        vals = [r[key] for r in subset if r[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    ins = [r for r in rows if r["type"] != "out_of_scope"]
    oos = [r for r in rows if r["type"] == "out_of_scope"]
    run_id = f"{datetime.now():%Y%m%d-%H%M%S-%f}-{kind}" + (f"-{label}" if label else "")
    summary = {
        "run_id": run_id,
        "kind": kind,
        "model": config.model((config.answer or {}).get("tier", "dev")),
        "items": len(rows),
        "abstain_on_out_of_scope": round(sum(r["abstained"] for r in oos) / len(oos), 3)
        if oos
        else None,
        "answered_in_scope": round(sum(not r["abstained"] for r in ins) / len(ins), 3)
        if ins
        else None,
        "scope_compliance": round(sum(r["abstain_correct"] for r in rows) / len(rows), 3)
        if rows
        else None,
        "answered_out_of_scope": [r["id"] for r in oos if r["scope"] == "answered_out_of_scope"],
        "citation_recall": mean("citation_recall", ins),
        "check_pass_rate": mean("check_pass_rate", ins),
        "reports_incomplete": [r["id"] for r in ins if r["reports_incomplete"]],
        "avg_tokens": round(sum(r["tokens"] for r in rows) / max(len(rows), 1)),
        "total_tokens": sum(r["tokens"] for r in rows),
        "new_tokens_this_run": new_tokens,
        "errors": [r["id"] for r in rows if r["errors"]],
        "per_item": rows,
    }
    manifest = {
        "run_id": run_id,
        "kind": kind,
        "created": datetime.now().isoformat(timespec="seconds"),
        "namespaces": {m: d.name for m, (d, _) in modes.items()},
        "router_version": ROUTER_VERSION if routes is not None else None,
        "dataset": {"sha256": digest(frozen), "snapshot": frozen},
        "items": entries,
        "summary": {k: v for k, v in summary.items() if k != "per_item"},
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{run_id}.json"
    with path.open("x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    summary["file"] = str(path.relative_to(PROJECT_ROOT))
    return summary


def load_run(run_id: str = "latest") -> dict:
    """A run manifest by id, or the most recent one."""
    if run_id == "latest":
        runs = sorted(
            (p for p in RUNS_DIR.glob("*.json") if ".judge-" not in p.name),
            key=lambda p: p.stat().st_mtime,
        )
        if not runs:
            raise FileNotFoundError("no eval runs yet: run `reglens eval-answers` first")
        return json.loads(runs[-1].read_text(encoding="utf-8"))
    path = RUNS_DIR / f"{run_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))
