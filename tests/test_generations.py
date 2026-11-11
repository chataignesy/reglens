"""Corpus publication integration checks use a disposable database, never the user corpus."""

import os
import uuid
from dataclasses import replace

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from reglens.index import db
from reglens.index import generations as gen
from reglens.ingest.chunks import Chunk


@pytest.fixture
def database():
    admin_url = os.environ.get("REGLENS_TEST_ADMIN_URL")
    if not admin_url:
        pytest.skip("Set REGLENS_TEST_ADMIN_URL for disposable database integration checks")
    name = "reglens_test_" + uuid.uuid4().hex
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = make_conninfo(admin_url, dbname=name)
    try:
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def chunk(text="old", id="one"):
    return Chunk(
        id,
        "test",
        "v1",
        "L1",
        "all",
        "article",
        "1",
        "1",
        None,
        "Art. 1(1)",
        "Rule",
        [],
        "Test",
        text,
        text,
        cite="Test Art. 1(1)",
    )


def build(conn, text="old", *, vectors=True):
    gid = gen.begin(conn, {"embedding": "fixture", "revision": "1"}, source_records=[])
    db.upsert_chunks(conn, [chunk(text)])
    db.replace_edges(conn, [])
    if vectors:
        db.set_embeddings(conn, [("one", [1.0] * db.DIM)])
    return gid


def test_atomic_publication_reader_pinning_failure_and_rollback(database):
    with db.connect(database) as builder:
        a = build(builder)
        gen.publish(builder, a)
        with db.connect(database) as old:
            b = build(builder, "new", vectors=False)
            with pytest.raises(ValueError, match="Incomplete corpus"):
                gen.publish(builder, b)
            with db.connect(database) as reader:
                assert gen.current(reader) == a
                assert reader.execute("SELECT text FROM chunks").fetchone()[0] == "old"
            db.set_embeddings(builder, [("one", [1.0] * db.DIM)])
            gen.publish(builder, b)
            assert old.execute("SELECT text FROM chunks").fetchone()[0] == "old"
            with db.connect(database) as new:
                assert gen.current(new) == b
                assert new.execute("SELECT text FROM chunks").fetchone()[0] == "new"
                with pytest.raises(ValueError, match="immutable"):
                    db.upsert_chunks(new, [chunk("bad")])
            gen.publish(builder, a, expected_head=b)
            with db.connect(database) as rolled_back:
                assert gen.current(rolled_back) == a


def test_stale_builder_and_vector_reuse(database):
    with db.connect(database) as first:
        a = build(first)
        gen.publish(first, a)
        b = build(first, vectors=False)
        assert gen.reuse_vectors(first) == 1
        with db.connect(database) as second:
            c = build(second, "other")
            gen.publish(first, b)
            with pytest.raises(ValueError, match="Head changed"):
                gen.publish(second, c)


def test_pinned_registry_is_not_replaced_by_workspace_config(database):
    from reglens.sources import load_sources

    with db.connect(database) as conn:
        gid = build(conn)
        gen.publish(conn, gid)
    with db.connect(database) as conn:
        assert load_sources(conn=conn) == []


def test_date_boundaries_and_strict_unknown_filtering(database):
    from reglens.retrieve.search import Filters, _fetch

    with db.connect(database) as conn:
        gen.begin(conn, {"fixture": True}, source_records=[])
        db.upsert_chunks(
            conn,
            [
                replace(
                    chunk("valid", "valid"),
                    effective_from="2025-01-01",
                    application_from="2026-01-01",
                    effective_until="2027-01-01",
                    temporal_verified=True,
                    applicability={"approach": ["SA"]},
                ),
                chunk("unknown", "unknown"),
            ],
        )

        def ids(f):
            where, params = f.sql(conn)
            return {r[0] for r in conn.execute("SELECT id FROM chunks WHERE true" + where, params)}

        assert ids(Filters(as_of="2026-01-01")) == {"valid", "unknown"}
        assert ids(Filters(as_of="2027-01-01")) == {"unknown"}
        assert ids(Filters(as_of="2025-12-31", require_known_validity=True)) == set()
        assert ids(Filters(conditions={"approach": ["SA"]}, require_known_applicability=True)) == {
            "valid"
        }
        hit = _fetch(conn, [("valid", 1.0)])[0]
        assert hit.effective_from == "2025-01-01" and hit.temporal_verified


def test_publication_waits_for_writers_then_validates_current_data(database):
    import concurrent.futures
    import threading

    with db.connect(database) as builder:
        gid = build(builder)
        with db.connect(database) as writer:
            gen.resume(writer, gid)
            gen.writable(writer)
            writer.execute("UPDATE chunks SET embedding=NULL")
            started = threading.Event()

            def publish():
                with db.connect(database) as publisher:
                    started.set()
                    return gen.publish(publisher, gid)

            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                task = pool.submit(publish)
                assert started.wait(5)
                with pytest.raises(concurrent.futures.TimeoutError):
                    task.result(timeout=.15)
                writer.commit()
                with pytest.raises(ValueError, match="Incomplete corpus"):
                    task.result(timeout=5)
            assert gen.active(builder) == "legacy"
        db.set_embeddings(builder, [("one", [1.0] * db.DIM)])
        gen.publish(builder, gid)
        with pytest.raises(ValueError, match="unfinished"):
            gen.resume(builder, gid)
