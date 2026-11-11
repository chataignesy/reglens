"""LLM judge: is the answer correct against the golden `expected_answer`?

It grades one *run manifest* (see eval/answers.py): exactly the answer artifact each item
ended with in that run, routed or not, so a headline score is reproducible from its run id.

Cheap by design:
- bulk tier (Haiku) at low effort; the judge sees question, reference answer and RegLens answer
  only (no passages), so a call is ~1.5-2k tokens;
- no call where the outcome is deterministic: out-of-scope items (correct iff abstained),
  in-scope abstentions and answers without verified text (score 0);
- verdicts cached by content (F4): judge prompt and model, question, reference and the graded
  answer text. A regenerated answer is graded again; an unchanged one is not.

Scores: 2 = correct and covers the reference's key facts; 1 = partly correct (key facts missing,
or hedged where the reference is definite); 0 = wrong, contradicts the reference, or no answer.
"""

from __future__ import annotations

import hashlib
import json
import re

from reglens.config import PROJECT_ROOT, Config
from reglens.eval.answers import RUNS_DIR, file_sha
from reglens.eval.fingerprint import question_hash
from reglens.eval.golden import GoldenItem
from reglens.llm.provider import LLMError, LLMProvider

JUDGE_SYSTEM = """\
You grade answers about EU credit risk regulation against a reference answer written by a
domain expert. Judge substance, not style or length.

Score:
2 = correct and contains every key fact of the reference (numbers, conditions, articles may be
    phrased differently); extra correct detail is fine.
1 = partly correct: some key facts missing, or hedged/uncertain where the reference is definite.
0 = wrong: contradicts the reference on a key fact, or does not answer the question.

Reply with ONE JSON object and nothing else:
{"score": 2, "missing": ["key facts from the reference that are absent"],
 "contradictions": ["statements that conflict with the reference"], "rationale": "one sentence"}
"""

JUDGE_VERSION = hashlib.sha256(JUDGE_SYSTEM.encode()).hexdigest()[:8]
JUDGE_DIR = PROJECT_ROOT / "data" / "evals" / "judge" / "by-content"


def judge_prompt(item: GoldenItem, answer_text: str) -> str:
    return (
        f"Question:\n{item.question}\n\n"
        f"Reference answer:\n{item.expected_answer}\n\n"
        f"Answer to grade:\n{answer_text}"
    )


def verdict_key(item: GoldenItem, answer_text: str, model: str) -> str:
    raw = "|".join([JUDGE_VERSION, model, item.question, item.expected_answer, answer_text])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _parse(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start : end + 1])
    score = int(data.get("score"))
    if score not in (0, 1, 2):
        raise ValueError(f"score out of range: {score}")
    verdict = {
        "score": score,
        "missing": list(data.get("missing") or []),
        "contradictions": list(data.get("contradictions") or []),
        "rationale": str(data.get("rationale") or ""),
    }
    return verdict | {"flags": consistency_flags(verdict)}


_SHOULD_BE = re.compile(r"\bshould (?:be|score|get|receive)\s+(?:a\s+)?([012])\b", re.I)


def consistency_flags(v: dict) -> list[str]:
    """Where a verdict disagrees with itself (review R2). The raw score is kept; flagged
    verdicts are listed in the run report for a manual check, never silently rewritten."""
    flags = []
    if v["score"] == 2 and v["missing"]:
        flags.append("score 2 but key facts listed as missing")
    if v["score"] >= 1 and v["contradictions"]:
        flags.append(f"score {v['score']} but contradictions listed")
    if v["score"] == 0 and not v["missing"] and not v["contradictions"]:
        flags.append("score 0 without missing facts or contradictions")
    said = {int(m) for m in _SHOULD_BE.findall(v["rationale"])}
    if said and v["score"] not in said:
        flags.append(f"rationale says the score should be {'/'.join(map(str, sorted(said)))}")
    return flags


def _artifact(entry: dict) -> tuple[dict | None, str]:
    """(answer record, problem). The record must be the exact bytes the run recorded."""
    path = PROJECT_ROOT / entry["artifact"]
    if not path.exists():
        return None, "answer artifact missing"
    if file_sha(path) != entry["artifact_sha256"]:
        return None, "answer artifact changed since the run"
    return json.loads(path.read_text(encoding="utf-8")), ""


def _run_answer(item: GoldenItem, entry: dict | None) -> tuple[dict | None, str]:
    """The run's answer for `item`, or a problem. Second review S6: the run must have answered
    this question text, not an earlier wording kept under the same id."""
    if entry is None:
        return None, "not in run"
    if entry.get("question_sha") and entry["question_sha"] != question_hash(item.question):
        return None, "question changed since the run (regrade needs a new run)"
    rec, problem = _artifact(entry)
    if rec is not None and rec.get("question") and (
        question_hash(str(rec["question"])) != question_hash(item.question)
    ):
        return None, "answer is for a different question text"
    return rec, problem


def _deterministic(item: GoldenItem, rec: dict) -> dict | None:
    if item.type == "out_of_scope":
        return {"score": 2 if rec["abstained"] else 0, "method": "deterministic",
                "rationale": "out of scope: correct iff abstained"}
    if rec["abstained"]:
        return {"score": 0, "method": "deterministic",
                "rationale": "abstained on an in-scope question"}
    if rec.get("unverified") or not str(rec.get("answer") or "").strip():
        return {"score": 0, "method": "deterministic",
                "rationale": "no verified answer: " + "; ".join(rec.get("errors") or [])}
    return None


def plan(manifest: dict, items: list[GoldenItem], model: str) -> dict:
    """Which items need a judge call (for the dry-run estimate)."""
    from reglens.eval.snapshots import run_items

    items = run_items(manifest, items)
    by_id = {e["id"]: e for e in manifest["items"]}
    needs, deterministic, cached, problems = [], [], [], []
    for item in items:
        rec, problem = _run_answer(item, by_id.get(item.id))
        if rec is None:
            problems.append(f"{item.id}: {problem}")
        elif _deterministic(item, rec) is not None:
            deterministic.append(item.id)
        elif (JUDGE_DIR / f"{verdict_key(item, rec['answer'], model)}.json").exists():
            cached.append(item.id)
        else:
            needs.append(item.id)
    return {"needs_call": needs, "deterministic": deterministic, "cached": cached,
            "problems": problems}


def judge(
    provider: LLMProvider, config: Config, manifest: dict, items: list[GoldenItem], *, log=print
) -> dict:
    JUDGE_DIR.mkdir(parents=True, exist_ok=True)
    model = config.model("bulk")
    from reglens.eval.snapshots import run_items

    items = run_items(manifest, items)
    by_id = {e["id"]: e for e in manifest["items"]}
    from reglens.eval.artifacts import adjudications

    reviews = adjudications()
    rows, new_tokens, problems = [], 0, []
    for item in items:
        entry = by_id.get(item.id)
        rec, problem = _run_answer(item, entry)
        if rec is None:
            problems.append(f"{item.id}: {problem}")
            continue
        verdict = _deterministic(item, rec)
        if verdict is None:
            path = JUDGE_DIR / f"{verdict_key(item, rec['answer'], model)}.json"
            if path.exists():
                verdict = json.loads(path.read_text(encoding="utf-8"))
                verdict.setdefault("flags", consistency_flags(verdict))
            else:
                try:
                    c = provider.complete(judge_prompt(item, rec["answer"]), purpose="judge",
                                          system=JUDGE_SYSTEM, tier="bulk", effort="low")
                    verdict = _parse(c.text) | {"method": "llm", "model": c.model,
                                                "tokens": c.usage.total_tokens}
                    new_tokens += c.usage.total_tokens
                    log(f"  {item.id}: score {verdict['score']} ({c.usage.total_tokens:,} tokens)")
                except (LLMError, ValueError, json.JSONDecodeError) as e:
                    log(f"  {item.id}: judge failed: {e}")
                    problems.append(f"{item.id}: judge failed")
                    continue  # not cached; a re-run retries
                path.write_text(json.dumps(verdict, indent=2, ensure_ascii=False), "utf-8")
        rows.append({"id": item.id, "type": item.type, "route": entry["route"]} | verdict)

    def mean(subset):
        return round(sum(r["score"] for r in subset) / (2 * len(subset)), 3) if subset else None

    single = [r for r in rows if r["type"] not in ("multi_hop", "out_of_scope")]
    multi = [r for r in rows if r["type"] == "multi_hop"]
    in_scope = single + multi
    oos = [r for r in rows if r["type"] == "out_of_scope"]
    summary = {
        "run_id": manifest["run_id"],
        "judge_prompt": JUDGE_VERSION,
        "judge_model": model,
        "items": len(rows),
        "problems": problems,  # items of the run that could not be graded
        "correctness_in_scope": mean(in_scope),  # mean score / 2
        "correctness_single": mean(single),
        "correctness_multi_hop": mean(multi),
        "fully_correct": sum(r["score"] == 2 for r in in_scope),
        "partly_correct": sum(r["score"] == 1 for r in in_scope),
        "wrong": sum(r["score"] == 0 for r in in_scope),
        "out_of_scope_declined": f"{sum(r['score'] == 2 for r in oos)}/{len(oos)}",
        "with_contradictions": [r["id"] for r in rows if r.get("contradictions")],
        # R2: verdicts that disagree with themselves; check these by hand before quoting a score
        "inconsistent_verdicts": {r["id"]: r["flags"] for r in rows if r.get("flags")},
        "practitioner_reviews": {entry["id"]: reviews[entry["artifact_sha256"]]
                                 for entry in manifest["items"]
                                 if entry["artifact_sha256"] in reviews},
        "reference_basis": "frozen" if manifest.get("dataset") else "legacy_current",
        "new_tokens": new_tokens,
        "per_item": rows,
    }
    out = RUNS_DIR / f"{manifest['run_id']}.judge-{JUDGE_VERSION}.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["file"] = str(out.relative_to(PROJECT_ROOT))
    return summary
