"""Explicit model-reported research coverage, checked against delivered evidence keys."""

from __future__ import annotations

ASPECTS = ("rule", "definitions", "exceptions", "applicability", "temporal")
INSTRUCTION = """
Before answering, check five research aspects: rule, definitions, exceptions, applicability,
temporal. Use only supplied evidence. For each, include a `research_checks` entry in the final
JSON with `aspect`, `status` (evidence_found, not_relevant, or unresolved), `citations` (the exact
keys read), and `reason`. not_relevant requires a reason. evidence_found requires citations.
Do not treat missing dates/conditions or a search with no hits as proof of absence. Mark those
unresolved. Within the existing budget, target unresolved aspects with a focused query or a
reference/definition read. Do not repeat broad searches. Report residual gaps in the answer.
This checklist records your research; it does not certify completeness or legal correctness.
"""


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
