"""Postgres + pgvector store: chunks (full-text + embeddings) and cross-reference edges."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from dataclasses import asdict

import psycopg
from pgvector.psycopg import register_vector

from reglens.ingest.chunks import Chunk
from reglens.ingest.xrefs import Edge

DEFAULT_URL = "postgresql://reglens:reglens-local@127.0.0.1:5433/reglens"
DIM = 1024  # BGE-M3
HNSW_EF_SEARCH = 400

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chunks (
    id text PRIMARY KEY,
    source_id text NOT NULL,
    version text,
    legal_level text NOT NULL,
    applies_to text NOT NULL,
    kind text NOT NULL,
    article text,
    paragraph text,
    point text,
    ref text NOT NULL,
    title text,
    hierarchy text[] NOT NULL,
    prefix text NOT NULL,
    text text NOT NULL,
    body text NOT NULL,
    amended_by text[] NOT NULL,
    part int NOT NULL,
    text_hash text NOT NULL,
    embedding vector({DIM}),
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS cite text NOT NULL DEFAULT '';
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS source_sha256 text NOT NULL DEFAULT '';
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS published_on date;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS effective_from date;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS effective_until date;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS application_from date;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS application_until date;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS temporal_verified boolean NOT NULL DEFAULT false;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS applicability jsonb NOT NULL DEFAULT '{{}}';
CREATE INDEX IF NOT EXISTS chunks_cite ON chunks (cite);
CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_source ON chunks (source_id, article);
CREATE INDEX IF NOT EXISTS chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS edges (
    src text NOT NULL,
    kind text NOT NULL,
    target_source text NOT NULL,
    target_article text NOT NULL,
    target_paragraph text,
    target_point text
);
CREATE INDEX IF NOT EXISTS edges_src ON edges (src);
CREATE INDEX IF NOT EXISTS edges_target ON edges (target_source, target_article);
"""

_COLS = [
    "id",
    "source_id",
    "version",
    "legal_level",
    "applies_to",
    "kind",
    "article",
    "paragraph",
    "point",
    "ref",
    "title",
    "hierarchy",
    "prefix",
    "text",
    "body",
    "amended_by",
    "part",
    "cite",
    "source_sha256",
    "published_on", "effective_from", "effective_until", "application_from", "application_until",
    "temporal_verified", "applicability",
]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def connect(url: str | None = None, *, generation: str | None = None) -> psycopg.Connection:
    conn = psycopg.connect(url or os.environ.get("REGLENS_DATABASE_URL") or DEFAULT_URL,
                          connect_timeout=5)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    # HNSW is approximate: at the default ef_search (40) it missed real top-10 hits (e.g. CRR
    # Art. 185(b) ranked 2nd by an exact scan). With ~5k vectors a wide search costs
    # milliseconds and matches the exact scan; iterative scans keep filtered queries
    # (source, applies_to) from returning too few rows. Needs pgvector >= 0.8.
    conn.execute(f"SET hnsw.ef_search = {HNSW_EF_SEARCH}")
    conn.execute("SET hnsw.iterative_scan = relaxed_order")
    from reglens.index.generations import pin

    try:
        pin(conn, generation or os.environ.get("REGLENS_CORPUS_GENERATION"))
        table = conn.execute("SELECT to_regclass('chunks')").fetchone()[0]
        if table and not conn.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=%s::regclass "
            "AND attname='applicability')", (table,)
        ).fetchone()[0]:
            # Additive compatibility migration. Release the DDL lock before answering.
            for statement in SCHEMA.split(";"):
                if statement.strip().startswith("ALTER TABLE chunks"):
                    conn.execute(statement)
            conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA)
    conn.commit()


def existing_hashes(conn: psycopg.Connection) -> dict[str, tuple[str, bool]]:
    """chunk id -> (text hash, has embedding)."""
    rows = conn.execute("SELECT id, text_hash, embedding IS NOT NULL FROM chunks").fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def upsert_chunks(conn: psycopg.Connection, chunks: Iterable[Chunk]) -> int:
    """Insert or update chunks; a changed text clears its embedding. Returns rows written."""
    from reglens.index.generations import writable

    writable(conn)
    n = 0
    sql = (
        f"INSERT INTO chunks ({', '.join(_COLS)}, text_hash) "
        f"VALUES ({', '.join(['%s'] * (len(_COLS) + 1))}) "
        "ON CONFLICT (id) DO UPDATE SET "
        + ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLS[1:])
        + ", text_hash = EXCLUDED.text_hash, "
        "embedding = CASE WHEN chunks.text_hash = EXCLUDED.text_hash THEN chunks.embedding END"
    )
    with conn.cursor() as cur:
        for c in chunks:
            row = asdict(c)
            from psycopg.types.json import Jsonb

            row["applicability"] = Jsonb(row["applicability"])
            cur.execute(sql, [row[k] for k in _COLS] + [text_hash(c.text)])
            n += 1
    conn.commit()
    return n


def delete_missing(conn: psycopg.Connection, source_id: str, keep_ids: set[str]) -> int:
    from reglens.index.generations import writable

    writable(conn)
    rows = conn.execute("SELECT id FROM chunks WHERE source_id = %s", (source_id,)).fetchall()
    stale = [r[0] for r in rows if r[0] not in keep_ids]
    if stale:
        conn.execute("DELETE FROM chunks WHERE id = ANY(%s)", (stale,))
        conn.commit()
    return len(stale)


def set_embeddings(conn: psycopg.Connection, items: list[tuple[str, list[float]]]) -> None:
    from reglens.index.generations import writable

    writable(conn)
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE chunks SET embedding = %s WHERE id = %s", [(v, i) for i, v in items]
        )
    conn.commit()


def replace_edges(conn: psycopg.Connection, edges: list[Edge]) -> None:
    from reglens.index.generations import writable

    writable(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM edges")
        cur.executemany(
            "INSERT INTO edges VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (
                    e.src,
                    e.kind,
                    e.target_source,
                    e.target_article,
                    e.target_paragraph,
                    e.target_point,
                )
                for e in edges
            ],
        )
    conn.commit()
