"""Read and cite structural amendment introductions; do not relax citation verification."""

import re


def parent_units(conn, hits, filters=None):
    from reglens.agent.tools import Toolbox, _rows
    from reglens.answer.required_evidence import _whole, body

    if conn is None or (filters is not None and filters.source_ids == []):
        return []
    out, seen = [], set()
    for hit in hits[:8]:
        anchors = _rows(conn, "id = %s", [hit.id], limit=1)
        if not anchors or anchors[0].kind != "article":
            continue
        row = anchors[0]
        point = row.point or ""
        for _ in range(2):
            if not re.fullmatch(r"(?:\([^()]+\)){2,}", point):
                break
            point = re.sub(r"\([^()]+\)$", "", point)
            candidates = _rows(
                conn, "source_id = %s AND article = %s AND paragraph IS NOT DISTINCT FROM %s "
                "AND kind = 'article' AND point = %s",
                [row.source_id, row.article, row.paragraph, point], limit=20,
            )
            for parent in candidates:
                if parent.id in seen or not re.search(
                    r"\bArticle\s+\d+[a-z]?\b.{0,100}\b(?:amended|replaced|inserted|deleted)\b",
                    body(parent.text), re.I,
                ):
                    continue
                seen.add(parent.id)
                if group := _whole(conn, parent, Toolbox(conn, filters=filters)):
                    out.append((row.id, group))
                    if len(out) == 4:
                        return out
    return out


def citation_gaps(conn, data, hits, filters=None, delivered=None, evidence_hits=None):
    from reglens.agent.tools import key_of
    from reglens.answer.verify import _norm_numbers

    anchors = hits if evidence_hits is None else evidence_hits
    parents = parent_units(conn, anchors, filters)
    if not parents:
        return []
    got = delivered if delivered is not None else {h.id: len(h.text) for h in anchors}
    by_id = {h.id: h for h in anchors}
    by_cite = {f"C{i}": h.id for i, h in enumerate(hits, 1)}
    by_cite.update({key_of(h): h.id for h in hits})
    gaps = []
    for child_id, group in parents:
        child = by_id[child_id]
        parent_ids = {r.id for r in group}
        parent_numbers = set().union(*(_norm_numbers(r.text) for r in group))
        for claim in data.get("claims", []):
            cited_ids = {by_cite.get(c) for c in claim.get("citations", [])}
            if child_id not in cited_ids:
                continue
            needed = (_norm_numbers(claim.get("text", "")) - _norm_numbers(child.text))
            if not needed & parent_numbers:
                continue
            if any(got.get(r.id, 0) < len(r.text) for r in group):
                gaps.append("Read required amendment context: " + key_of(group[0]))
            elif not parent_ids <= cited_ids:
                gaps.append("Review required citation context: cite " + key_of(group[0])
                            + " with the amendment child to support "
                            + ", ".join(sorted(needed & parent_numbers)))
    return list(dict.fromkeys(gaps))
