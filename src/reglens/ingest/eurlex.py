"""Structure-aware parser for EUR-Lex XHTML (consolidated texts and Official Journal acts).

Produces one record per article paragraph (or per top-level point, when a paragraph is
long — e.g. the Art. 4(1) definitions), plus one per recital, each with its position in
the legal hierarchy (Part > Title > Chapter > Section > Sub-Section).
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Division headings: label line (e.g. "CHAPTER 3") followed by a name line.
_LABEL_CLASSES = {"title-division-1", "oj-ti-section-1"}
_NAME_CLASSES = {"title-division-2", "oj-ti-section-2"}
_ART_TITLE = {"title-article-norm", "oj-ti-art"}
_ART_SUBTITLE = {"stitle-article-norm", "oj-sti-art"}
_LEVELS = [("SUB-SECTION", 5), ("SECTION", 4), ("CHAPTER", 3), ("TITLE", 2), ("PART", 1)]
_PARA_NUM = re.compile(r"^(\d+[a-z]?)\.\s+")
_CELEX_IN_MODREF = re.compile(r"^(\d{5}[A-Z]\d{4})")
_WS = re.compile(r"\s+")


@dataclass
class Unit:
    """One retrievable piece of a legal text."""

    kind: str  # "article" | "recital"
    article: str | None  # "178", "47b"; recital number for recitals
    paragraph: str | None  # "1", "1a"; None when unnumbered
    point: str | None  # "(54)" when a long paragraph was split by points
    hierarchy: list[tuple[str, str]]  # [("PART THREE", "CAPITAL REQUIREMENTS"), ...]
    title: str | None  # article heading, e.g. "Default of an obligor or credit facility"
    text: str
    amended_by: list[str] = field(default_factory=list)  # CELEX of amending acts (modrefs)


def _classes(el: Tag) -> set[str]:
    return set(el.get("class") or [])


def _clean(text: str) -> str:
    return _WS.sub(" ", text.replace("\xa0", " ")).strip()


def _text(el: Tag) -> str:
    """Element text without modification markers (▼M17, ►C2 ...)."""
    for m in el.find_all("p", class_="modref"):
        m.decompose()
    text = _clean(el.get_text(" "))
    return re.sub(r"[▼►◄]\s?[A-Z]\d+\s*|◄", "", text).strip()


def _level(label: str) -> int | None:
    up = label.upper()
    for key, lvl in _LEVELS:
        if up.startswith(key):
            return lvl
    return None


def _amendments(el: Tag, base: str | None) -> list[str]:
    """Amending acts from modification markers; skips the base act and its corrigenda."""
    out = []
    for a in el.select("p.modref a[title]"):
        m = _CELEX_IN_MODREF.match(a["title"])
        if m and m.group(1) != base and m.group(1) not in out:
            out.append(m.group(1))
    return out


def _inside(node: Tag, ancestor: Tag) -> bool:
    return any(p is ancestor for p in node.parents)


def _split_points(el: Tag) -> tuple[str, list[tuple[str, str]]] | None:
    """Split a paragraph into lead-in text and its top-level points, if it has any."""
    # Consolidated texts: grid lists. Official Journal acts: two-column tables.
    points = [
        g
        for g in el.find_all("div", class_="grid-container")
        if not any(_inside(p, el) for p in g.find_parents("div", class_="grid-container"))
    ]
    if points:
        cells = [
            (g.find("div", class_="grid-list-column-1"), g.find("div", class_="grid-list-column-2"))
            for g in points
        ]
    else:
        points = [
            t
            for t in el.find_all("table")
            if not any(_inside(p, el) for p in t.find_parents("table"))
        ]
        cells = []
        for t in points:
            tds = t.find("tr").find_all("td", recursive=False) if t.find("tr") else []
            cells.append((tds[0], tds[1]) if len(tds) == 2 else (None, t))
    if not points:
        return None
    items = []
    for label_el, body_el in cells:
        label = _clean(label_el.get_text(" ")) if label_el else ""
        items.append((label, _text(body_el) if body_el else ""))
    for g in points:
        g.extract()
    lead = _text(el)
    return lead, items


def _point_cell(el: Tag) -> tuple[Tag, Tag] | None:
    """(label cell, body cell) when `el` is a single point: an OJ table or a grid-list item."""
    if el.name == "table":
        tr = el.find("tr")
        tds = tr.find_all("td", recursive=False) if tr else []
        if len(tds) == 2 and re.fullmatch(r"\(?[0-9a-z]+\)?", _clean(tds[0].get_text(" "))):
            return tds[0], tds[1]
    if el.name == "div" and "grid-container" in _classes(el):
        a = el.find("div", class_="grid-list-column-1")
        b = el.find("div", class_="grid-list-column-2")
        if a and b:
            return a, b
    return None


def _paragraphs(article: Tag) -> list[tuple[str | None, Tag]]:
    """Direct children of an article grouped into (paragraph number, element) pairs."""
    out: list[tuple[str | None, Tag]] = []
    for child in article.find_all(recursive=False):
        cls = _classes(child)
        if cls & (_ART_TITLE | {"modref", "eli-title"}):
            continue
        num = None
        span = child.find("span", class_="no-parag", recursive=False)
        if span:
            num = _clean(span.get_text()).rstrip(".")
            span.decompose()
        else:
            m = _PARA_NUM.match(_clean(child.get_text(" ")))
            if m and child.name == "div":
                num = m.group(1)
        out.append((num, child))
    return out


def parse_xhtml(
    path: Path,
    *,
    base_celex: str | None = None,
    split_tokens: int = 800,
    chars_per_token: float = 3.0,
) -> list[Unit]:
    """Parse a EUR-Lex XHTML file. `base_celex` (e.g. 32013R0575) is excluded from amended_by."""
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    units: list[Unit] = []
    stack: list[tuple[int, str, str]] = []  # (level, label, name)
    pending: tuple[int, str] | None = None

    def is_heading(el: Tag) -> bool:
        return el.name == "p" and bool(_classes(el) & (_LABEL_CLASSES | _NAME_CLASSES))

    def is_block(el: Tag) -> bool:
        return (
            el.name == "div"
            and "eli-subdivision" in _classes(el)
            and re.match(r"^(art|rct)_\d", el.get("id", "")) is not None
        )

    for el in soup.find_all(lambda e: is_heading(e) or is_block(e)):
        if el.find_parent(is_block):
            continue  # nested inside an article already handled
        if is_heading(el):
            text = _clean(el.get_text(" "))
            if _classes(el) & _LABEL_CLASSES:
                lvl = _level(text)
                pending = (lvl, text) if lvl else None
            elif pending:
                lvl, label = pending
                stack = [s for s in stack if s[0] < lvl] + [(lvl, label, text)]
                pending = None
            continue

        block_id = el["id"]
        hierarchy = [(label, name) for _, label, name in stack]
        if block_id.startswith("rct_"):
            body = _text(el)
            units.append(Unit("recital", block_id[4:], None, None, hierarchy, None, body))
            continue

        number = block_id[4:]
        sub = el.find("p", class_=lambda c: c in _ART_SUBTITLE)
        title = _clean(sub.get_text(" ")) if sub else None
        amended = _amendments(el, base_celex)

        def too_long(node: Tag) -> bool:
            return len(_clean(node.get_text(" "))) / chars_per_token > split_tokens

        # Closures below are only called within this iteration, so late binding is safe.
        def emit(para: str | None, point: str | None, text: str) -> None:
            if text:
                units.append(Unit("article", number, para, point, hierarchy, title, text, amended))  # noqa: B023

        def emit_split(para: str | None, prefix: str, node: Tag) -> bool:
            """Emit `node` as lead-in + one unit per top-level point; False if it has none."""
            split = _split_points(node)
            if not split:
                return False
            lead, items = split
            emit(para, prefix or None, lead)
            for label, body in items:
                emit(para, f"{prefix}{label}", body)
            return True

        current: Unit | None = None
        para_num: str | None = None
        for num, child in _paragraphs(el):
            cell = _point_cell(child) if num is None else None
            if cell:
                # A point container directly under the article (OJ amending acts).
                label_el, body_el = cell
                label = _clean(label_el.get_text(" "))
                if not (too_long(body_el) and emit_split(para_num, label, body_el)):
                    emit(para_num, label, _text(body_el))
                current = None
                continue
            para_num = num or para_num
            if too_long(child) and emit_split(para_num, "", child):
                current = None
                continue
            body = _text(child)
            if num and body.startswith(f"{num}."):
                body = body[len(num) + 1 :].lstrip()  # OJ acts keep "2. " in the text
            if not body or set(body) <= {"—", " "}:
                continue  # deleted paragraph placeholder
            if num is None and current is not None:
                current.text += "\n" + body  # continuation of the previous paragraph
                continue
            current = Unit("article", number, num, None, hierarchy, title, body, amended)
            units.append(current)
    return units
