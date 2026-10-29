"""Headless Streamlit check: the page renders with disclaimer and key field (no LLM call)."""

from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

APP = Path(__file__).resolve().parents[1] / "src" / "reglens" / "ui" / "app.py"


def test_app_renders_without_asking():
    at = st_testing.AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "RegLens"
    assert any("not legal or regulatory advice" in i.value.lower() for i in at.info)
    labels = [t.label for t in at.sidebar.text_input]
    assert "Anthropic API key" in labels
    assert at.button[0].disabled  # nothing asked until there is a question
