"""Explicit model-reported research coverage, checked against delivered evidence keys."""

from __future__ import annotations

import re

ASPECTS = ("rule", "definitions", "exceptions", "applicability", "temporal")
INSTRUCTION = """
Scope your research to the question's actual requirements and stated assumptions. Check rule,
definitions, exceptions, applicability and temporal evidence ONLY to the extent each can change
the requested answer. Include `research_checks` entries with `aspect`, `status` (evidence_found,
not_relevant, unresolved), `citations` (exact read keys), and `reason`. evidence_found requires
citations; not_relevant requires a reason. This is research coverage, not legal certification.

Do not invent extra requirements. For a question about what a specified document says, answer
from that document; do not also require proof of current legal applicability, future revisions,
all omitted background provisions, or everything the document does not say. Answering that the
specified passages do not establish something can itself completely answer the question.
Missing temporal_verified metadata alone is not a missing answer fact. Keep any date-coverage
warning separate. If the user actually asks for current law, a legal application date, a
transition, or applicability that changes the conclusion, investigate and qualify unresolved
facts. Explicit dates supported by the passage text are evidence; never invent verified dates.

Set `missing_info` true ONLY for an unanswered requirement of the actual question. List those
requirements in `missing_requirements` (empty when false). Set `research_needed` true ONLY when
missing_info is true AND another corpus-tool lookup could obtain the missing evidence. Set it
false for a complete scoped answer, optional background, missing user inputs or evidence that
cannot be obtained from this corpus. Keep genuine limitations visible even when further tools
cannot resolve them. Out-of-scope refusal is not a research gap.

If a required, retrievable gap remains, use a focused lookup for that gap within the existing
budget. Do not repeat broad searches or keep investigating optional checklist aspects. Once the
asked facts and indispensable conditions are supported, finish; an unused tool budget is fine.
Do not present absent evidence or an empty search as proof of legal absence.
Before a definitive yes/no answer, identify the operative rule AND any explicit proviso that
could change the result for the supplied scenario. 'Subject to paragraphs ...' means those
exceptions must be checked, not assumed inapplicable. A passage saying it omits a requested
calculation component, discount rate, condition or applicable exception is a required gap even
if other parts can be answered. Do not say 'not covered' and simultaneously report completeness.
Do not require an input when another cumulative condition already determines the outcome.
Treat a classification explicitly supplied by the scenario (e.g. a corporate or eligible
collateral) as an assumption, not a definition to re-prove. Read a definition when applying it
is actually necessary (e.g. deciding whether given sales make a corporate a large corporate).
Reserve tool calls for full reads of passages you cite; omit optional material rather than
citing a truncated preview. A successful answer need not exhaust the research budget.

Break the actual question into a short `answer_requirements` list before finalising. Each entry
has `requirement` (one requested fact or indispensable condition), `status` (supported or
unresolved), `citations` (read evidence keys), and `retrievable` (boolean). Supported entries
require citations. Unresolved entries must describe the specific missing fact. Do not list
optional tests, templates, adjacent topics or metadata as requirements unless the question
asks for them. For multi-part questions, cover each part; for a fallback rule, cover the normal
rule, intermediate alternatives and the condition permitting the fallback. Distinguish a
covered portion from an uncovered portion when the scenario splits an exposure. Investigate
exceptions that refer BACK to the rule as well as references appearing in the rule itself.
Only treat an exception as applicable after reading its conditions. This list is a model
self-check, not proof that every legal dependency has been discovered.
"""

_PROVISO = re.compile(
    r"(?:subject to|by way of derogation from|without prejudice to)\s+paragraphs?\s+"
    r"(\d+[a-z]?(?:(?:\s*,\s*|\s+and\s+|\s+to\s+)\d+[a-z]?){0,8})",
    re.I,
)


def provisos(hit) -> list[str]:
    """Explicit same-article exceptions only; not an unbounded traversal of all references."""
    out = []
    for group in _PROVISO.findall(hit.text):
        numbers = re.findall(r"\d+[a-z]?", group)
        if " to " in group.lower() and len(numbers) == 2 and all(n.isdigit() for n in numbers):
            numbers = [
                str(n)
                for n in range(int(numbers[0]), min(int(numbers[1]) + 1, int(numbers[0]) + 8))
            ]
        out.extend(numbers)
    return list(dict.fromkeys(out))


_ARTICLE_PROVISO = re.compile(
    r"(?P<relation>subject to|by way of derogation from|without prejudice to|in accordance with)"
    r"\s+Article\s+(?P<article>\d+[a-z]?)(?:\((?P<paragraph>\d+[a-z]?)\))?(?!\w)",
    re.I,
)
_EXCEPTION = r"shall not apply|do not apply|derogation|exempt|non-application"


def article_provisos(hit, *, required_only: bool = False) -> list[tuple[str, str | None]]:
    """References for pre-reading; only explicit qualifications establish a mandatory gap.

    'In accordance with' is a candidate dependency, not proof that the target must be read
    for this question. Required model-reported gaps still escalate independently.
    """
    out = []
    for m in _ARTICLE_PROVISO.finditer(hit.text):
        if required_only and m["relation"].lower() == "in accordance with":
            continue
        if re.match(
            r"\s+of\s+(?:Regulation|Directive|Delegated|Implementing)", hit.text[m.end() :], re.I
        ):
            continue
        out.append((m["article"], m["paragraph"]))
    return list(dict.fromkeys(out))


def incoming_exceptions(conn, source_id: str, articles: list[str], filters=None) -> list:
    """Bounded candidates pointing back to a rule, not a claim that an exception applies.

    Uses indexed reverse edges; missing edges or other wording can still hide exceptions.
    """
    from reglens.agent.tools import Toolbox, _rows

    return Toolbox(conn, filters=filters)._eligible(
        _rows(
            conn,
            "source_id = %s AND body ~* %s AND EXISTS "
            "(SELECT 1 FROM edges e WHERE e.src = chunks.id AND e.target_source = %s "
            "AND e.target_article = ANY(%s))",
            [source_id, _EXCEPTION, source_id, articles],
            limit=40,
        )
    )


def expand_provisos(
    conn, hits: list, filters=None, *, max_extra: int = 4, max_chars: int = 12000
) -> list:
    """Read a bounded one-hop set before drafting, preserving every caller filter."""
    if conn is None or max_extra <= 0 or max_chars <= 0:
        return hits
    from reglens.agent.tools import Toolbox, _rows, key_of, resolve_key

    box = Toolbox(conn, filters=filters)
    out, seen, left = list(hits), {h.id for h in hits}, max_chars
    incoming_by_source = {}
    sources = {h.source_id for h in hits[:4] if re.match(r"Art\.\s*\d", h.ref)}
    for source_id in sorted(sources):
        articles = list(
            dict.fromkeys(
                m[1]
                for h in hits[:4]
                if h.source_id == source_id and (m := re.match(r"Art\.\s*(\d+[a-z]?)", h.ref))
            )
        )
        incoming_by_source[source_id] = incoming_exceptions(conn, source_id, articles, filters)
    resolved = set()
    for h in hits[:4]:
        article = re.match(r"Art\.\s*(\d+[a-z]?)", h.ref)
        if not article:
            continue
        paras = provisos(h)
        rows = (
            box._eligible(
                _rows(
                    conn,
                    "source_id = %s AND article = %s AND paragraph = ANY(%s)",
                    [h.source_id, article[1], paras],
                    limit=20,
                )
            )
            if paras
            else []
        )
        # Do not spend every slot on windows of the first (possibly irrelevant) proviso.
        # Prefer complete small units; leave oversized units for targeted agent research.
        groups = [[r for r in rows if r.paragraph == para] for para in paras]
        for target_article, para in article_provisos(h)[:4]:
            groups.append(
                box._eligible(
                    _rows(
                        conn,
                        "source_id = %s AND article = %s" + (" AND paragraph = %s" if para else ""),
                        [h.source_id, target_article, *([para] if para else [])],
                        limit=40,
                    )
                )
            )
        # Exceptions may point to this article without the article pointing back.
        for candidate in incoming_by_source.get(h.source_id, [])[:4]:
            key = key_of(candidate)
            if key not in resolved:
                resolved.add(key)
                groups.append(box._eligible(resolve_key(conn, key)))
        for group in sorted(groups, key=len):
            group = [r for r in group if r.id not in seen]
            if not group:
                continue
            if (
                len(out) - len(hits) + len(group) > max_extra
                or sum(len(r.text) for r in group) > left
            ):
                continue
            for row in group:
                added = row.hit(h.score)
                added.generation = h.generation
                out.append(added)
                seen.add(row.id)
                left -= len(row.text)
    return out


def guard(
    question: str,
    data: dict,
    hits: list,
    *,
    conn=None,
    filters=None,
    delivered=None,
    evidence_hits=None,
) -> list[str]:
    """Independent, auditable conservative signals; this does not prove completeness."""
    if data.get("abstain"):
        return []
    from reglens.answer.context_plan import known_definition_gaps, requested_gaps

    gaps = known_definition_gaps(conn, data, filters)
    gaps += requested_gaps(
        conn, question, hits if evidence_hits is None else evidence_hits, filters, delivered
    )
    required_gaps = []
    delivered = {f"C{n}" for n in range(1, len(hits) + 1)}
    # On the API agent's pre-final check, keys are tool keys, not yet C# keys.
    # Delivery is validated after resolution; unresolved entries still trigger a focused lookup.
    for requirement in data.get("answer_requirements", []):
        unresolved = requirement["status"] == "unresolved"
        if hits and requirement["status"] == "supported":
            unresolved = not set(requirement["citations"]) <= delivered
        if unresolved:
            required_gaps.append(requirement["requirement"])
            if requirement["retrievable"]:
                gaps.append("Resolve the required answer fact: " + requirement["requirement"])
    if required_gaps:
        data["missing_info"] = True
        data["missing_requirements"] = list(
            dict.fromkeys(
                [
                    *data.get("missing_requirements", []),
                    *required_gaps,
                ]
            )
        )
    # Document-content questions may be fully answered by identifying a document's limits.
    document_bound = bool(
        re.search(
            r"foreword|what (?:does|do|did).*(?:document|guide|passages).*say|"
            r"(?:according to|in) (?:the |these )?(?:specified )?(?:foreword|passages)",
            question,
            re.I,
        )
    )
    date_required = bool(
        re.search(
            r"current law|as of|in force|historical|version|applic(?:ation|able) date",
            question,
            re.I,
        )
    )
    document_bound = document_bound and not date_required
    text = str(data.get("answer") or "")
    if not document_bound:
        if data.get("missing_info") and data.get("research_needed") is False:
            for requirement in data.get("missing_requirements", []):
                if re.search(
                    r"not (?:in|covered by) (?:the )?(?:retrieved )?passages|"
                    r"passages (?:do not|don't) (?:state|include)|did not read",
                    requirement,
                    re.I,
                ) and not re.search(
                    r"metadata|verified.*interval|not (?:needed|required)|"
                    r"not (?:provided|given) in the question",
                    requirement,
                    re.I,
                ):
                    gaps.append("Try a focused lookup for the required gap: " + requirement)
        for m in re.finditer(
            r"(?:not covered\s*[:.]|(?:the )?passages (?:do not|don't) (?:cover|set out|give)|"
            r"I (?:did not|haven't|have not) (?:read|retrieve))[^\n]{0,600}",
            text,
            re.I,
        ):
            statement = m[0]
            definition = re.search(
                r"definition of ['‘\"]?([a-z -]+?)(?:[,.‘’'\"]|$)", statement, re.I
            )
            if (
                definition
                and re.search(r"\b" + re.escape(definition[1].strip()) + r"\b", question, re.I)
                and not re.search(r"defin|what (?:is|are)|meaning", question, re.I)
            ):
                continue  # the scenario already supplies this classification
            # Metadata uncertainty / optional background are not missing asked facts.
            if re.search(
                r"not (?:needed|required|necessary)|optional",
                statement,
                re.I,
            ):
                continue
            if not date_required and re.search(
                r"metadata|version|publication|download|February 2019 date", statement, re.I
            ):
                continue
            gaps.append("Check the stated evidence gap: " + statement)
        cited = {k for c in data.get("claims", []) for k in c.get("citations", [])}
        cited |= set(re.findall(r"\[(C\d+)\]", text))
        available = {(h.source_id, re.sub(r"\s+", "", h.ref).lower()) for h in hits}
        for n, h in enumerate(hits, 1):
            if f"C{n}" not in cited:
                continue
            art = re.match(r"Art\.\s*(\d+[a-z]?)", h.ref)
            if art:
                read_exception = any(
                    f"C{i}" in cited
                    and other.source_id == h.source_id
                    and re.sub(r"\s+", "", other.ref).lower()
                    in {f"art.{art[1]}({p})" for p in provisos(h)}
                    for i, other in enumerate(hits, 1)
                )
                if read_exception and re.match(r"\W*yes\b", text, re.I):
                    continue  # an evidenced election, not a denial based only on the general rule
                for para in provisos(h):
                    target = f"Art. {art[1]}({para})"
                    if (h.source_id, target.replace(" ", "").lower()) not in available:
                        gaps.append(f"Check the explicit proviso {h.source_id} {target}")
                for target_article, para in article_provisos(h, required_only=True):
                    target = f"Art. {target_article}" + (f"({para})" if para else "")
                    present = any(
                        other.source_id == h.source_id
                        and (other.ref == target or other.ref.startswith(target + "("))
                        for other in hits
                    )
                    if not present:
                        gaps.append(f"Check the explicit dependency {h.source_id} {target}")
    if gaps:
        data["missing_info"], data["research_needed"] = True, True
        data["missing_requirements"] = list(
            dict.fromkeys([*data.get("missing_requirements", []), *gaps])
        )
    return gaps


def needs_research(answer) -> bool:
    """Preserve gaps without re-running tools for explicitly unresolvable/optional work.

    Legacy records lacking the new decision retain their existing fallback behavior.
    """

    def get(key, default=None):
        return (
            answer.get(key, default) if isinstance(answer, dict) else getattr(answer, key, default)
        )

    return bool(get("missing_info")) and get("research_needed") is not False


def report(data: dict, delivered: set[str], partial: set[str] | None = None) -> dict:
    rows = data.get("research_checks", [])
    if not isinstance(rows, list):
        rows = []
    out = {}
    for aspect in ASPECTS:
        candidates = [r for r in rows if isinstance(r, dict) and r.get("aspect") == aspect]
        status, reason, cites = "unresolved", "Research check not reported", []
        if len(candidates) == 1:
            row = candidates[0]
            reason = row.get("reason", "")
            cites = row.get("citations", [])
            status = row.get("status")
            valid = (
                isinstance(reason, str)
                and bool(reason.strip())
                and isinstance(cites, list)
                and all(isinstance(c, str) for c in cites)
                and status in {"evidence_found", "not_relevant", "unresolved"}
            )
            if not valid:
                status, reason, cites = "unresolved", "Invalid research check", []
            elif status == "evidence_found" and (
                not cites or not set(cites) <= delivered or set(cites) & (partial or set())
            ):
                status, reason = "unresolved", "Evidence was absent, unread, or only read in part"
        out[aspect] = {"status": status, "reason": reason, "citations": cites}
    return {
        "basis": "model_reported; delivery_checked",
        "checks": out,
        "unresolved": [k for k, r in out.items() if r["status"] == "unresolved"],
    }


def completion_note(data: dict) -> str | None:
    if not needs_research(data):
        return None
    if requirements := data.get("missing_requirements"):
        return (
            "Target only these unanswered requirements of the question: "
            + "; ".join(requirements)
            + ". Read the needed evidence; do not expand into optional background."
        )
    # Older cached replies remain usable, with explicitly unknown checklist coverage.
    if "research_checks" not in data:
        return None
    if not isinstance(data["research_checks"], list):
        return "Report the five research checks in the required structured format."
    unresolved = [
        r
        for r in data.get("research_checks", [])
        if isinstance(r, dict) and r.get("aspect") in ASPECTS and r.get("status") == "unresolved"
    ]
    if not unresolved:
        return None
    return (
        "Target the unresolved research checks: "
        + "; ".join(f"{r['aspect']}: {str(r.get('reason', ''))[:300]}" for r in unresolved)
        + ". Stop if the necessary evidence is unavailable; disclose the gap."
    )
