"""Plain-text extraction and token estimates for downloaded documents.

No tokenizer is available offline, so tokens = characters / chars_per_token, with the ratio
calibrated once against real usage reported by the model (`reglens calibrate`).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from reglens.llm.provider import LLMProvider

_SKIP = {"script", "style", "head", "title"}
_BLOCK = {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def file_text(path: Path) -> str:
    return html_to_text(path.read_text(encoding="utf-8", errors="replace"))


def estimate_tokens(text: str, chars_per_token: float) -> int:
    return round(len(text) / chars_per_token)


def calibrate(provider: LLMProvider, sample: str, *, tier: str = "bulk") -> float:
    """Measure chars per token: same tiny prompt with and without `sample`, diff the input."""
    template = "Reply with the single word: ok\n\n<doc>\n{}\n</doc>"

    def prompt_tokens(body: str) -> int:
        u = provider.complete(template.format(body), purpose="calibrate", tier=tier).usage
        return u.input_tokens + u.cache_read_input_tokens + u.cache_creation_input_tokens

    sample_tokens = prompt_tokens(sample) - prompt_tokens("")
    if sample_tokens <= 0:
        raise RuntimeError("Calibration failed: sample added no tokens")
    return len(sample) / sample_tokens
