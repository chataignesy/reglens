"""Cache identity for evaluation artifacts (review 2026-11-08: F4).

A cached answer is reused only if everything that produced it is unchanged: the question
text, the corpus/index generation, the prompt and code of the answering path, and the model
and settings. Anything else gets a new namespace (old runs stay on disk, never mixed in).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import reglens
from reglens.config import PROJECT_ROOT

_PKG = Path(reglens.__file__).parent

# Files whose content shapes an answer (retrieval included: it chooses the passages).
RETRIEVAL_FILES = [
    "retrieve/search.py",
    "retrieve/glossary.py",
    "retrieve/glossary.yaml",
    "index/embed.py",
]
SINGLE_FILES = ["answer/pipeline.py", "answer/prompts.py", "answer/schema.py", *RETRIEVAL_FILES]
AGENT_FILES = [
    *SINGLE_FILES,
    "agent/run.py",
    "agent/tools.py",
    "agent/api_loop.py",
    "agent/mcp_server.py",
    "ingest/cite.py",
]


def sha(text: str, n: int = 12) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def code_hash(files: list[str]) -> str:
    h = hashlib.sha256()
    for rel in files:
        path = _PKG / rel
        h.update(rel.encode())
        if path.exists():
            h.update(path.read_bytes())
    return h.hexdigest()[:12]


# Every chunk column that can change retrieval inclusion (applies_to, filters), source
# classification (legal_level, kind), dates (version), citation keys or text (second review S4).
_CHUNK_FIELDS = (
    "id", "source_id", "text_hash", "cite", "applies_to", "legal_level", "version", "kind",
    "ref", "title", "article", "paragraph", "point", "part", "source_sha256",
    "array_to_string(amended_by, '|')",
)


def _corpus(conn) -> str:
    row_expr = " || '~' || ".join(f"coalesce({c}::text, '')" for c in _CHUNK_FIELDS)
    row = conn.execute(
        f"SELECT md5(string_agg({row_expr}, ',' ORDER BY id)), "
        "(SELECT md5(string_agg(src || kind || target_source || target_article || "
        "coalesce(target_paragraph, '') || coalesce(target_point, ''), ',' ORDER BY "
        "src, kind, target_source, target_article, target_paragraph, target_point)) FROM edges) "
        "FROM chunks"
    ).fetchone()
    registry = PROJECT_ROOT / "sources.yaml"  # labels, legal levels, dates, applicability
    reg = hashlib.sha256(registry.read_bytes()).hexdigest() if registry.exists() else ""
    return sha(f"{row[0]}|{row[1]}|{reg}")


def corpus_fingerprint(conn) -> str:
    """Chunks (text hashes, citation keys and all answer-relevant metadata), graph edges and
    the source registry. Computed fresh on every call (~0.1 s): no memo can go stale after a
    metadata-only refresh."""
    return _corpus(conn)


def namespace(kind: str, conn, model: str, settings: dict, suffix: str = "") -> str:
    """'single-<hash>' or 'agent-<hash>': code, model, settings and corpus generation."""
    files = AGENT_FILES if kind == "agent" else SINGLE_FILES
    parts = [
        code_hash(files),
        model,
        json.dumps(settings, sort_keys=True),
        corpus_fingerprint(conn),
    ]
    return f"{kind}-{sha('|'.join(parts), 10)}{suffix}"


def question_hash(question: str) -> str:
    return sha(question.strip(), 8)
