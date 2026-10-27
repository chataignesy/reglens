"""Cross-reference and definition edges between chunks (no LLM calls).

Edge kinds:
- refers_to       "Article 92(3)", "Articles 153 and 157", "... of Regulation (EU) No 575/2013"
- amends          CRR3 amending act: "Article 160 is amended / replaced / inserted" -> CRR article
- uses_definition chunk uses a term defined in CRR Art. 4(1) ('large corporate', 'QRRE', ...)
Targets are (source_id, article, paragraph); they are resolved to chunk ids at index time.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from reglens.config import PROJECT_ROOT
from reglens.ingest.chunks import Chunk

CRR = "crr3-consolidated"
XREF_FILE = PROJECT_ROOT / "data" / "processed" / "xrefs.jsonl"

_ART = r"(\d{1,3}[a-z]?)(\((\d+[a-z]?)\))?"
_REF = re.compile(rf"\bArticles?\s+{_ART}((?:\s*(?:,|and|or)\s*{_ART})*)")
_MORE = re.compile(rf"(?:,|and|or)\s*{_ART}")
_CRR_AFTER = re.compile(
    r"^[^.;]{0,80}?of (?:Regulation \(EU\) (?:No )?575/2013|that Regulation|the CRR)\b"
)
_OTHER_AFTER = re.compile(
    r"^[^.;]{0,40}?of (?:Directive|Regulation \(EU\) (?:No )?(?!575/2013)\d+/\d+|Delegated)"
)
_AMENDS = re.compile(rf"^\s*Articles?\s+{_ART}\s+is (?:amended|replaced|inserted|deleted)")
_DEF = re.compile(r"^‘([^’]{2,80})’(?: or ‘([^’]{1,30})’)?\s+means\b")


@dataclass(frozen=True)
class Edge:
    src: str  # chunk id
    kind: str  # refers_to | amends | uses_definition
    target_source: str
    target_article: str
    target_paragraph: str | None = None
    target_point: str | None = None  # e.g. "(5a)" for an Art. 4(1) definition


def _default_target(chunk: Chunk) -> str | None:
    """Where a bare 'Article N' points: the same act for regulations, nowhere for guidelines."""
    if chunk.source_id == "crr3-amending-act":
        return CRR  # article numbers in the amending act's points refer to the CRR
    if chunk.legal_level in ("L1", "L2"):
        return chunk.source_id
    return None


def reference_edges(chunk: Chunk) -> list[Edge]:
    edges: list[Edge] = []
    body = chunk.body
    m = _AMENDS.match(body)
    if chunk.source_id == "crr3-amending-act" and m:
        edges.append(Edge(chunk.id, "amends", CRR, m.group(1), m.group(3)))
    for m in _REF.finditer(body):
        after = body[m.end() :]
        if _OTHER_AFTER.match(after):
            continue  # reference into another act (CRD, other regulations)
        target = CRR if _CRR_AFTER.match(after) else _default_target(chunk)
        if not target:
            continue
        refs = [(m.group(1), m.group(3))]
        refs += [(x.group(1), x.group(3)) for x in _MORE.finditer(m.group(4) or "")]
        for art, para in refs:
            if target == chunk.source_id and art == chunk.article:
                continue  # self-reference
            edges.append(Edge(chunk.id, "refers_to", target, art, para))
    return edges


def definitions(chunks: list[Chunk]) -> dict[str, Chunk]:
    """Defined term (lower case) -> defining chunk, from CRR Art. 4(1)."""
    terms: dict[str, Chunk] = {}
    for c in chunks:
        if c.source_id == CRR and c.article == "4" and c.point:
            m = _DEF.match(c.body)
            if m:
                for t in filter(None, m.groups()):
                    terms[t.lower()] = c
    return terms


def definition_edges(chunks: list[Chunk], terms: dict[str, Chunk]) -> list[Edge]:
    if not terms:
        return []
    # Longest terms first: 'unregulated financial sector entity' beats 'financial sector entity'.
    ordered = sorted(terms, key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in ordered) + r")\b", re.I)
    edges = []
    for c in chunks:
        found = {
            terms[m.group(1).lower()].id: terms[m.group(1).lower()]
            for m in pattern.finditer(c.body)
        }
        for target_id, d in sorted(found.items()):
            if target_id != c.id:
                edges.append(Edge(c.id, "uses_definition", CRR, "4", d.paragraph, d.point))
    return edges


def build_edges(chunks: list[Chunk]) -> list[Edge]:
    edges = [e for c in chunks for e in reference_edges(c)]
    edges += definition_edges(chunks, definitions(chunks))
    return list(dict.fromkeys(edges))  # de-duplicate, keep order


def write_edges(edges: list[Edge]) -> None:
    XREF_FILE.parent.mkdir(parents=True, exist_ok=True)
    with XREF_FILE.open("w", encoding="utf-8") as f:
        for e in edges:
            f.write(json.dumps(asdict(e)) + "\n")


def load_edges() -> list[Edge]:
    if not XREF_FILE.exists():
        return []
    return [Edge(**json.loads(line)) for line in XREF_FILE.read_text(encoding="utf-8").splitlines()]
