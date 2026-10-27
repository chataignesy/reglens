"""Golden evaluation set: one JSON object per line in evals/golden/*.jsonl.

See evals/golden/README.md for the field guide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.sources import APPLIES_TO, load_sources

GOLDEN_DIR = PROJECT_ROOT / "evals" / "golden"
TYPES = {"factual", "multi_hop", "comparison", "applicability", "out_of_scope"}
STATUSES = {"draft", "verified"}
DIFFICULTIES = {"easy", "medium", "hard"}


@dataclass(frozen=True)
class Citation:
    source: str  # id in sources.yaml
    ref: str  # e.g. "Art. 178(1)(b)" or "para. 23"


@dataclass(frozen=True)
class GoldenItem:
    id: str
    question: str
    type: str
    expected_answer: str
    expected_citations: list[Citation]
    applies_to: str
    topic: str
    difficulty: str
    author: str
    status: str
    notes: str = ""
    tags: list[str] = field(default_factory=list)


def _parse(raw: dict, where: str, source_ids: set[str]) -> GoldenItem:
    raw = dict(raw)
    raw["expected_citations"] = [Citation(**c) for c in raw.get("expected_citations", [])]
    item = GoldenItem(**raw)
    errors = []
    if item.type not in TYPES:
        errors.append(f"type {item.type!r} not in {sorted(TYPES)}")
    if item.status not in STATUSES:
        errors.append(f"status {item.status!r} not in {sorted(STATUSES)}")
    if item.difficulty not in DIFFICULTIES:
        errors.append(f"difficulty {item.difficulty!r} not in {sorted(DIFFICULTIES)}")
    if item.applies_to not in APPLIES_TO:
        errors.append(f"applies_to {item.applies_to!r} not in {sorted(APPLIES_TO)}")
    if item.type == "out_of_scope" and item.expected_citations:
        errors.append("out_of_scope items must have no expected_citations")
    if item.type != "out_of_scope" and not item.expected_citations:
        errors.append("in-scope items need at least one expected citation")
    unknown = [c.source for c in item.expected_citations if c.source not in source_ids]
    if unknown:
        errors.append(f"unknown source ids {unknown}")
    if errors:
        raise ValueError(f"{where} ({item.id}): " + "; ".join(errors))
    return item


def load_golden(paths: list[Path] | None = None) -> list[GoldenItem]:
    paths = paths or sorted(GOLDEN_DIR.glob("*.jsonl"))
    source_ids = {s.id for s in load_sources()}
    items: list[GoldenItem] = []
    for path in paths:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                items.append(_parse(json.loads(line), f"{path.name}:{n}", source_ids))
    ids = [i.id for i in items]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"Duplicate golden ids: {dupes}")
    return items
