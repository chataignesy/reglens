"""Deterministic citation checks (no LLM): does each claim point at passages that support it?

Checks per claim, in order:
- no_citation         the claim cites nothing
- unknown_citation    it cites a passage number that was not in the context
- unsupported_number  a number in the claim (%, EUR, periods, ...) is in none of its cited passages
                      (numbers written as words count; numbers taken from the question are allowed)
- kind_mismatch       labelled "law" but cites no CRR/RTS passage
"""

from __future__ import annotations

import re
from decimal import Decimal

from reglens.answer.pipeline import Answer

_NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?![\w])")
LAW_LEVELS = {"L1", "L2"}


_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "twenty": "20",
}
# Number words only next to a period unit ('three months'), so 'Part Ten' or 'three categories'
# do not turn into numbers.
_WORD_RE = re.compile(r"\b(" + "|".join(_WORDS) + r")[\s-]+(?:day|week|month|year)s?\b", re.I)


def _norm_numbers(text: str) -> set[str]:
    """Numbers as canonical strings: '0,05 %' and '0.050%' -> '0.05'; 'three months' -> '3'."""
    out = {_WORDS[w.lower()] for w in _WORD_RE.findall(text)}
    for m in _NUM.finditer(text):
        d = Decimal(m.group(1).replace(",", ".")).normalize()
        out.add(format(d, "f"))
    return out


def check_answer(ans: Answer) -> dict:
    """Annotate each claim's `check` and return a summary."""
    passages = {f"C{i}": h for i, h in enumerate(ans.context, 1)}
    from_question = _norm_numbers(ans.question)  # e.g. the EUR 120 in a worked example
    counts: dict[str, int] = {}
    for claim in ans.claims:
        cited = [passages[c] for c in claim.citations if c in passages]
        if not claim.citations:
            claim.check = "no_citation"
        elif len(cited) < len(claim.citations):
            claim.check = "unknown_citation"
        else:
            available = set().union(*(_norm_numbers(h.text) for h in cited))
            missing = _norm_numbers(claim.text) - available - from_question
            if missing:
                claim.check = f"unsupported_number({', '.join(sorted(missing))})"
            elif claim.kind == "law" and not any(h.legal_level in LAW_LEVELS for h in cited):
                claim.check = "kind_mismatch"
            else:
                claim.check = "ok"
        key = claim.check.split("(")[0]
        counts[key] = counts.get(key, 0) + 1
    n = len(ans.claims)
    return {
        "claims": n,
        "ok": counts.get("ok", 0),
        "supported_rate": round(counts.get("ok", 0) / n, 3) if n else None,
        "problems": {k: v for k, v in counts.items() if k != "ok"},
    }
