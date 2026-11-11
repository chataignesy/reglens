"""Planted gaps (the answer key in docs/synthetic-policy/gaps.yaml) and their links to the
obligation register. A gap's `refs` are citation keys; a ref also covers its sub-paragraphs
("CRR Art. 191" links obligations keyed "CRR Art. 191(1)")."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from reglens.config import PROJECT_ROOT
from reglens.gap.register import Obligation, id_lookup

GAPS_FILE = PROJECT_ROOT / "docs" / "synthetic-policy" / "gaps.yaml"
POLICY_FILE = PROJECT_ROOT / "docs" / "synthetic-policy" / "model-validation-policy.md"
GAP_TYPES = ("missing", "partial", "contradicted")


@dataclass
class Gap:
    id: str
    type: str
    section: str
    finding: str
    refs: list[str]
    obligations: list[str] = field(default_factory=list)  # linked register IDs


def ref_covers(ref: str, key: str) -> bool:
    return key == ref or key.startswith(ref + "(")


def load_gaps(obligations: list[Obligation], path: Path = GAPS_FILE) -> list[Gap]:
    gaps = []
    for g in yaml.safe_load(path.read_text(encoding="utf-8")):
        if g["type"] not in GAP_TYPES:
            raise ValueError(f"{g['id']}: unknown type {g['type']}")
        gap = Gap(g["id"], g["type"], str(g["section"]), g["finding"], list(g["refs"]))
        by_id = id_lookup(obligations)
        if g.get("obligations"):  # explicit links: must exist and sit under one of the refs
            for oid in g["obligations"]:
                o = by_id.get(oid)
                if o is None or not any(ref_covers(r, o.key) for r in gap.refs):
                    raise ValueError(f"{gap.id}: {oid} is not in the register under {gap.refs}")
            gap.obligations = list(dict.fromkeys(by_id[oid].id for oid in g["obligations"]))
        else:
            gap.obligations = [
                o.id
                for o in obligations
                if o.validation_relevant and any(ref_covers(r, o.key) for r in gap.refs)
            ]
        gaps.append(gap)
    return gaps


def unresolved_refs(gaps: list[Gap], obligations: list[Obligation]) -> list[tuple[str, str]]:
    keys = [o.key for o in obligations if o.validation_relevant]
    return [(g.id, r) for g in gaps for r in g.refs if not any(ref_covers(r, k) for k in keys)]
