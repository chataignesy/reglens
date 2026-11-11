"""Content-addressed, exclusive-write review artifacts; originals are never overwritten."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from reglens.config import PROJECT_ROOT


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def store(directory: Path, value: dict) -> Path:
    # JSON arrays have one representation. Dataclass tuples (e.g. citation alternatives)
    # must compare equal to the lists read back from an unchanged artifact.
    value = json.loads(json.dumps(value, ensure_ascii=False))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest(value)}.json"
    try:
        with path.open("x", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
    except FileExistsError:
        if json.loads(path.read_text(encoding="utf-8")) != value:
            raise ValueError("Existing immutable artifact was modified") from None
    return path


def adjudicate(
    artifact: Path, *, reviewer: str, decision: str, reason: str, directory: Path | None = None
) -> Path:
    if not reviewer.strip() or not reason.strip():
        raise ValueError("Reviewer identity and reasoning are required")
    if decision not in {"accepted", "rejected", "needs_evidence"}:
        raise ValueError("Unknown adjudication decision")
    raw = artifact.read_bytes()
    json.loads(raw)  # review an actual structured artifact, never an absent path
    record = {
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "artifact": str(artifact.resolve()),
        "reviewer": reviewer,
        "decision": decision,
        "reason": reason,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    return store(directory or PROJECT_ROOT / "data/evals/adjudications", record)


def adjudications(directory: Path | None = None) -> dict[str, list[dict]]:
    """Read verified records by artifact hash; conflicting opinions remain visible."""
    out: dict[str, list[dict]] = {}
    for path in (directory or PROJECT_ROOT / "data/evals/adjudications").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if path.stem != digest(record):
            raise ValueError(f"Adjudication was modified: {path.name}")
        out.setdefault(record["artifact_sha256"], []).append(record)
    return out
