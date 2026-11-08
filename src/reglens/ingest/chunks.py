"""Turn parsed units into retrieval chunks with a deterministic hierarchy prefix.

Each chunk's `text` starts with its location, e.g.
  "CRR › Part Three Capital requirements › Title II … › Art. 178 Default of an obligor … › para. 1"
so that both BM25 and embeddings see where the text sits (no LLM-generated context).
Chunks are written to data/processed/chunks/<source id>.jsonl.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.ingest.eurlex import Unit
from reglens.sources import Source

CHUNK_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"


@dataclass
class Chunk:
    id: str  # "<source>:<kind>:<article>:<paragraph>:<point>[#part]"
    source_id: str
    version: str | None  # CELEX version or document date
    legal_level: str
    applies_to: str
    kind: str
    article: str | None
    paragraph: str | None
    point: str | None
    ref: str  # human-readable reference, e.g. "Art. 178(1)" or "para. 71"
    title: str | None
    hierarchy: list[str]
    prefix: str
    text: str  # prefix + body: what gets indexed and embedded
    body: str
    amended_by: list[str] = field(default_factory=list)
    part: int = 0  # >0 when a long unit was split into windows
    cite: str = ""  # citation key, unique per logical unit (see ingest/cite.py)
    source_sha256: str = ""  # digest of the raw source file the text was parsed from


def _title_case(s: str) -> str:
    return s if not s.isupper() else s.capitalize()


def _label_case(s: str) -> str:
    """'PART THREE' -> 'Part Three', 'TITLE II' -> 'Title II', 'Sub-Section 2' unchanged."""
    if not s.isupper():
        return s
    return " ".join(w if re.fullmatch(r"[IVXLC]+", w) else w.capitalize() for w in s.split())


def ref_of(unit: Unit) -> str:
    if unit.kind == "recital":
        return f"recital {unit.article}"
    if unit.kind == "paragraph":  # numbered paragraph of a guideline / guide (PDF sources)
        return f"para. {unit.paragraph}" + (unit.point or "")
    if unit.kind == "background":  # explanatory part of an EBA final report
        p = unit.paragraph or ""
        return f"background para. {p}" if p.isdigit() else f"background {p}".strip()
    if unit.kind == "section":  # unnumbered prose, referenced by its section number
        return unit.paragraph or "section"
    if unit.kind == "qa":  # EBA Single Rulebook Q&A, by question ID
        return f"Q&A {unit.paragraph}"
    ref = f"Art. {unit.article}"
    if unit.paragraph:
        ref += f"({unit.paragraph})"
    if unit.point:
        ref += unit.point if unit.point.startswith("(") else f"({unit.point})"
    return ref


def _windows(body: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Split an over-long body at sentence/line boundaries into overlapping windows."""
    pieces = re.split(r"(?<=[.;:])\s+|\n", body)
    out, cur = [], ""
    for piece in pieces:
        if cur and len(cur) + len(piece) + 1 > max_chars:
            out.append(cur)
            cur = cur[-overlap_chars:] + " " + piece
        else:
            cur = f"{cur} {piece}".strip()
    if cur:
        out.append(cur)
    return out


def build_chunks(
    source: Source,
    units: list[Unit],
    *,
    version: str | None,
    chars_per_token: float,
    max_tokens: int = 1200,
    overlap_tokens: int = 100,
    source_sha256: str = "",
) -> list[Chunk]:
    chunks: list[Chunk] = []
    seen: dict[str, int] = {}
    for u in units:
        if u.kind == "article" and not source.in_scope(u.article):
            continue
        hierarchy = [
            f"{_label_case(label)} {_title_case(name)}".strip() for label, name in u.hierarchy
        ]
        ref = ref_of(u)
        head = ref if u.kind != "article" else f"{ref.split('(')[0]} {u.title or ''}".strip()
        parts = [source.label(), *hierarchy, head]
        if u.kind == "article" and (u.paragraph or u.point):
            parts.append(ref)
        prefix = " › ".join(p for p in parts if p)

        max_chars = int(max_tokens * chars_per_token)
        bodies = (
            [u.text]
            if len(u.text) <= max_chars
            else _windows(u.text, max_chars, int(overlap_tokens * chars_per_token))
        )
        base_id = f"{source.id}:{u.kind}:{u.article}:{u.paragraph or ''}:{u.point or ''}"
        n = seen.get(base_id, 0)
        seen[base_id] = n + 1
        if n:
            base_id += f"~{n}"  # same reference twice (e.g. unnumbered subparagraphs)
        for i, body in enumerate(bodies):
            chunks.append(
                Chunk(
                    id=base_id + (f"#{i + 1}" if len(bodies) > 1 else ""),
                    source_id=source.id,
                    version=version,
                    legal_level=source.legal_level,
                    applies_to=source.applies_to,
                    kind=u.kind,
                    article=u.article,
                    paragraph=u.paragraph,
                    point=u.point,
                    ref=ref,
                    title=u.title,
                    hierarchy=hierarchy,
                    prefix=prefix,
                    text=f"{prefix}\n{body}",
                    body=body,
                    amended_by=u.amended_by,
                    part=i + 1 if len(bodies) > 1 else 0,
                    source_sha256=source_sha256,
                )
            )
    from reglens.ingest.cite import assign_cites

    assign_cites(chunks)
    return chunks


def write_chunks(source_id: str, chunks: list[Chunk]) -> Path:
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    path = CHUNK_DIR / f"{source_id}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    return path


def load_chunks(source_ids: list[str] | None = None) -> list[Chunk]:
    paths = sorted(CHUNK_DIR.glob("*.jsonl"))
    out = []
    for p in paths:
        if source_ids and p.stem not in source_ids:
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            out.append(Chunk(**json.loads(line)))
    return out
