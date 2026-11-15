"""Immutable corpus snapshots. Build privately; publish a validated generation atomically.

Each snapshot owns chunks and edges in its own schema. Connections pin search_path once, so
an answer cannot mix snapshots when another process publishes. The public catalog is tiny;
existing public tables are adopted as the legacy generation without copying or changing data.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict

from psycopg import Connection, sql
from psycopg.types.json import Jsonb

CATALOG = """
CREATE TABLE IF NOT EXISTS public.corpus_generations (
    id text PRIMARY KEY,
    schema_name text UNIQUE NOT NULL,
    state text NOT NULL CHECK (state IN ('building', 'ready')),
    base_id text,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.corpus_head (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    generation_id text NOT NULL REFERENCES public.corpus_generations(id)
);
"""
LOCK = 771984231


def catalog_exists(conn) -> bool:
    return conn.execute("SELECT to_regclass('public.corpus_head')").fetchone()[0] is not None


def install(conn) -> None:
    """Idempotent adoption. Does not rename/delete any existing user tables."""
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
    conn.execute(CATALOG)
    conn.execute(
        "INSERT INTO public.corpus_generations(id,schema_name,state) "
        "VALUES ('legacy','public','ready') ON CONFLICT DO NOTHING"
    )
    conn.execute(
        "INSERT INTO public.corpus_head(singleton,generation_id) "
        "VALUES(true,'legacy') ON CONFLICT DO NOTHING"
    )
    conn.commit()


def active(conn) -> str:
    if not catalog_exists(conn):
        return "legacy"
    return conn.execute("SELECT generation_id FROM public.corpus_head WHERE singleton").fetchone()[
        0
    ]


def pin(conn, generation: str | None = None) -> str:
    """Called once at connection creation. Building snapshots cannot be selected as readers."""
    if not catalog_exists(conn):
        if generation not in (None, "legacy"):
            raise ValueError(f"Unknown corpus generation: {generation}")
        return "legacy"
    gid = generation or active(conn)
    row = conn.execute(
        "SELECT schema_name,state FROM public.corpus_generations WHERE id=%s", (gid,)
    ).fetchone()
    if row is None or row[1] != "ready":
        raise ValueError(f"Corpus generation is not published/ready: {gid}")
    conn.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(row[0])))
    return gid


def current(conn) -> str:
    """Identity pinned to this connection, not the head which may have moved."""
    if not isinstance(conn, Connection):
        return "legacy"  # lightweight fake connections used by offline tests
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    if schema == "public":
        return "legacy"
    row = conn.execute(
        "SELECT id FROM public.corpus_generations WHERE schema_name=%s", (schema,)
    ).fetchone()
    return row[0] if row else "legacy"


def metadata(conn) -> dict:
    if not isinstance(conn, Connection) or not catalog_exists(conn):
        return {}
    row = conn.execute(
        "SELECT metadata FROM public.corpus_generations WHERE id=%s", (current(conn),)
    ).fetchone()
    return row[0] if row else {}


def writable(conn) -> None:
    """Managed published schemas are immutable through application write helpers."""
    if not isinstance(conn, Connection):
        return
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    if schema == "public":
        # Adoption waits for pre-adoption application writes; adopted legacy is frozen too.
        conn.execute("SELECT pg_advisory_xact_lock_shared(%s)", (LOCK,))
        if catalog_exists(conn):
            raise ValueError("Published legacy snapshot is immutable; build another generation")
        return
    row = conn.execute(
        "SELECT state FROM public.corpus_generations WHERE schema_name=%s FOR SHARE", (schema,)
    ).fetchone()
    if row and row[0] != "building":
        raise ValueError("Published corpus is immutable; build another generation")


def begin(conn, model_identity: dict, *, source_records: list[dict] | None = None) -> str:
    from reglens.index import db

    install(conn)
    gid = uuid.uuid4().hex
    schema = "corpus_" + gid
    base = active(conn)
    if source_records is None:
        from reglens.sources import load_sources

        source_records = [asdict(s) for s in load_sources()]
    conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    conn.execute(
        "INSERT INTO public.corpus_generations(id,schema_name,state,base_id,metadata) "
        "VALUES (%s,%s,'building',%s,%s)",
        (gid, schema, base, Jsonb({"models": model_identity, "sources": source_records})),
    )
    conn.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    # Force the new schema to own both tables even though public contains the legacy ones.
    # CREATE IF NOT EXISTS resolves by search_path and would otherwise see the legacy tables.
    conn.execute(
        db.SCHEMA.replace(
            "CREATE TABLE IF NOT EXISTS chunks", f'CREATE TABLE "{schema}".chunks'
        ).replace("CREATE TABLE IF NOT EXISTS edges", f'CREATE TABLE "{schema}".edges')
    )
    conn.commit()
    return gid


def reuse_vectors(conn) -> int:
    """Reuse only vectors with matching text AND pinned model identity."""
    gid = current(conn)
    row = conn.execute(
        "SELECT base_id,metadata FROM public.corpus_generations WHERE id=%s", (gid,)
    ).fetchone()
    base = conn.execute(
        "SELECT schema_name,metadata FROM public.corpus_generations WHERE id=%s", (row[0],)
    ).fetchone()
    if not base or base[1].get("models") != row[1].get("models"):
        return 0
    writable(conn)
    result = conn.execute(
        sql.SQL(
            "UPDATE chunks c SET embedding=b.embedding FROM {}.chunks b "
            "WHERE c.id=b.id AND c.text_hash=b.text_hash AND b.embedding IS NOT NULL"
        ).format(sql.Identifier(base[0]))
    )
    conn.commit()
    return result.rowcount


def resume(conn, gid: str) -> dict:
    """Select a private build for its explicit operator; readers still cannot pin it."""
    row = conn.execute(
        "SELECT schema_name,state,metadata FROM public.corpus_generations WHERE id=%s", (gid,)
    ).fetchone()
    if not row or row[1] != "building":
        raise ValueError("Only an unfinished build can be resumed")
    conn.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(row[0])))
    return row[2]


def validate(conn, gid: str) -> dict:
    row = conn.execute(
        "SELECT schema_name FROM public.corpus_generations WHERE id=%s", (gid,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown generation: {gid}")
    schema = sql.Identifier(row[0])
    count, embedded, cited = conn.execute(
        sql.SQL(
            "SELECT count(*),count(embedding),count(*) FILTER (WHERE cite<>'') FROM {}.chunks"
        ).format(schema)
    ).fetchone()
    orphan = conn.execute(
        sql.SQL(
            "SELECT count(*) FROM {}.edges e LEFT JOIN {}.chunks c ON e.src=c.id WHERE c.id IS NULL"
        ).format(schema, schema)
    ).fetchone()[0]
    if not count or count != embedded or count != cited or orphan:
        raise ValueError(
            f"Incomplete corpus: chunks={count}, vectors={embedded}, "
            f"citations={cited}, orphan edge sources={orphan}"
        )
    return {"chunks": count, "embeddings": embedded, "orphan_edge_sources": orphan}


def publish(conn, gid: str, *, expected_head: str | None = None) -> dict:
    """Validate then atomically move head. A stale builder never overwrites a newer build."""
    if not re.fullmatch(r"[a-f0-9]{32}|legacy", gid):
        raise ValueError("Invalid generation id")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        row = conn.execute(
            "SELECT base_id,state FROM public.corpus_generations WHERE id=%s FOR UPDATE", (gid,)
        ).fetchone()
        # Wait for in-flight writers before validating; state cannot flip underneath them.
        report = validate(conn, gid)
        head = active(conn)
        expected = expected_head if expected_head is not None else row[0]
        if expected is not None and head != expected:
            raise ValueError(
                f"Head changed from {expected} to {head}; publish explicitly after review"
            )
        conn.execute(
            "UPDATE public.corpus_generations SET state='ready', "
            "metadata=metadata || %s WHERE id=%s",
            (Jsonb({"validation": report}), gid),
        )
        conn.execute("UPDATE public.corpus_head SET generation_id=%s WHERE singleton", (gid,))
    conn.commit()
    return report


def list_generations(conn) -> list[dict]:
    install(conn)
    head = active(conn)
    rows = conn.execute(
        "SELECT id,state,base_id,metadata,created_at FROM public.corpus_generations "
        "ORDER BY created_at DESC"
    ).fetchall()
    return [
        {
            "id": gid,
            "state": state,
            "active": gid == head,
            "base": base,
            "metadata": meta,
            "created": created.isoformat(),
        }
        for gid, state, base, meta, created in rows
    ]
