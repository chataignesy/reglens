"""Regression tests for evidence identity and completeness (review 2026-11-08: D2-D5, F1)."""

from collections import defaultdict

import pytest

import reglens.agent.run as run
import reglens.agent.tools as tools
from reglens.agent.tools import Row, Toolbox, trace_entry
from reglens.ingest.chunks import Chunk, load_chunks
from reglens.ingest.cite import assign_cites, unit_of
from reglens.ingest.eurlex import parse_xhtml
from reglens.ingest.xrefs import reference_edges


def _row(id, ref, text, *, article="124", paragraph=None, point=None, cite=""):
    return Row(id, tools.CRR, ref, "T", text, "L1", "v", "article", article, paragraph, point, cite)


# F1: only passages actually delivered may be cited


def test_unread_real_passage_is_not_accepted(monkeypatch):
    real = _row("c1", "Art. 1", "Subject matter")
    monkeypatch.setattr(run, "resolve_key", lambda conn, key: [real] if key == "CRR Art. 1" else [])
    unread: list[str] = []
    _, mapping = run._resolve(None, ["CRR Art. 1"], [], delivered=set(), undelivered=unread)
    assert mapping == {"CRR Art. 1": ["C?"]} and unread == ["CRR Art. 1"]
    _, mapping = run._resolve(None, ["CRR Art. 1"], ["CRR Art. 1"], delivered={"CRR Art. 1"})
    assert mapping == {"CRR Art. 1": ["C1"]}


def test_reference_targets_are_not_delivered_passages():
    out = "References from [CRR Art. 178(1)]:\n- refers_to: CRR Art. 178(3)\nUse get_article."
    entry = trace_entry(1, "follow_reference", ["CRR Art. 178(1)"], out)
    assert entry["keys"] == [] and entry["refs"] == ["CRR Art. 178(3)"]


# D3: long articles are paged, never cut silently


def test_get_article_pages_instead_of_cutting(monkeypatch):
    all_rows = [_row(f"c{i:02}", f"Art. 124({i})", "x" * 3000, paragraph=str(i)) for i in range(16)]
    monkeypatch.setattr(tools, "_count", lambda conn, where, params: len(all_rows))
    monkeypatch.setattr(
        tools, "_rows", lambda conn, where, params, limit=50, offset=0: all_rows[offset:offset + limit]
    )
    box = Toolbox(None)
    first = box.get_article("CRR", "124")
    assert "passages 1-4 of 16" in first and "offset=4" in first
    assert "12 more passage(s) not shown" in first
    assert first.count("x" * 3000) == 4  # whole passages only
    assert set(box.seen) == {f"CRR Art. 124({i})" for i in range(4)}  # only what was shown
    last = box.get_article("CRR", "124", offset=12)
    assert "passages 13-16 of 16" in last and "last page" in last


# D2: an unnumbered qualification after a point list keeps its paragraph


def test_continuation_after_point_split_keeps_paragraph(tmp_path):
    xhtml = tmp_path / "law.xhtml"
    xhtml.write_text(
        """<div class="eli-subdivision" id="art_142">
          <div><span class="no-parag">1.</span>Definitions apply:
            <div class="grid-container"><div class="grid-list-column-1">(5a)</div>
            <div class="grid-list-column-2">large corporate means a company</div></div>
          </div><p>For the purposes of point (5a), use the audited figures.</p></div>""",
        encoding="utf-8",
    )
    units = parse_xhtml(xhtml, split_tokens=1)
    assert units[-1].text.startswith("For the purposes of point (5a)")
    assert units[-1].paragraph == "1" and units[-1].point is None


def test_definition_includes_its_qualification(monkeypatch):
    definition = _row("d", "Art. 142(1)(5a)", "‘large corporate’ means …", article="142",
                      paragraph="1", point="(5a)")
    qual = _row("q", "Art. 142(1)", "For the purposes of point (5a), … audited …", article="142",
                paragraph="1")

    def rows(conn, where, params, limit=50, offset=0):
        return [qual] if "point IS NULL" in where else [definition]

    monkeypatch.setattr(tools, "_rows", rows)
    out = Toolbox(None).get_definition("large corporate")
    assert "‘large corporate’ means" in out and "audited" in out


# D4: one citation key per logical unit


def _chunk(id, kind, article, paragraph, hierarchy):
    return Chunk(id, "ecb-validation-reporting", "v", "L4", "SI", kind, article, paragraph, None,
                 f"para. {paragraph}", "Instructions", hierarchy, "p", "t", "b")


def test_restarting_numbering_gets_section_qualified_keys():
    a = _chunk("x:paragraph:b0:1:", "paragraph", "b0", "1", ["Instructions", "2.4 General"])
    b = _chunk("x:paragraph:b1:1:", "paragraph", "b1", "1", ["Instructions", "2.5 PD"])
    c = _chunk("x:paragraph:b1:2:", "paragraph", "b1", "2", ["Instructions", "2.5 PD"])
    assign_cites([a, b, c])
    assert a.cite == "ECB validation reporting instructions, Section 2.4, para. 1"
    assert b.cite == "ECB validation reporting instructions, Section 2.5, para. 1"
    assert c.cite == "ECB validation reporting instructions para. 2"  # unique: unchanged


def test_loose_key_naming_several_units_is_ambiguous():
    rows = [_row("a", "para. 1", "A", article="b0"), _row("b", "para. 1", "B", article="b1")]
    assert tools._one_unit(rows) == []
    assert tools._one_unit(rows[:1]) == rows[:1]


def test_corpus_keys_are_unique_per_unit():
    chunks = load_chunks()
    if not chunks:
        pytest.skip("no processed chunks")
    by_source = defaultdict(list)
    for c in chunks:
        by_source[c.source_id].append(c)
    for cs in by_source.values():
        assign_cites(cs)
    units = defaultdict(set)
    for c in chunks:
        units[c.cite].add(unit_of(c))
    assert [k for k, u in units.items() if len(u) > 1] == []


# D5: references to a sibling paragraph of the same article are kept


def test_same_article_sibling_reference_is_an_edge():
    c = Chunk("crr3-consolidated:article:178:1:", tools.CRR, "v", "L1", "all", "article", "178",
              "1", None, "Art. 178(1)", "Default", [], "p", "t",
              "The conditions in Article 178(3) shall apply. See also Article 178.")
    edges = reference_edges(c)
    assert [(e.target_article, e.target_paragraph) for e in edges] == [("178", "3")]


def test_paragraph_references_inside_an_article_are_edges():
    c = Chunk("crr3-consolidated:article:178:1:", tools.CRR, "v", "L1", "all", "article", "178",
              "1", None, "Art. 178(1)", "Default", [], "p", "t",
              "As set out in paragraph 3 of this Article and paragraphs 4 and 5, but not "
              "paragraph 2 of Article 92; this paragraph 1 applies.")
    edges = [(e.target_article, e.target_paragraph) for e in reference_edges(c)]
    assert ("178", "3") in edges and ("178", "4") in edges and ("178", "5") in edges
    assert ("178", "2") not in edges and ("178", "1") not in edges
    assert ("92", None) in edges
