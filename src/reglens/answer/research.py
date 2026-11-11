"""Explicit model-reported research coverage, checked against delivered evidence keys."""

from __future__ import annotations

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
"""


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
