"""The answer contract: the JSON reply the model must give, validated before use.

A reply that cannot be parsed, or parses but breaks the contract (no answer text, claims
without citations, unknown claim kinds, ...), is never shown as an ordinary answer. The
pipeline retries once; if the retry also fails, the answer is marked *unverified* and the raw
output is kept for diagnosis only (see `Answer.unverified`).
"""

from __future__ import annotations

import json

KINDS = ("law", "supervisory", "interpretation")


def problems(data: object) -> list[str]:
    """Contract violations in a parsed reply (empty list: valid)."""
    if not isinstance(data, dict):
        return ["reply is not a JSON object"]
    out = []
    abstain = data.get("abstain", False)
    if not isinstance(abstain, bool):
        out.append("'abstain' is not true/false")
        abstain = bool(abstain)
    for key in ("answer", "abstain_reason"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            out.append(f"'{key}' is not a string")
    if "missing_info" in data and not isinstance(data["missing_info"], bool):
        out.append("'missing_info' is not true/false")
    if "research_needed" in data:
        if not isinstance(data["research_needed"], bool):
            out.append("'research_needed' is not true/false")
        elif data["research_needed"] and not data.get("missing_info"):
            out.append("research_needed requires missing_info")
    if "missing_requirements" in data:
        requirements = data["missing_requirements"]
        if not isinstance(requirements, list) or not all(
            isinstance(r, str) and r.strip() for r in requirements
        ):
            out.append("'missing_requirements' must be a list of nonempty strings")
        elif bool(requirements) != bool(data.get("missing_info")):
            out.append("missing_requirements must agree with missing_info")
    claims = data.get("claims") or []
    if "answer_requirements" in data:
        requirements = data["answer_requirements"]
        if not isinstance(requirements, list) or len(requirements) > 12:
            out.append("answer_requirements must be a list of at most 12 requested facts")
        else:
            for n, r in enumerate(requirements, 1):
                if not isinstance(r, dict) or not (
                    isinstance(r.get("requirement"), str) and r["requirement"].strip()
                    and r.get("status") in ("supported", "unresolved")
                    and isinstance(r.get("retrievable"), bool)
                    and isinstance(r.get("citations"), list)
                    and all(isinstance(c, str) and c.strip() for c in r["citations"])
                    and (r["status"] != "supported" or bool(r["citations"]))
                ):
                    out.append(f"invalid answer requirement {n}")
    if not isinstance(claims, list):
        return [*out, "'claims' is not a list"]
    if abstain:
        return out
    if not str(data.get("answer") or "").strip():
        out.append("empty answer text")
    if not claims:
        out.append("no claims")
    for n, c in enumerate(claims, 1):
        if not isinstance(c, dict):
            out.append(f"claim {n} is not an object")
            continue
        if not str(c.get("text") or "").strip():
            out.append(f"claim {n} has no text")
        kind = c.get("kind")
        if kind not in KINDS:
            out.append(f"claim {n} has kind {kind!r} (expected {', '.join(KINDS)})")
        cites = c.get("citations")
        if not isinstance(cites, list) or not all(isinstance(x, str) for x in cites):
            out.append(f"claim {n} citations are not a list of strings")
        elif not cites and kind != "interpretation":
            out.append(f"claim {n} cites nothing")
    return out


def parse_reply(text: str) -> tuple[dict | None, list[str]]:
    """(parsed reply, contract problems). Parsing tolerates code fences and stray prose."""
    from reglens.answer.pipeline import _parse_json

    try:
        data = _parse_json(text)
    except (ValueError, json.JSONDecodeError) as e:
        return None, [f"unparseable model output: {e}"]
    return data, problems(data)


def retry_note(found: list[str]) -> str:
    """Appended to the prompt for the one retry after an invalid reply."""
    return (
        "\n\nYour previous reply could not be used: "
        + "; ".join(found[:5])
        + ". Reply again with ONE JSON object in the required format and nothing else."
    )
