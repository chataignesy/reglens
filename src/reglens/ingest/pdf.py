"""PDF sources (EBA guidelines, ECB guide): Docling -> Markdown -> numbered paragraphs.

Docling output is cached in data/processed/docling/<source id>.md, so the slow,
GPU-heavy conversion runs once per document version.

Paragraph numbering restarts between parts of a document (EBA final report: background,
then the guidelines; ECB guide: foreword, overarching principles, each risk chapter), so
paragraphs are grouped into numbering *blocks*. In EBA final reports only the block that
contains "Compliance and reporting obligations" is the operative guideline text; other
blocks become kind "background".
"""

from __future__ import annotations

import re
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.ingest.eurlex import Unit

DOCLING_DIR = PROJECT_ROOT / "data" / "processed" / "docling"

_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_NUM_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
_PARA = re.compile(r"^(\d{1,3})\.\s+(.*)$")
_BOGUS_NUM = re.compile(r"^\d{1,3}\.\s+(?=\(|[-–•])")  # Docling numbers list items: "2. (a) …"
_FOOTER = re.compile(r"^[A-Z][A-Z0-9 ,.\-–&()/’']{12,}\s+\|?\s*\d{1,3}$")  # running page headers
_GUIDELINES_START = re.compile(r"compliance and reporting obligations", re.I)


def pdf_to_markdown(source_id: str, pdf: Path, *, force: bool = False) -> str:
    out = DOCLING_DIR / f"{source_id}.md"
    if out.exists() and not force:
        return out.read_text(encoding="utf-8")
    from docling.document_converter import DocumentConverter  # heavy import, ml extra

    doc = DocumentConverter().convert(str(pdf)).document
    md = doc.export_to_markdown()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return md


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_markdown(
    md: str, *, parts: list[str] | None = None, blocks_include: list[str] | None = None
) -> list[Unit]:
    """Split Docling Markdown into numbered-paragraph units.

    If a "Compliance and reporting obligations" heading exists (EBA guidelines), only its
    numbering block is operative and all other blocks become kind "background".
    parts: regexes for unnumbered top-level part headings (e.g. "Credit risk" in the ECB guide).
    blocks_include: keep only blocks whose part heading matches one of these regexes.
    """
    part_res = [re.compile(rf"(?:{p})", re.I) for p in parts or []]  # matched in full
    units: list[Unit] = []
    headings: list[tuple[int, str, bool]] = []  # (depth, text, numbered)
    part = ""  # current part heading; stored on each unit as `title`
    block, last_num, guidelines_block = 0, 0, None
    current: Unit | None = None

    def section_ref() -> str:
        """'Section 2.2' from the nearest numbered heading, else the heading text."""
        for _, text, numbered in reversed(headings):
            if numbered:
                return "Section " + _NUM_HEADING.match(text).group(1)
        return headings[-1][1] if headings else "Introduction"

    def depth_of(text: str) -> tuple[int, bool]:
        """Numbered headings: depth from the number (4.4.1 -> 3); unnumbered: one below."""
        m = _NUM_HEADING.match(text)
        if m:
            return m.group(1).count(".") + 1, True
        numbered = [d for d, _, n in headings if n]
        if numbered:
            return max(numbered) + 1, False
        return (1 if part_res else 0), False  # with explicit parts, only parts are top level

    for raw in md.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--") or _FOOTER.match(line):
            continue
        h = _HEADING.match(line)
        if h:
            text = _clean(h.group(1))
            if text.lower() in {"contents", "table of contents"} or re.match(r"^Table \d+$", text):
                continue  # table of contents / table captions are not structure
            is_part = any(r.fullmatch(text) for r in part_res)
            d, numbered = (0, False) if is_part else depth_of(text)
            headings = [x for x in headings if x[0] < d] + [(d, text, numbered)]
            if is_part or (not part_res and d == 0):
                part = text
            if _GUIDELINES_START.search(text):
                guidelines_block = block + 1 if last_num > 1 else block
            current = None
            continue
        p = _PARA.match(line)
        num = int(p.group(1)) if p else None
        if num is not None and not _BOGUS_NUM.match(line):
            if num == 1 and last_num > 1:  # numbering restarts: new block
                block += 1
            if num == 1 or last_num < num <= last_num + 3:
                last_num = num
                current = Unit(
                    kind="paragraph",
                    article=f"b{block}",
                    paragraph=str(num),
                    point=None,
                    hierarchy=[("", t) for _, t, _ in headings],
                    title=part or None,
                    text=_clean(p.group(2)),
                )
                units.append(current)
                continue
        text = _clean(_BOGUS_NUM.sub("", line).lstrip("-• "))
        if current is None:  # prose under a heading, outside numbered paragraphs
            current = Unit(
                kind="section",
                article=f"b{block}",
                paragraph=section_ref(),
                point=None,
                hierarchy=[("", t) for _, t, _ in headings],
                title=part or None,
                text=text,
            )
            units.append(current)
        else:
            current.text += "\n" + text

    def in_scope(u: Unit) -> bool:
        return not blocks_include or any(re.match(p, u.title or "", re.I) for p in blocks_include)

    # Blocks whose numbered paragraphs are in scope; prose elsewhere (e.g. reference annexes
    # that repeat part headings) is dropped when a scope filter is set.
    live_blocks = {u.article for u in units if u.kind == "paragraph" and in_scope(u)}
    out = []
    for u in units:
        if blocks_include and u.kind == "section" and u.article not in live_blocks:
            continue
        if u.kind == "section" and len(u.text) < 40:
            continue  # stray captions, page labels
        operative = u.kind == "paragraph" and u.article == f"b{guidelines_block}"
        if guidelines_block is not None and not operative:
            u.kind = "background"
        if not in_scope(u):
            continue
        out.append(u)
    return out
