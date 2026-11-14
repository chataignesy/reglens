"""Bounded contextual reads before drafting; these select evidence, not legal answers."""

import re


def requested_units(conn, question, hits, filters=None):
    """Resolve small explicit paragraph ranges only with one unambiguous document-part anchor."""
    from reglens.agent.tools import Toolbox, _rows, key_of, resolve_key

    match = re.search(r"\b(?:paragraphs|paras\.)\s*(\d+)\s*[–—-]\s*(\d+)", question, re.I)
    if conn is None or not match:
        return []
    start, end = map(int, match.groups())
    if not 0 < end - start < 6:
        return []
    anchors = {
        (h.source_id, h.title)
        for h in hits
        if h.title and re.search(r"(?<!\w)" + re.escape(h.title) + r"(?!\w)", question, re.I)
    }
    if len(anchors) != 1:
        return []
    source, title = anchors.pop()
    box = Toolbox(conn, filters=filters)
    groups = []
    for number in range(start, end + 1):
        rows = _rows(
            conn,
            "source_id = %s AND title = %s AND paragraph = %s",
            [source, title, str(number)],
            limit=20,
        )
        keys = list(dict.fromkeys(key_of(r) for r in rows))
        if len(keys) != 1:
            continue
        full = resolve_key(conn, keys[0])
        eligible = box._eligible(full)
        if full and len(full) == len(eligible):
            groups.append(eligible)
    return groups


def expand_context(conn, question, hits, filters=None, *, max_extra=4, max_chars=12000):
    """Requested units first, then parent qualifiers and existing one-hop dependencies."""
    from reglens.agent.tools import Toolbox, _rows, key_of, resolve_key
    from reglens.answer.research import expand_provisos

    if conn is None or not hits:
        return hits
    box = Toolbox(conn, filters=filters)
    out, seen, left = list(hits), {h.id for h in hits}, max_chars
    groups = requested_units(conn, question, hits, filters)
    from reglens.answer.conditions import condition_units
    from reglens.answer.required_evidence import evidence_units

    groups += condition_units(conn, question, hits, filters)
    groups += evidence_units(conn, question, hits, filters)
    peer_article = None
    # A broad question can span parallel paragraphs (e.g. retail and non-retail).
    # Require three literal question terms in the sibling body, not merely its title.
    stopwords = {
        "what",
        "which",
        "does",
        "have",
        "with",
        "from",
        "that",
        "this",
        "minimum",
        "required",
        "length",
        "under",
        "must",
        "there",
        "their",
    }
    terms = set(re.findall(r"\b[a-z]{3,}\b", question.lower())) - stopwords
    for hit in hits[:4]:
        # The trailing parent text can qualify a child point without a graph edge back.
        rows = _rows(conn, "id = %s", [hit.id], limit=1)
        if not rows or not rows[0].point or not rows[0].paragraph:
            continue
        row = rows[0]
        if peer_article is None and row.article and len(terms) >= 3:
            peer_article = (row.source_id, row.article)
            peers = _rows(
                conn,
                "source_id = %s AND article = %s AND paragraph IS DISTINCT FROM %s "
                "AND point IS NULL AND kind = 'article'",
                [row.source_id, row.article, row.paragraph],
                limit=40,
            )
            scored = sorted(
                peers, key=lambda r: -len(terms & set(re.findall(r"\b[a-z]{3,}\b", r.text.lower())))
            )
            for peer in scored[:2]:
                if len(terms & set(re.findall(r"\b[a-z]{3,}\b", peer.text.lower()))) >= 3:
                    full = resolve_key(conn, key_of(peer))
                    eligible = box._eligible(full)
                    if full and len(full) == len(eligible):
                        groups.append(eligible)
        qualifiers = _rows(
            conn,
            "source_id = %s AND article = %s AND paragraph = %s AND point IS NULL "
            "AND kind = 'article' AND body ILIKE %s",
            [row.source_id, row.article, row.paragraph, f"%point {row.point}%"],
            limit=4,
        )
        for key in dict.fromkeys(key_of(q) for q in qualifiers):
            full = resolve_key(conn, key)
            eligible = box._eligible(full)
            if full and len(full) == len(eligible):
                groups.append(eligible)
    for group in groups:
        extra = [r for r in group if r.id not in seen]
        size = sum(len(r.text) for r in extra)
        if len(out) - len(hits) + len(extra) > max_extra or size > left:
            continue
        for row in extra:
            added = row.hit(hits[0].score)
            added.generation = hits[0].generation
            out.append(added)
            seen.add(row.id)
        left -= size
    return expand_provisos(
        conn, out, filters, max_extra=max_extra - (len(out) - len(hits)), max_chars=left
    )


def requested_gaps(conn, question, hits, filters=None, delivered=None):
    """A source-bound question still requires every explicitly requested available unit."""
    from reglens.agent.tools import key_of

    got = delivered if delivered is not None else {h.id: len(h.text) for h in hits}
    return [
        "Read the explicitly requested passage: " + key_of(group[0])
        for group in requested_units(conn, question, hits, filters)
        if any(got.get(r.id, 0) < len(r.text) for r in group)
    ]


def known_definition_gaps(conn, data, filters=None):
    """Confirm availability of model-declared required definitions without trusting its guess."""
    from reglens.agent.tools import Toolbox, key_of

    if conn is None:
        return []
    requirements = [
        r["requirement"] for r in data.get("answer_requirements", []) if r["status"] == "unresolved"
    ]
    if data.get("missing_info"):
        requirements += data.get("missing_requirements", [])
    terms = []
    for requirement in requirements:
        match = re.search(r"\bdefinition of\s+['‘\"]([^’'\"]{2,80})[’'\"]", requirement, re.I)
        if match and match[1] not in terms:
            terms.append(match[1])
    gaps = []
    box = Toolbox(conn, filters=filters)
    for term in terms[:2]:
        from reglens.agent.tools import definition_rows

        rows = box._eligible(definition_rows(conn, term))
        if rows:
            keys = list(dict.fromkeys(key_of(row) for row in rows))
            gaps.append(f"Read the required definition of '{term}': " + "; ".join(keys))
    return gaps
