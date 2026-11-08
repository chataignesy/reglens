"""Citation keys: the human-readable identity of a citable unit, e.g. "CRR Art. 178(1)".

One key per logical unit (source, kind, article/block, paragraph, point), shared by its window
parts and unnumbered continuations. Where a plain key would name more than one unit (paragraph
numbering that restarts per section in a PDF), it is qualified by the section, e.g.
"ECB validation reporting instructions, Section 2.5.1, para. 1". Keys are assigned once per
source at chunk-build time and stored with the chunk, so lookups are exact.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from functools import lru_cache
from typing import TYPE_CHECKING

from reglens.sources import Source, load_sources

if TYPE_CHECKING:
    from reglens.ingest.chunks import Chunk


@lru_cache(maxsize=1)
def _sources() -> dict[str, Source]:
    return {s.id: s for s in load_sources()}


def citation_key(source_id: str, ref: str, title: str | None, kind: str) -> str:
    """The plain key, before any qualification for duplicates."""
    s = _sources()[source_id]
    if kind == "qa":
        return f"{s.label()} {ref.removeprefix('Q&A ')}"  # "EBA Q&A 2014_1297"
    if s.parts and title and kind in ("paragraph", "section"):
        return f"{s.label()}, {title}, {ref}"  # ECB guide: numbering restarts per part
    return f"{s.label()} {ref}"


def unit_of(c: Chunk) -> tuple:
    """Logical unit: windows (#n) and continuations (~n) of one reference share it. PDF prose
    referenced by its section number is one unit even across a numbering-block boundary."""
    block = c.article
    if c.kind in ("section", "background") and not (c.paragraph or "").isdigit():
        block = None
    return (c.source_id, c.kind, block, c.paragraph or None, c.point or None)


_SECTION = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")


def _section(c: Chunk) -> str | None:
    """Number of the deepest numbered heading, e.g. '2.5.1'."""
    for h in reversed(c.hierarchy):
        if m := _SECTION.match(h):
            return m.group(1)
    return None


def assign_cites(chunks: Iterable[Chunk]) -> None:
    """Set `chunk.cite` for one source's chunks; every key maps to exactly one unit."""
    chunks = list(chunks)
    by_key: dict[str, dict[tuple, list]] = defaultdict(lambda: defaultdict(list))
    for c in chunks:
        by_key[citation_key(c.source_id, c.ref, c.title, c.kind)][unit_of(c)].append(c)
    for key, units in by_key.items():
        if len(units) == 1:
            for c in next(iter(units.values())):
                c.cite = key
            continue
        label = _sources()[next(iter(units))[0]].label()
        rest = key[len(label) :].lstrip(", ").strip()
        named = {}
        for unit, cs in units.items():
            sec = _section(cs[0])
            named[unit] = f"{label}, Section {sec}, {rest}" if sec else f"{label}, {rest}"
        counts = defaultdict(int)
        for name in named.values():
            counts[name] += 1
        for unit, cs in units.items():
            name = named[unit]
            if counts[name] > 1:  # same section too: fall back to the numbering block
                block = unit[2] or ""
                n = int(block[1:]) + 1 if re.fullmatch(r"b\d+", block) else block
                name = f"{name.rsplit(', ', 1)[0]}, list {n}, {rest}"
            for c in cs:
                c.cite = name
