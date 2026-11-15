"""Explicitly reviewed provision metadata. CELEX dates are not inferred legal intervals."""

from pathlib import Path

import yaml

from reglens.context import METADATA, validate_metadata


def annotate(chunks, path: Path | None) -> None:
    if path is None:
        return
    records = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    sources = {c.source_id for c in chunks}
    for record in records:
        if record["source"] not in sources:
            continue
        targets = [
            c
            for c in chunks
            if c.source_id == record["source"]
            and c.ref == record["ref"]
            and ("title" not in record or c.title == record["title"])
            and ("version" not in record or c.version == record["version"])
        ]
        if not targets:
            raise ValueError(f"Metadata annotation matched no provision: {record['ref']}")
        for c in targets:
            fields = {k: getattr(c, k) for k in METADATA}
            unknown = set(record["metadata"]) - set(fields)
            if unknown:
                raise ValueError(f"Unknown metadata fields: {sorted(unknown)}")
            fields.update(record["metadata"])
            for key, value in validate_metadata(fields).items():
                setattr(c, key, value)
