"""Structured citation matching for the evals (review 2026-11-08: D6).

An expected citation is an OR of AND-groups:
- the citation itself, where a range ("paras. 71-73") requires ALL its members, or
- any accepted alternative (itself possibly a range).
A citation's document part ("Foreword, para. 1" in the ECB guide, whose paragraph numbering
restarts per part) must match the part of the cited passage. A citation without a part
matches any part; the golden set test checks such citations are unambiguous in the corpus.

Credit for one expected citation = the best group's share of members found, so citing
para. 71 of an expected "paras. 71-73" earns 1/3, not 1.
"""

from __future__ import annotations

from dataclasses import dataclass

from reglens.eval.golden import Citation
from reglens.eval.retrieval import normalize_refs, refs_match

_REF_START = ("art", "para", "recital", "section", "q&a", "background")


@dataclass(frozen=True)
class Want:
    source: str
    part: str | None  # lower-case part name, e.g. "foreword"
    ref: str  # normalised, e.g. "para.1" or "art.178(1)"


def part_of(ref: str) -> str | None:
    """'Foreword, paras. 1-3' -> 'foreword'; 'Art. 164(4), Table 1' -> None."""
    head = ref.split(",")[0].strip().lower()
    if "," not in ref or head.startswith(_REF_START):
        return None
    return head


def groups(c: Citation) -> list[list[Want]]:
    """OR over AND-groups: [all members of the citation], [all members of alternative 1], …"""
    out = []
    for x in (c, *c.alternatives):
        members = [Want(x.source, part_of(x.ref), r) for r in normalize_refs(x.ref)]
        if members:
            out.append(members)
    return out


def matches(w: Want, source: str, part: str | None, ref: str) -> bool:
    if w.source != source or not refs_match(w.ref, ref):
        return False
    return w.part is None or (part or "").strip().lower() == w.part


def credit(c: Citation, got: list[tuple[str, str | None, str]]) -> float | None:
    """Share of the citation found in `got` [(source, part, normalised ref)], best group."""
    gs = groups(c)
    if not gs:
        return None
    return max(sum(any(matches(w, *g) for g in got) for w in grp) / len(grp) for grp in gs)
