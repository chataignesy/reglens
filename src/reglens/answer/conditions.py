"""Explicit source links between waiting periods and the conditions qualifying them."""

import re


def _number(unit):
    value = getattr(unit, "paragraph", None)
    if value and value.isdigit():
        return int(value)
    match = re.fullmatch(r"para\.\s*(\d+)", unit.ref)
    return int(match[1]) if match else None


def condition_units(conn, question: str, hits: list, filters=None) -> list[list]:
    """Find an immediately following, explicitly linked condition list, never general peers.

    The topic must match the time-rule anchor, and the condition passage must refer back to
    that rule's period. Scope, block and complete-unit filters apply before delivery.
    """
    from reglens.agent.tools import Toolbox, _rows
    from reglens.answer.required_evidence import _whole, body, terms

    if not re.search(r"how long|\b(?:probation|waiting)\b|minimum.{0,40}period", question, re.I):
        return []
    if filters is not None and filters.source_ids == []:
        return []
    excluded = re.findall(
        r"\bnot (?:under|subject to|in) ([a-z -]+?)(?=[,;?.]|\bcan\b|\bmay\b|$)",
        question.lower(),
    )
    ranked, counts = [], {}
    for hit in sorted(hits, key=lambda h: -len(terms(question) & terms(body(h.text)))):
        text = body(hit.text)
        if (len(terms(question) & terms(text)) < 2
                or any(phrase.strip() in text.lower() for phrase in excluded)
                or not re.search(r"\b(?:period|months?|years?|days?)\b", text, re.I)
                or re.search(r"(?:previous|preceding) paragraph", text, re.I)):
            continue
        document = (hit.source_id, hit.title)
        rank = counts.get(document, 0)
        counts[document] = rank + 1
        ranked.append((rank, hit))
    anchors = [h for _, h in sorted(ranked, key=lambda p: p[0])[:4]]
    groups, seen = [], set()
    for hit in anchors:
        rows = _rows(conn, "id = %s", [hit.id], limit=1) if conn is not None else [hit]
        if not rows or (number := _number(rows[0])) is None:
            continue
        anchor = rows[0]
        if conn is None:
            candidates = [h for h in hits if h.source_id == anchor.source_id
                          and h.title == anchor.title and _number(h) == number + 1]
            if len(candidates) != 1:
                continue
        else:
            candidates = _rows(
                conn, "source_id = %s AND title IS NOT DISTINCT FROM %s "
                "AND article IS NOT DISTINCT FROM %s AND paragraph = %s AND kind = %s",
                [anchor.source_id, anchor.title, anchor.article, str(number + 1), anchor.kind],
                limit=20,
            )
        for candidate in candidates:
            intro = re.split(r"\n\s*\([a-z]\)", body(candidate.text), maxsplit=1)[0]
            if (candidate.id in seen
                    or not re.search(r"(?:previous|preceding) paragraph", intro, re.I)
                    or not re.search(r"\bperiod\b", intro, re.I)
                    or not re.search(r"\ball (?:of )?(?:the )?following conditions", intro, re.I)):
                continue
            seen.add(candidate.id)
            group = _whole(conn, candidate, Toolbox(conn, filters=filters)) if conn else [candidate]
            if group:
                groups.append(group)
    return groups[:4]
