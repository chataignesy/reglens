"""Corpus publication integration checks use a disposable database, never the user corpus."""

import os
import uuid

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
