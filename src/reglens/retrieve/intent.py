"""Narrow source opt-ins for questions explicitly asking about legislative changes."""

import re
from dataclasses import replace


def source_filters(conn, question, filters):
    from reglens.sources import load_sources

    # Explicit caller scope always wins, including an intentionally unrestricted search.
    if filters.source_ids is not None or not filters.default_scope:
        return filters
    if not re.search(r"\b(?:amend\w*|chang\w*|introduc\w*|replac\w*)\b", question, re.I):
        return filters
    sources = load_sources(conn=conn)
    selected = []
    for source in sources:
        if source.search_default or not re.search(r"amend", source.label(), re.I):
            continue
        aliases = re.findall(r"\b[A-Z]{2,}\d+\b|\b\d{4}/\d+\b", source.label())
        if any(re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", question, re.I) for a in aliases):
            selected.append(source.id)
    if not selected:
        return filters
    return replace(filters, source_ids=[s.id for s in sources if s.search_default] + selected)
