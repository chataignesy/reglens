"""Deterministic query expansion: practitioner jargon -> the legal texts' wording (no LLM)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

GLOSSARY_FILE = Path(__file__).with_name("glossary.yaml")


@lru_cache(maxsize=1)
def _entries() -> list[tuple[re.Pattern, str]]:
    raw = yaml.safe_load(GLOSSARY_FILE.read_text(encoding="utf-8"))
    out = []
    for e in raw:
        alts = "|".join(re.escape(t) for t in sorted(e["terms"], key=len, reverse=True))
        out.append((re.compile(rf"(?<![\w-])(?:{alts})(?![\w-])", re.I), e["expand"]))
    return out


def expand_query(question: str) -> str:
    """Question plus the legal wording for every glossary term it uses."""
    extra = [exp for pat, exp in _entries() if pat.search(question)]
    return question if not extra else f"{question}\n({'; '.join(dict.fromkeys(extra))})"
