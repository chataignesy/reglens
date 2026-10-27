from reglens.ingest.chunks import build_chunks
from reglens.ingest.eba_qa import parse_qa, qa_units
from reglens.ingest.xrefs import build_edges
from reglens.sources import Source

PAGE = """<html><body><main>
<div class="field field--name-qa-question-id"><div class="field__label">Question ID</div>2018_4012</div>
<div class="field field--name-qa-legal-article">178</div>
<div class="field field--name-qa-article-paragraph">1(b)</div>
<div class="field field--name-qa-subject-matter">Counting of days past due</div>
<div class="field field--name-qa-question">When does the counting start?</div>
<div class="field field--name-qa-question-background">Background text.</div>
<div class="field field--name-qa-final-answer">Counting starts when the threshold in Article 178(2)(d) is breached.</div>
<div class="field field--name-qa-status">Final Q&amp;A</div>
<div class="field field--name-qa-final-publishing-date">01/02/2019</div>
</main></body></html>"""


def test_parse_qa_fields():
    qa = parse_qa(PAGE, "https://example/qa")
    assert qa.id == "2018_4012"
    assert qa.article == "178" and qa.paragraph == "1(b)"
    assert qa.status == "Final Q&A"
    assert qa.answer.startswith("Counting starts")
    assert qa.topic == "Credit risk"  # fixed by the listing filter


def test_qa_chunk_and_edges():
    qa = parse_qa(PAGE, "https://example/qa")
    src = Source(id="eba-qa-credit-risk", title="EBA Q&A", issuer="EBA", legal_level="qa",
                 reference="", url=None, format="eba-qa", applies_to="all", scope=[], reuse="",
                 verify=False, short_name="EBA Q&A")
    [chunk] = build_chunks(src, qa_units([qa]), version="2026-10-27", chars_per_token=3.0)
    assert chunk.ref == "Q&A 2018_4012"
    assert chunk.prefix == "EBA Q&A › CRR Art. 178 › Credit risk › Q&A 2018_4012"
    kinds = {(e.kind, e.target_article) for e in build_edges([chunk])}
    assert ("answers_on", "178") in kinds and ("refers_to", "178") in kinds
