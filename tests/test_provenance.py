"""Input provenance (review 2026-11-08: D1, F3): caches are keyed by content, not by name."""

import json
import os
import sys
import types

import reglens.ingest.pdf as pdf
from reglens.gap.register import Passage, batch_id


def _fake_docling(monkeypatch, text):
    calls = []

    class Converter:
        def convert(self, path):
            calls.append(path)
            doc = types.SimpleNamespace(export_to_markdown=lambda: text)
            return types.SimpleNamespace(document=doc)

    mod = types.ModuleType("docling.document_converter")
    mod.DocumentConverter = Converter
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", mod)
    return calls


def test_redownloaded_pdf_is_converted_again(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf, "DOCLING_DIR", tmp_path)
    source = tmp_path / "src.pdf"
    source.write_bytes(b"%PDF old bytes")
    calls = _fake_docling(monkeypatch, "OLD text")
    assert pdf.pdf_to_markdown("s", source) == "OLD text" and len(calls) == 1
    meta = json.loads((tmp_path / "s.meta.json").read_text())
    assert meta["pdf_sha256"] == pdf.file_sha256(source)

    assert pdf.pdf_to_markdown("s", source) == "OLD text" and len(calls) == 1  # cached

    source.write_bytes(b"%PDF new regulatory text")  # re-downloaded: new bytes, same name
    calls2 = _fake_docling(monkeypatch, "NEW text")
    assert pdf.pdf_to_markdown("s", source) == "NEW text" and len(calls2) == 1


def test_legacy_cache_adopted_only_if_newer_than_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf, "DOCLING_DIR", tmp_path)
    source, md = tmp_path / "src.pdf", tmp_path / "s.md"
    source.write_bytes(b"%PDF bytes")
    md.write_text("cached text", encoding="utf-8")
    os.utime(source, (1_000, 1_000))
    os.utime(md, (2_000, 2_000))  # converted after the PDF was downloaded: adopted
    assert pdf.pdf_to_markdown("s", source) == "cached text"
    assert (tmp_path / "s.meta.json").exists()

    (tmp_path / "s.meta.json").unlink()
    os.utime(md, (500, 500))  # older than the PDF: provenance unknown, convert again
    _fake_docling(monkeypatch, "fresh text")
    assert pdf.pdf_to_markdown("s", source) == "fresh text"


def test_extraction_cache_key_covers_text_and_model():
    a = [Passage("crr:185:b", "crr3-consolidated", "Art. 185(b)", "CRR Art. 185(b)", "L1", "all",
                 "validate at least annually")]
    b = [Passage("crr:185:b", "crr3-consolidated", "Art. 185(b)", "CRR Art. 185(b)", "L1", "all",
                 "validate at least every two years")]  # same chunk id, corrected text
    assert batch_id(a, "claude-sonnet-5-5") != batch_id(b, "claude-sonnet-5-5")
    assert batch_id(a, "claude-sonnet-5-5") != batch_id(a, "claude-opus-5-5")
    assert batch_id(a, "claude-sonnet-5-5") == batch_id(list(a), "claude-sonnet-5-5")
