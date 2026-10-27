from datetime import date

import pytest

from reglens.ingest.download import pick_version
from reglens.ingest.tokens import calibrate, estimate_tokens, html_to_text
from reglens.llm.ledger import Usage
from reglens.llm.provider import Completion

VERSIONS = ["02013R0575-20270101", "02013R0575-20260626", "02013R0575-20260101"]


def test_pick_version_in_force_on_as_of_date():
    assert pick_version(VERSIONS, date(2026, 10, 27)) == "02013R0575-20260626"
    assert pick_version(VERSIONS, date(2027, 1, 1)) == "02013R0575-20270101"
    with pytest.raises(ValueError):
        pick_version(VERSIONS, date(2025, 1, 1))


def test_html_to_text_strips_markup_and_skips_head():
    html = (
        "<html><head><title>T</title><style>p{}</style></head>"
        "<body><p>Article&nbsp;178</p><p>Default   of  an obligor</p></body></html>"
    )
    assert html_to_text(html) == "Article 178\nDefault of an obligor"


def test_estimate_tokens():
    assert estimate_tokens("x" * 400, 4.0) == 100


def test_calibrate_diffs_prompt_tokens():
    class FakeProvider:
        def complete(self, prompt, **kwargs):
            # 50 tokens of template + 1 token per 3 chars of sample
            n = 50 + (len(prompt) - 40) // 3
            return Completion("ok", "m", Usage(input_tokens=4, output_tokens=1,
                                                cache_creation_input_tokens=n - 4))

    ratio = calibrate(FakeProvider(), "y" * 3000)
    assert ratio == pytest.approx(3.0, rel=0.01)
