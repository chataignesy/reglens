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


def test_required_scope_probe_obeys_sql_constraints_and_whole_windows(database):
    from dataclasses import asdict

    from reglens.agent.tools import _rows
    from reglens.answer.context_plan import expand_context
    from reglens.answer.required_evidence import evidence_units
    from reglens.answer.research import guard
    from reglens.retrieve.search import Filters
    from reglens.sources import load_sources

    source = next(s for s in load_sources() if s.id == "eba-gl-dod")
    with db.connect(database) as conn:
        gen.begin(conn, {"embedding": "fixture"}, source_records=[asdict(source)])
        technical = replace(chunk(), id="technical", source_id=source.id, kind="paragraph",
                            article="b0", paragraph="81", ref="para. 81", title="Guidelines",
                            hierarchy=["Guidelines", "Technical"], cite="Technical")
        scope = replace(technical, id="scope-a", paragraph="11", ref="para. 11", cite="Scope",
                        hierarchy=["Guidelines", "Scope of application"],
                        text="Scope first window", body="Scope first window", applies_to="LSI",
                        effective_from="2025-01-01", application_until="2027-01-01",
                        temporal_verified=True, applicability={"approach": ["IRB"]})
        tail = replace(scope, id="scope-b", text="Scope continuation", body="Scope continuation")
        db.upsert_chunks(conn, [technical, scope, tail])
        hit = _rows(conn, "id = %s", [technical.id])[0].hit(1)
        question = "Do the EBA default guidelines apply to smaller institutions?"
        eligible = Filters(source_ids=[source.id], applies_to="LSI", as_of="2026-01-01",
                           require_known_validity=True, conditions={"approach": ["IRB"]},
                           require_known_applicability=True)
        groups = evidence_units(conn, question, [hit], eligible)
        assert [[r.id for r in g] for g in groups] == [[scope.id, tail.id]]
        assert expand_context(conn, question, [hit], eligible, max_extra=1) == [hit]
        assert len(expand_context(conn, question, [hit], eligible, max_extra=2)) == 3
        for blocked in [
            replace(eligible, source_ids=[]), replace(eligible, source_ids=["other"]),
            replace(eligible, applies_to="SI"), replace(eligible, as_of="2024-12-31"),
            replace(eligible, as_of="2027-01-01"),
            replace(eligible, conditions={"approach": ["SA"]}),
            replace(eligible, legal_levels=["L3"]),
        ]:
            assert not evidence_units(conn, question, [hit], blocked)
        # A continuation excluded by a date filter invalidates the entire logical unit.
        db.upsert_chunks(conn, [replace(tail, effective_from="2026-06-01")])
        assert not evidence_units(conn, question, [hit], eligible)
        # Missing user inputs do not become a scope lookup for an unnamed instrument.
        data = {"answer": "Need your bank's approach", "missing_info": True,
                "research_needed": False, "missing_requirements": ["User's approach"]}
        assert not guard("Does this apply to my bank?", data, [hit], conn=conn)
        assert data["research_needed"] is False


def test_time_linked_conditions_preserve_block_filters_and_split_windows(database):
    import json
    from dataclasses import asdict

    from reglens.agent.api_loop import _completeness_note
    from reglens.agent.tools import _rows
    from reglens.answer.conditions import condition_units
    from reglens.answer.context_plan import expand_context
    from reglens.answer.research import guard
    from reglens.retrieve.search import Filters
    from reglens.sources import load_sources

    source = next(s for s in load_sources() if s.id == "eba-gl-dod")
    with db.connect(database) as conn:
        gen.begin(conn, {"embedding": "fixture"}, source_records=[asdict(source)])
        anchor = replace(chunk(), id="time", source_id=source.id, kind="paragraph",
                         article="b7", paragraph="42", ref="para. 42", title="Guidelines",
                         text="For distressed restructuring, the probation period is one year.",
                         body="For distressed restructuring, the probation period is one year.")
        first = replace(anchor, id="conditions-a", paragraph="43", ref="para. 43",
                        cite="Conditions", text="After the period referred to in the previous "
                        "paragraph, all of the following conditions must be met:\n"
                        "(a) a material payment has been made;")
        second = replace(first, id="conditions-b", text="(b) no past-due amounts;\n"
                         "(c) no concerns about full repayment.")
        other = replace(first, id="other-block", article="b8", cite="Other conditions")
        db.upsert_chunks(conn, [anchor, first, second, other])
        hits = [r.hit(1) for r in _rows(conn, "id = %s", [anchor.id])]
        question = "How long is the distressed restructuring probation period?"
        groups = condition_units(conn, question, hits)
        assert [[r.id for r in g] for g in groups] == [[first.id, second.id]]
        assert expand_context(conn, question, hits, max_extra=1) == hits
        expanded = expand_context(conn, question, hits, max_extra=2)
        assert len(expanded) == 3
        draft = {"answer": "At least one year [C1].", "claims": [{"citations": ["C1"]}]}
        gaps = guard(question, draft, expanded, conn=conn)
        assert any("material payment" in g for g in gaps)
        assert any("past-due" in g for g in gaps)
        data = {"answer": f"At least one year [{anchor.cite}].", "missing_info": False,
                "research_needed": False, "missing_requirements": [],
                "claims": [{"text": "One year", "kind": "supervisory",
                            "citations": [anchor.cite]}]}
        trace = [{"keys": [anchor.cite, first.cite],
                  "chunks": {r.id: len(r.text) for r in [anchor, first, second]}}]
        note = _completeness_note(json.dumps(data), trace, conn, question)
        assert note and "material payment" in note and "past-due" in note
        partial = guard(question, {"answer": "One year [C1]."}, hits, conn=conn,
                        delivered={anchor.id: len(anchor.text), first.id: len(first.text)})
        assert any(g.startswith("Read required") for g in partial)
        assert not condition_units(conn, question, hits, Filters(source_ids=["other"]))
        assert not condition_units(conn, question, hits, Filters(legal_levels=["L3"]))


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
