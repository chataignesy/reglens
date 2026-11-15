"""Load and validate the source registry (sources.yaml)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from reglens.config import PROJECT_ROOT

LEGAL_LEVELS = {"L1", "L2", "L3", "qa", "supervisory"}
APPLIES_TO = {"SI", "LSI", "all"}


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    issuer: str
    legal_level: str
    reference: str
    url: str | None
    format: str
    applies_to: str
    scope: list[str]
    reuse: str
    verify: bool
    celex: str | None = None
    consolidated: bool = False
    short_name: str | None = None
    articles: list[str] | None = None  # MVP scope filter, e.g. ["4", "107-241"]
    parts: list[str] | None = None  # PDF: unnumbered part headings (regexes)
    blocks: list[str] | None = None  # PDF: parts in MVP scope (regexes)
    search_default: bool = True  # False: only searched when explicitly requested
    published_on: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    application_from: str | None = None
    application_until: str | None = None
    temporal_verified: bool = False
    applicability: dict[str, list[str]] = field(default_factory=dict)

    def label(self) -> str:
        return self.short_name or self.title

    def in_scope(self, article: str | None) -> bool:
        """True if `article` (e.g. "122a") falls inside the `articles` filter (or no filter)."""
        if not self.articles or article is None:
            return True
        m = re.match(r"\d+", article)
        if not m:
            return False
        n = int(m.group())
        for spec in self.articles:
            lo, _, hi = spec.partition("-")
            if hi and int(lo) <= n <= int(hi):  # range: includes inserted articles like 122a
                return True
            if not hi and spec == article:  # single article: exact match
                return True
        return False


def load_sources(path: str | Path | None = None, *, conn=None) -> list[Source]:
    if path is None and conn is not None:
        from reglens.index.generations import metadata

        records = metadata(conn).get("sources")
        if records is not None:
            return [Source(**s) for s in records]
    path = Path(path or PROJECT_ROOT / "sources.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    from reglens.context import validate_metadata

    for record in raw["sources"]:
        record.update(validate_metadata(record))
    sources = [Source(**s) for s in raw["sources"]]

    ids = [s.id for s in sources]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate source ids: {sorted(dupes)}")
    for s in sources:
        if s.legal_level not in LEGAL_LEVELS:
            raise ValueError(f"{s.id}: unknown legal_level {s.legal_level!r}")
        if s.applies_to not in APPLIES_TO:
            raise ValueError(f"{s.id}: unknown applies_to {s.applies_to!r}")
    return sources
