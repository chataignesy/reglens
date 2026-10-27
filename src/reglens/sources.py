"""Load and validate the source registry (sources.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
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


def load_sources(path: str | Path | None = None) -> list[Source]:
    path = Path(path or PROJECT_ROOT / "sources.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
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
