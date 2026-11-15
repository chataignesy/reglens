"""Immutable answer attempts with a replaceable index of reusable results.

Provider outages remain in the attempt history, but never become reusable answers.
Model/evidence failures remain reusable so reruns cannot silently select better answers.
Legacy standalone artifacts are read without rewriting them.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from reglens.answer.route import _interrupted as interrupted


def cached(index: Path) -> tuple[dict, Path] | None:
    pointer = index.with_suffix(".index.json")
    if pointer.exists():
        index = pointer
    if not index.exists():
        return None
    value = json.loads(index.read_text(encoding="utf-8"))
    path = index
    if value.get("cache_format") == "attempt-index-v1":
        path = (index.parent / value["artifact"]).resolve()
        if not path.is_relative_to((index.parent / "attempts").resolve()):
            raise ValueError("Answer cache index points outside its attempt directory")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != value["sha256"]:
            raise ValueError("Answer cache attempt hash mismatch")
        value = json.loads(raw)
    return None if interrupted(value) else (value, path)


def save(index: Path, record: dict) -> Path:
    attempts = index.parent / "attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    path = attempts / f"{index.stem}-{uuid4().hex}.json"
    raw = json.dumps(record, indent=2, ensure_ascii=False).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(raw)
    if not interrupted(record):
        pointer = {
            "cache_format": "attempt-index-v1",
            "artifact": f"attempts/{path.name}",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        index = index.with_suffix(".index.json")
        tmp = index.with_name(f".{index.name}-{uuid4().hex}.tmp")
        try:
            tmp.write_text(json.dumps(pointer, indent=2), encoding="utf-8")
            os.replace(tmp, index)
        finally:
            tmp.unlink(missing_ok=True)
    return path
