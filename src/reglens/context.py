"""Explicit legal constraints and tri-state coverage. Missing metadata is not a legal fact."""

from __future__ import annotations

from datetime import date

DATES = (
    "published_on",
    "effective_from",
    "effective_until",
    "application_from",
    "application_until",
)
METADATA = (*DATES, "temporal_verified", "applicability")
CONDITIONS = {"approach", "exposure_class", "jurisdiction", "national_option"}


def validate_metadata(data: dict) -> dict:
    out = {k: data[k] for k in METADATA if k in data}
    for key in DATES:
        if out.get(key) is not None:
            out[key] = date.fromisoformat(str(out[key])).isoformat()
    for start, end in (
        ("effective_from", "effective_until"),
        ("application_from", "application_until"),
    ):
        if out.get(start) and out.get(end) and out[start] >= out[end]:
            raise ValueError(f"{end} must be after {start}; upper bounds are exclusive")
    if out.get("temporal_verified") and not any(
        out.get(k) for k in ("effective_from", "application_from")
    ):
        raise ValueError("Verified temporal metadata requires a governing start date")
    conditions = out.get("applicability", {})
    if not isinstance(conditions, dict) or set(conditions) - CONDITIONS:
        raise ValueError("Unknown applicability condition")
    for key, values in conditions.items():
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(v, str) and 0 < len(v) <= 80 for v in values)
        ):
            raise ValueError(f"{key} must be a nonempty list of short strings")
    return out


def coverage(hits, filters) -> dict:
    if filters is None:
        return {"temporal": "not_requested", "applicability": "not_requested"}
    temporal = "not_requested"
    if filters.as_of:
        temporal = "known" if hits and all(h.temporal_verified for h in hits) else "unknown"
    applicability = "not_requested"
    if filters.conditions:
        applicability = (
            "known"
            if hits and all(all(k in h.applicability for k in filters.conditions) for h in hits)
            else "unknown"
        )
    return {
        "temporal": temporal,
        "applicability": applicability,
        "requested_date": filters.as_of,
        "conditions": filters.conditions or {},
    }


def instruction(filters) -> str:
    if filters is None:
        return ""
    bits = []
    if filters.as_of:
        bits.append(
            f"Requested legal application date: {filters.as_of}. Unknown intervals do not "
            "establish what applied on this date; explicitly qualify the answer."
        )
    if filters.applies_to:
        bits.append(f"Institution type: {filters.applies_to}.")
    if filters.conditions:
        bits.append(
            f"Requested applicability conditions: {filters.conditions}. Unannotated "
            "passages do not establish these conditions; say what remains unknown."
        )
    return "\n\nQuery constraints:\n" + "\n".join(bits) if bits else ""
