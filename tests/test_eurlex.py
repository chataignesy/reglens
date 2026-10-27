from reglens.eval.retrieval import normalize_refs, refs_match
from reglens.ingest.chunks import build_chunks
from reglens.ingest.eurlex import parse_xhtml
from reglens.ingest.xrefs import build_edges
from reglens.sources import Source

CONSOLIDATED = """<html><body>
<p class="title-division-1">PART THREE</p><p class="title-division-2">CAPITAL REQUIREMENTS</p>
<p class="title-division-1">CHAPTER 3</p><p class="title-division-2">Internal Ratings Based Approach</p>
<div class="eli-subdivision" id="art_178">
  <p class="title-article-norm">Article 178</p>
  <p class="modref"><a title="32024R1623: REPLACED">&#9660;M17</a></p>
  <div class="eli-title"><p class="stitle-article-norm">Default of an obligor</p></div>
  <div class="norm"><span class="no-parag">1. </span>
    <div class="norm inline-element"><p class="norm">A default shall be considered to have occurred:</p>
      <div class="grid-container grid-list"><div class="list grid-list-column-1"><span>(a) </span></div>
        <div class="grid-list-column-2"><p class="norm">unlikely to pay;</p></div></div>
      <div class="grid-container grid-list"><div class="list grid-list-column-1"><span>(b) </span></div>
        <div class="grid-list-column-2"><p class="norm">more than 90 days past due as referred to in Article 92(3).</p></div></div>
    </div></div>
  <div class="norm"><span class="no-parag">2. </span><p class="norm">For overdrafts, see paragraph 1.</p></div>
</div>
<div class="eli-subdivision" id="art_300"><p class="title-article-norm">Article 300</p>
  <p class="norm">Out of scope.</p></div>
</body></html>"""

OJ = """<html><body>
<div class="eli-subdivision" id="rct_14"><p class="oj-normal">(14) A downturn should last at least 12 months.</p></div>
<div class="eli-subdivision" id="art_1"><p class="oj-ti-art">Article 1</p>
  <div class="eli-title"><p class="oj-sti-art">Threshold</p></div>
  <div id="001.001"><p class="oj-normal">1. Set a threshold under Article 178(1) of Regulation (EU) No 575/2013.</p></div>
  <div id="001.002"><p class="oj-normal">2. The maximum amount shall not exceed 100 EUR.</p></div>
</div></body></html>"""


def _source(**kw):
    base = dict(id="crr3-consolidated", title="CRR", issuer="EU", legal_level="L1", reference="",
                url=None, format="html", applies_to="all", scope=[], reuse="", verify=False,
                short_name="CRR")
    return Source(**{**base, **kw})


def test_consolidated_structure(tmp_path):
    p = tmp_path / "crr.xhtml"
    p.write_text(CONSOLIDATED, encoding="utf-8")
    units = parse_xhtml(p, base_celex="32013R0575")
    u1 = next(u for u in units if u.article == "178" and u.paragraph == "1")
    assert u1.title == "Default of an obligor"
    assert u1.hierarchy == [("PART THREE", "CAPITAL REQUIREMENTS"),
                            ("CHAPTER 3", "Internal Ratings Based Approach")]
    assert "(b) more than 90 days past due" in u1.text
    assert u1.amended_by == ["32024R1623"]
    assert any(u.article == "178" and u.paragraph == "2" for u in units)


def test_long_paragraph_splits_by_points(tmp_path):
    p = tmp_path / "crr.xhtml"
    p.write_text(CONSOLIDATED, encoding="utf-8")
    units = parse_xhtml(p, split_tokens=5)  # force splitting
    points = [u.point for u in units if u.article == "178" and u.paragraph == "1"]
    assert points == [None, "(a)", "(b)"]


def test_oj_paragraph_numbers_and_recitals(tmp_path):
    p = tmp_path / "rts.xhtml"
    p.write_text(OJ, encoding="utf-8")
    units = parse_xhtml(p)
    assert units[0].kind == "recital" and units[0].article == "14"
    u2 = next(u for u in units if u.paragraph == "2")
    assert u2.text == "The maximum amount shall not exceed 100 EUR."


def test_chunks_prefix_scope_and_edges(tmp_path):
    p = tmp_path / "crr.xhtml"
    p.write_text(CONSOLIDATED, encoding="utf-8")
    src = _source(articles=["107-241"])
    chunks = build_chunks(src, parse_xhtml(p), version="v1", chars_per_token=3.0)
    assert {c.article for c in chunks} == {"178"}  # Art. 300 filtered out by scope
    c1 = next(c for c in chunks if c.ref == "Art. 178(1)")
    assert c1.prefix == ("CRR › Part Three Capital requirements › Chapter 3 Internal Ratings "
                         "Based Approach › Art. 178 Default of an obligor › Art. 178(1)")
    assert c1.text.startswith(c1.prefix + "\n")
    edges = build_edges(chunks)
    assert any(e.kind == "refers_to" and e.target_article == "92" and e.target_paragraph == "3"
               for e in edges)


def test_scope_filter():
    s = _source(articles=["4", "107-241"])
    assert s.in_scope("4") and s.in_scope("122a") and s.in_scope("241")
    assert not s.in_scope("4a") and not s.in_scope("242") and not s.in_scope("92")


def test_ref_matching():
    assert normalize_refs("Art. 164(4), Table 1") == ["art.164(4)"]
    assert normalize_refs("paras. 36-37") == ["para.36", "para.37"]
    assert normalize_refs("Foreword, paras. 1-3") == ["para.1", "para.2", "para.3"]
    assert normalize_refs("Document releases table") == []
    assert refs_match("art.178(1)(b)", "art.178(1)")
    assert refs_match("art.4(1)", "art.4(1)(54)")
    assert not refs_match("art.17", "art.178(1)")
