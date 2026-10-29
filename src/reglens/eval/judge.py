"""LLM judge: is the answer correct against the golden `expected_answer`?

Cheap by design:
- bulk tier (Haiku) at low effort; the judge sees question, reference answer and RegLens answer
  only (no passages), so a call is ~1.5-2k tokens;
- no call where the outcome is deterministic: out-of-scope items (correct iff abstained) and
  in-scope abstentions (score 0);
- verdicts cached per (answer prompt version, judge prompt version, item id).

Scores: 2 = correct and covers the reference's key facts; 1 = partly correct (key facts missing,
or hedged where the reference is definite); 0 = wrong, contradicts the reference, or no answer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from reglens.config import PROJECT_ROOT, Config
from reglens.eval.answers import ANSWER_DIR, PROMPT_VERSION
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
JUDGE_DIR = PROJECT_ROOT / "data" / "evals" / "judge" / f"{PROMPT_VERSION}-{JUDGE_VERSION}"


def judge_prompt(item: GoldenItem, answer_text: str) -> str:
    return (
        f"Question:\n{item.question}\n\n"
        f"Reference answer:\n{item.expected_answer}\n\n"
        f"Answer to grade:\n{answer_text}"
    )


def _parse(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start : end + 1])
    score = int(data.get("score"))
    if score not in (0, 1, 2):
        raise ValueError(f"score out of range: {score}")
    return {
        "score": score,
        "missing": list(data.get("missing") or []),
        "contradictions": list(data.get("contradictions") or []),
        "rationale": str(data.get("rationale") or ""),
    }


def _load_answer(item_id: str) -> dict | None:
    path = ANSWER_DIR / PROMPT_VERSION / f"{item_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _ref_hash(item: GoldenItem) -> str:
    return hashlib.sha256(item.expected_answer.encode()).hexdigest()[:12]


def _cached(item: GoldenItem) -> dict | None:
    """Cached verdict, unless it was graded against a different reference answer."""
    path = JUDGE_DIR / f"{item.id}.json"
    if not path.exists():
        return None
    verdict = json.loads(path.read_text(encoding="utf-8"))
    stored = verdict.get("reference_hash")
    return verdict if stored in (None, _ref_hash(item)) else None


def plan(items: list[GoldenItem]) -> dict:
    """Which items need a judge call (for the dry-run estimate)."""
    needs, deterministic, cached, no_answer = [], [], [], []
    for item in items:
        rec = _load_answer(item.id)
        if rec is None:
            no_answer.append(item.id)
        elif _cached(item) is not None:
            cached.append(item.id)
        elif item.type == "out_of_scope" or rec["abstained"]:
            deterministic.append(item.id)
        else:
            needs.append(item.id)
    return {"needs_call": needs, "deterministic": deterministic, "cached": cached,
            "no_answer": no_answer}


def judge(provider: LLMProvider, config: Config, items: list[GoldenItem], *, log=print) -> dict:
    JUDGE_DIR.mkdir(parents=True, exist_ok=True)
    rows, new_tokens = [], 0
    for item in items:
        rec = _load_answer(item.id)
        if rec is None:
            continue
        path = JUDGE_DIR / f"{item.id}.json"
        verdict = _cached(item)
        if verdict is not None:
            pass
        elif item.type == "out_of_scope":
            verdict = {"score": 2 if rec["abstained"] else 0, "method": "deterministic",
                       "rationale": "out of scope: correct iff abstained", "tokens": 0}
        elif rec["abstained"]:
            verdict = {"score": 0, "method": "deterministic",
                       "rationale": "abstained on an in-scope question", "tokens": 0}
        else:
            answer_text = rec["answer"]
            try:
                c = provider.complete(judge_prompt(item, answer_text), purpose="judge",
                                      system=JUDGE_SYSTEM, tier="bulk", effort="low")
                verdict = _parse(c.text) | {"method": "llm", "model": c.model,
                                            "tokens": c.usage.total_tokens}
                new_tokens += c.usage.total_tokens
                log(f"  {item.id}: score {verdict['score']} ({c.usage.total_tokens:,} tokens)")
            except (LLMError, ValueError, json.JSONDecodeError) as e:
                log(f"  {item.id}: judge failed: {e}")
                continue  # not cached; a re-run retries
        verdict["reference_hash"] = _ref_hash(item)
        path.write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")
        rows.append({"id": item.id, "type": item.type} | verdict)

    def mean(subset):
        return round(sum(r["score"] for r in subset) / (2 * len(subset)), 3) if subset else None

    single = [r for r in rows if r["type"] not in ("multi_hop", "out_of_scope")]
    multi = [r for r in rows if r["type"] == "multi_hop"]
    in_scope = single + multi
    summary = {
        "answer_prompt": PROMPT_VERSION,
        "judge_prompt": JUDGE_VERSION,
        "judge_model": config.model("bulk"),
        "items": len(rows),
        "correctness_in_scope": mean(in_scope),  # mean score / 2
        "correctness_single": mean(single),
        "correctness_multi_hop": mean(multi),
        "fully_correct": sum(r["score"] == 2 for r in in_scope),
        "partly_correct": sum(r["score"] == 1 for r in in_scope),
        "wrong": sum(r["score"] == 0 for r in in_scope),
        "with_contradictions": [r["id"] for r in rows if r.get("contradictions")],
        "new_tokens": new_tokens,
        "per_item": rows,
    }
    out = PROJECT_ROOT / "data" / "evals" / f"judge-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["file"] = str(out.relative_to(PROJECT_ROOT))
    return summary
