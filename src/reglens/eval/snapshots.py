"""Frozen references and future holdout checks. Existing development data is never a holdout."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path

from reglens.config import PROJECT_ROOT
from reglens.eval.artifacts import digest, store
from reglens.eval.golden import GoldenItem, _parse, load_golden
from reglens.sources import load_sources


def question_key(question: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", question).casefold()))


def questions(value):
    if isinstance(value, dict):
        if isinstance(value.get("question"), str):
            yield question_key(value["question"])
        for v in value.values():
            yield from questions(v)
    elif isinstance(value, list):
        for v in value:
            yield from questions(v)


def payload(items: list[GoldenItem], *, role: str = "development") -> dict:
    if role not in {"development", "holdout"}:
        raise ValueError("Snapshot role must be development or holdout")
    if not items or any(i.status != "verified" for i in items):
        raise ValueError("Snapshots require nonempty, verified items")
    if len({i.id for i in items}) != len(items):
        raise ValueError("Duplicate evaluation IDs")
    if len({question_key(i.question) for i in items}) != len(items):
        raise ValueError("Duplicate normalized questions")
    return {
        "schema": 1,
        "role": role,
        "items": [asdict(i) for i in items],
        "sources": [asdict(s) for s in load_sources()],
    }


def freeze(
    items: list[GoldenItem],
    *,
    role: str = "development",
    directory: Path | None = None,
    development: list[GoldenItem] | None = None,
    history: Path | None = None,
) -> Path:
    data = payload(items, role=role)
    if role == "holdout":
        known = {
            question_key(i.question)
            for i in (development if development is not None else load_golden())
        }
        history = history if history is not None else PROJECT_ROOT / "data/evals"
        for path in history.rglob("*.json"):
            # Fail closed if history cannot be audited.
            known.update(questions(json.loads(path.read_text(encoding="utf-8"))))
        overlap = [i.id for i in items if question_key(i.question) in known]
        if overlap:
            raise ValueError(
                "Holdout questions already used in development/history: " + ", ".join(overlap)
            )
    return store(directory or PROJECT_ROOT / "evals/frozen", data)


def items_from_payload(data: dict) -> list[GoldenItem]:
    if data.get("schema") != 1 or data.get("role") not in {"development", "holdout"}:
        raise ValueError("Invalid evaluation snapshot")
    source_ids = {s["id"] for s in data["sources"]}
    items = [_parse(raw, "frozen snapshot", source_ids) for raw in data["items"]]
    if len({i.id for i in items}) != len(items):
        raise ValueError("Duplicate frozen IDs")
    return items


def load(path: Path) -> tuple[dict, list[GoldenItem]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if path.stem != digest(data):
        raise ValueError("Frozen snapshot hash differs; references were changed")
    return data, items_from_payload(data)


def run_items(manifest: dict, requested: list[GoldenItem] | None = None) -> list[GoldenItem]:
    frozen = manifest.get("dataset")
    if not frozen:
        return requested if requested is not None else load_golden()  # labelled legacy fallback
    if digest(frozen["snapshot"]) != frozen["sha256"]:
        raise ValueError("Run's frozen evaluation references were changed")
    items = items_from_payload(frozen["snapshot"])
    ids = {i.id for i in requested} if requested is not None else None
    return [i for i in items if ids is None or i.id in ids]
