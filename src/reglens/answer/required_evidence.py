"""Finite structural coverage signals, never a legal completeness certificate."""

import re

_STOP = set("""what which when where how does have has been being from that this these those
with without under into their they them must shall should would could all any the and for are
not only also such following include includes including requirements required conditions
institutions institution guidelines regulation article paragraph purposes referred accordance
apply applies applicable application means respect relation using use may can set out each
than more other least relevant appropriate particular provided given whether period during
after before amount amounts credit risk exposure exposures default realised calculation""".split())


def terms(text: str) -> set[str]:
    # Light normalisation only; absence is a review signal, not semantic disproof.
    return {w[:-1] if w.endswith("s") and not w.endswith("ss") else w
            for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP}


def list_question(question: str) -> bool:
    return bool(re.search(
        r"\bwhich\s+(?:(?:qualifying|short-term|short|term|additional|other|economic|"
        r"validation|direct|indirect|off-balance-sheet|types of|categories of|of the following)"
        r"\s+){0,5}(?:conditions|components|elements|requirements|tools|"
        r"responsibilities|exceptions|exposures|transactions|costs|items)|"
        r"\bwhat\b[^?]{0,100}\b(?:conditions|components|elements|requirements|tools|"
        r"responsibilities|approve|include|exceptions)|"
        r"\blist\b", question, re.I
    ))


def body(text: str) -> str:
    """Ignore deterministic hierarchy prefixes when judging lexical relevance."""
    return text.split("\n", 1)[1] if " › " in text.split("\n", 1)[0] else text


def _whole(conn, candidate, box):
    from reglens.agent.tools import _one_unit, _rows, key_of

    # Fetch one beyond the delivery ceiling so a long unit is never silently accepted.
    rows = _rows(conn, "cite = %s", [key_of(candidate)], limit=81)
    if (not rows or len(rows) > 80 or not _one_unit(rows)
            or any(r.source_id != candidate.source_id for r in rows)):
        return []
    eligible = box._eligible(rows)
    return eligible if len(eligible) == len(rows) else []


def evidence_units(
    conn, question: str, hits: list, filters=None, delivered=None, *, required_only=False
) -> list[list]:
    """At most eight whole target units from four anchors and finite candidate probes.

    Scope is source-bound. Lists use children of the same article or relevant mandatory
    siblings in a narrowly shared section. Neither registry labels nor previews are evidence.
    """
    if conn is None or not hits or (filters is not None and filters.source_ids == []):
        return []
    from reglens.agent.tools import Toolbox, _rows, key_of

    box = Toolbox(conn, filters=filters)
    candidates = []
    if re.search(
        r"\b(?:do|does|are|is)\b.{0,120}\b(?:guidelines?|guide|regulation|directive|document)"
        r".{0,100}\b(?:apply|applicable|addressed)\b|\bapplicability\b|\baddressees\b|\bscope\b",
        question, re.I,
    ):
        from reglens.sources import load_sources

        sources = {h.source_id for h in hits}

        def source_terms(text):
            return set(re.findall(r"[a-z]{3,}", text.lower())) - {
                "the", "and", "for", "eba", "ecb", "guidelines", "guide", "regulation",
                "institutions", "institution", "definition", "under", "apply", "does",
            }

        scored = [
            (len(source_terms(question) & source_terms(s.title + " " + s.label())), s.id)
            for s in load_sources(conn=conn) if s.id in sources
        ]
        best = max((n for n, _ in scored), default=0)
        matched = [s for n, s in scored if n == best and n >= 1]
        if len(matched) == 1:
            candidates += _rows(
                conn, "source_id = %s AND kind = 'paragraph' AND EXISTS "
                "(SELECT 1 FROM unnest(hierarchy) h WHERE h ~* %s)",
                [matched[0], r"^(?:[0-9. ]+)?(?:scope(?: of application)?|addressees)$"], limit=40,
            )
    if list_question(question):
        seen_anchors = set()
        articles_by_source = {}
        for hit in hits[:4]:
            anchors = _rows(conn, "id = %s", [hit.id], limit=1)
            if not anchors:
                continue
            anchor = anchors[0]
            if anchor.kind == "article" and anchor.article:
                first_article = articles_by_source.setdefault(anchor.source_id, anchor.article)
                if anchor.article != first_article:
                    continue
                identity = (anchor.source_id, anchor.article, anchor.paragraph)
                where = "source_id = %s AND article = %s"
                params = [anchor.source_id, anchor.article]
                # The question may ask for parallel requirements of an entire article.
                # For an explicit introduction only its own children are indispensable.
                if not anchor.point and re.search(r"following|include", anchor.text, re.I):
                    where += " AND paragraph IS NOT DISTINCT FROM %s"
                    params.append(anchor.paragraph)
            elif len(anchor.hierarchy) >= 4:
                path = anchor.hierarchy[:-1]
                identity = (anchor.source_id, tuple(path))
                where = "source_id = %s AND title = %s AND hierarchy[1:%s] = %s AND kind = %s"
                params = [anchor.source_id, anchor.title, len(path), path, anchor.kind]
            else:
                continue
            if identity in seen_anchors:
                continue
            seen_anchors.add(identity)
            peers = _rows(conn, where, params, limit=40)
            for peer in peers:
                child = (anchor.kind == "article" and anchor.article
                         and not anchor.point and peer.point
                         and peer.paragraph == anchor.paragraph
                         and re.search(r"following|include", anchor.text, re.I))
                # Topic overlap offers context; it does not make every neighbouring rule
                # indispensable. Require a directly requested facet for mandatory peer reads.
                facets = ("tool", "cost", "condition", "component", "element", "exception")
                direct = any(re.search(r"\b" + f + r"s?\b", question, re.I)
                             and re.search(r"\b" + f + r"s?\b", body(peer.text), re.I)
                             for f in facets)
                if required_only and not child and not direct:
                    continue
                if child or (len(terms(question) & terms(body(peer.text))) >= 2
                             and re.search(r"\bshall\b|\bshould\b|\bmust\b", peer.text, re.I)):
                    candidates.append(peer)
    # Take one candidate from each narrow section before extra members of the same
    # section. A long definition list must not crowd out a sibling discount-rate rule.
    counts = {}
    ranked = []
    seen_candidates = set()
    for candidate in candidates:
        if candidate.id in seen_candidates:
            continue
        seen_candidates.add(candidate.id)
        section = (candidate.source_id, tuple(candidate.hierarchy))
        rank = counts.get(section, 0)
        counts[section] = rank + 1
        read = delivered is not None and delivered.get(candidate.id, 0) >= len(candidate.text)
        ranked.append((read, rank, -len(terms(question) & terms(body(candidate.text))), candidate))
    candidates = [r for _, _, _, r in sorted(ranked, key=lambda x: x[:3])]
    groups, seen = [], set()
    for candidate in candidates:
        key = key_of(candidate)
        if key in seen:
            continue
        seen.add(key)
        if group := _whole(conn, candidate, box):
            groups.append(group)
            if len(groups) == 8:
                break
    return groups


def coverage_gaps(
    conn, question, data, hits, filters=None, delivered=None, evidence_hits=None
) -> list[str]:
    """Unread available units and obvious enumeration omissions, with auditable pointers."""
    from reglens.agent.tools import key_of
    from reglens.answer.conditions import condition_units

    got = delivered if delivered is not None else {h.id: len(h.text) for h in hits}
    anchors = hits if evidence_hits is None else evidence_hits
    conditions = condition_units(conn, question, anchors, filters)
    gaps = ["Read required scope/list evidence: " + key_of(group[0])
            for group in [*conditions, *evidence_units(
                conn, question, anchors, filters, got, required_only=True
            )]
            if any(got.get(r.id, 0) < len(r.text) for r in group)]
    condition_summary = bool(re.search(
        r"all (?:of the )?conditions.{0,80}(?:met|satisfied|fulfilled)",
        str(data.get("answer") or ""), re.I,
    ))
    if not list_question(question) and not condition_summary and not conditions:
        return gaps
    answer = terms(str(data.get("answer") or "") + " " + " ".join(
        c.get("text", "") for c in data.get("claims", [])
    ))
    cited = {k for c in data.get("claims", []) for k in c.get("citations", [])}
    cited |= set(re.findall(r"\[([^\[\]]+)\]", str(data.get("answer") or "")))
    required_ids = {r.id for group in conditions for r in group}
    from dataclasses import replace

    combined = {group[0].id: replace(group[0], text="\n".join(body(r.text) for r in group))
                for group in conditions}
    complete = {group[0].id: all(got.get(r.id, 0) >= len(r.text) for r in group)
                for group in conditions}
    # Preserve original C# positions. Analyse a split logical condition list only once,
    # with its complete delivered windows joined in source order.
    units = [combined.get(h.id, h) for h in hits]
    units += [r for cid, r in combined.items() if cid not in {h.id for h in hits}]
    for n, hit in enumerate(units, 1):
        if hit.id in required_ids and hit.id not in combined:
            continue
        if hit.id not in required_ids and f"C{n}" not in cited and key_of(hit) not in cited:
            continue
        if not complete.get(hit.id, got.get(hit.id, 0) >= len(hit.text)):
            continue
        source_text = body(hit.text)
        if not list_question(question) and not re.search(
            r"all of the following conditions", source_text, re.I
        ):
            continue
        parts = re.split(r"(?:^|[\n;:])\s*(?:\(([a-z])\)|([a-z])\.)\s+", source_text)
        labels = [(parts[i] or parts[i + 1]) for i in range(1, len(parts), 3)]
        items = parts[3::3]
        if len(items) < 2 or labels[:2] != ["a", "b"]:
            continue
        # A time-linked condition's predicate precedes its explanatory tail. Mentioning
        # background words from that tail must not cover an omitted payment/arrears test.
        vocab = [terms(re.split(r"[;.]", item, maxsplit=1)[0]
                       if hit.id in required_ids else item) for item in items[:12]]
        for index, words in enumerate(vocab):
            others = set().union(*(v for i, v in enumerate(vocab) if i != index))
            distinctive = words - others
            minimum = 1 if hit.id in required_ids else 2
            if len(distinctive) >= minimum and not distinctive & answer:
                gaps.append(f"Review requested list coverage in {key_of(hit)}, "
                            f"item ({labels[index]}): {items[index].strip()[:350]}")
    return list(dict.fromkeys(gaps))[:12]
