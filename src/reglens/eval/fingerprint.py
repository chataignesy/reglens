"""Cache identity for evaluation artifacts (review 2026-11-08: F4).

A cached answer is reused only if everything that produced it is unchanged: the question
text, the corpus/index generation, the prompt and code of the answering path, and the model
and settings. Anything else gets a new namespace (old runs stay on disk, never mixed in).
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import reglens

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


@lru_cache(maxsize=4)
def _corpus(conn_id: int, conn) -> str:
    row = conn.execute(
        "SELECT md5(string_agg(id || ':' || text_hash || ':' || cite, ',' ORDER BY id)), "
        "(SELECT md5(string_agg(src || kind || target_source || target_article || "
        "coalesce(target_paragraph, '') || coalesce(target_point, ''), ',' ORDER BY "
        "src, kind, target_source, target_article, target_paragraph, target_point)) FROM edges) "
        "FROM chunks"
    ).fetchone()
    return sha(f"{row[0]}|{row[1]}")


def corpus_fingerprint(conn) -> str:
    """Chunks (ids, text hashes, citation keys) and graph edges currently indexed."""
    return _corpus(id(conn), conn)


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
