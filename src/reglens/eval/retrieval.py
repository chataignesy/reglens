"""Retrieval-only evaluation on the golden set (no LLM calls).

A retrieved chunk matches an expected citation when the source is the same and one
reference contains the other: expected "Art. 178(1)(b)" matches chunk "Art. 178(1)", and
expected "Art. 4(1)" matches chunk "Art. 4(1)(54)". Citations that are not article,
paragraph or recital references (e.g. "Foreword") are reported as not evaluable.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from reglens.config import PROJECT_ROOT
from reglens.eval.golden import GoldenItem
from reglens.retrieve.search import Filters, search

RESULTS_DIR = PROJECT_ROOT / "data" / "evals"


def normalize_refs(ref: str) -> list[str]:
    """'Art. 164(4), Table 1' -> ['art.164(4)']; 'paras. 36-37' -> ['para.36', 'para.37']."""
    full = ref.lower()
    # A numbered list in a PDF can restart in every section. Preserve the section in
    # Want, while normalizing its paragraph/range here for comparison with chunk refs.
    if re.match(r"^section\s+\d+(?:\.\d+)*,\s*paras?\.", full.strip()):
        full = full.split(",", 1)[1].strip()
    ref = full.split(",")[0].strip()
    m = re.match(r"paras?\.\s*(\d+)\s*-\s*(\d+)$", ref)
    if m:
        return [f"para.{n}" for n in range(int(m.group(1)), int(m.group(2)) + 1)]
    ref = re.sub(r"\s+", "", ref).replace("paras.", "para.")
    if re.match(r"^(art\.\d|para\.\d|recital\d|section\d)", ref):
        return [ref]
    # e.g. "Foreword, paras. 1-3": paragraph numbers after a part name
    m = re.search(r"paras?\.\s*(\d+)(?:\s*-\s*(\d+))?", full)
    if m:
        return [f"para.{n}" for n in range(int(m.group(1)), int(m.group(2) or m.group(1)) + 1)]
    return []


def refs_match(expected: str, got: str) -> bool:
    short, long = sorted((expected, got), key=len)
    return long == short or (long.startswith(short) and long[len(short)] == "(")


@dataclass
class ItemResult:
    id: str
    type: str
    expected: list[str]
    found_at: dict[str, int | None] = field(default_factory=dict)  # member -> rank (1-based)
    top: list[str] = field(default_factory=list)
    # expected citation -> its AND-groups (the citation, then each accepted alternative) as
    # the rank of every member: the same OR-over-AND structure as answer-level credit (S5)
    groups: dict[str, list[list[int | None]]] = field(default_factory=dict)

    def credit(self, at: int) -> float:
        """Mean over expected citations of the best group's share of members within `at`."""
        per = [
            max(sum(1 for r in g if r and r <= at) / len(g) for g in gs)
            for gs in self.groups.values()
            if gs
        ]
        return sum(per) / len(per) if per else 0.0

    def ranks(self) -> list[int]:
        return [r for gs in self.groups.values() for g in gs for r in g if r]


def evaluate(
    conn,
    items: list[GoldenItem],
    *,
    mode: str,
    k: int = 10,
    indexed: set[str],
    filters: Filters | None = None,
    **search_kwargs,
) -> dict:
    """`search_kwargs` go to `search()` (e.g. candidates=50) for tuning experiments."""
    filters = filters or Filters()
    results: list[ItemResult] = []
    skipped: list[str] = []
    for item in items:
        if item.type == "out_of_scope" or item.status != "verified":
            continue
        from reglens.eval.citations import groups, matches

        # each expected citation as OR over complete AND-groups (the citation's own members,
        # or all members of one accepted alternative), shared with answer-level credit (S5);
        # the document part must match when given (D6)
        wanted = [(c, groups(c)) for c in item.expected_citations if c.source in indexed]
        wanted = [(c, gs) for c, gs in wanted if gs]
        if not wanted:
            skipped.append(item.id)
            continue
        hits = search(conn, item.question, mode=mode, k=k, filters=filters, **search_kwargs)
        got = [
            (
                h.source_id,
                h.title,
                normalize_refs(h.ref)[0] if normalize_refs(h.ref) else h.ref,
                h.hierarchy,
            )
            for h in hits
        ]

        def rank(w, got=got) -> int | None:
            return next((i for i, g in enumerate(got, 1) if matches(w, *g)), None)

        res = ItemResult(
            item.id,
            item.type,
            [f"{w.source}:{w.ref}" for _, gs in wanted for w in gs[0]],
            top=[f"{s}:{r}" for s, _, r, _ in got],
        )
        for c, gs in wanted:
            res.groups[f"{c.source}:{c.ref}"] = [[rank(w) for w in g] for g in gs]
            for w in gs[0]:
                res.found_at[f"{w.source}:{w.ref}"] = rank(w)
        results.append(res)

    def recall(at: int) -> float:
        per_item = [x.credit(at) for x in results]
        return sum(per_item) / len(per_item) if per_item else 0.0

    def hit(at: int) -> float:
        return sum(any(r <= at for r in x.ranks()) for x in results) / max(len(results), 1)

    mrr = sum(1 / min(x.ranks(), default=float("inf")) for x in results) / max(len(results), 1)
    return {
        "mode": mode,
        "k": k,
        "items": len(results),
        "skipped_not_evaluable": skipped,
        "recall@5": round(recall(5), 3),
        "recall@10": round(recall(10), 3),
        "hit@5": round(hit(5), 3),
        "hit@10": round(hit(10), 3),
        "mrr@10": round(mrr, 3),
        "per_item": [asdict(x) for x in results],
    }


def save(results: list[dict]) -> str:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"retrieval-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return str(path.relative_to(PROJECT_ROOT))
