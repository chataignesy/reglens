"""Evaluation integrity (review 2026-11-08: D6, D7, F4)."""

import json
from collections import defaultdict

import pytest

import reglens.eval.answers as ea
from reglens.answer.pipeline import Answer
from reglens.config import load_config
from reglens.eval.citations import part_of
from reglens.eval.golden import Citation, GoldenItem, load_golden
from reglens.retrieve.search import Hit


def item(id, cites, type="factual", question=None):
    return GoldenItem(id, question or f"{id}?", type, "a", cites, "all", "t", "easy", "me",
                      "verified")


def record(*context):
    return {"context": [dict(c) for c in context],
            "claims": [{"citations": [f"C{i}" for i in range(1, len(context) + 1)]}]}


# D6: ranges need all members, parts must match


def test_range_needs_every_member():
    it = item("r", [Citation("eba-gl-dod", "paras. 71-73")])
    assert ea.citation_recall(it, record({"source_id": "eba-gl-dod", "ref": "para. 71"})) == (
        pytest.approx(1 / 3))
    full = record(*({"source_id": "eba-gl-dod", "ref": f"para. {n}"} for n in (71, 72, 73)))
    assert ea.citation_recall(it, full) == 1.0


def test_alternative_can_satisfy_a_citation():
    it = item("a", [Citation("eba-gl-dod", "para. 71",
                             (Citation("ecb-guide-internal-models", "para. 150"),))])
    got = record({"source_id": "ecb-guide-internal-models", "ref": "para. 150",
                  "title": "Credit risk"})
    assert ea.citation_recall(it, got) == 1.0


def test_wrong_document_part_gets_no_credit():
    it = item("p", [Citation("ecb-guide-internal-models", "Foreword, para. 1")])
    wrong = record({"source_id": "ecb-guide-internal-models", "ref": "para. 1",
                    "title": "Credit risk"})
    right = record({"source_id": "ecb-guide-internal-models", "ref": "para. 1",
                    "title": "Foreword"})
    assert ea.citation_recall(it, wrong) == 0.0 and ea.citation_recall(it, right) == 1.0


def test_partless_golden_citations_are_unambiguous():
    """A citation without a part matches any part: that is only sound if its number exists
    in one part of the indexed corpus."""
    from reglens.ingest.chunks import load_chunks
    from reglens.sources import load_sources

    chunks = load_chunks()
    if not chunks:
        pytest.skip("no processed chunks")
    with_parts = {s.id for s in load_sources() if s.parts}
    parts = defaultdict(set)
    for c in chunks:
        if c.source_id in with_parts:
            parts[(c.source_id, c.ref)].add(c.title)
    bad = [
        (i.id, x.ref)
        for i in load_golden()
        for e in i.expected_citations
        for x in (e, *e.alternatives)
        if x.source in with_parts and part_of(x.ref) is None
        and len(parts.get((x.source, x.ref.split(",")[0].strip()), ())) > 1
    ]
    assert bad == []


# D7 / F4: runs use the app's dispatch, write a manifest, key answers by question text


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "ANSWER_DIR", tmp_path / "answers")
    monkeypatch.setattr(ea, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(ea, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ea, "answer_version", lambda cfg, conn, agent=False: (
        "agent-x" if agent else "single-x"))
    monkeypatch.setattr(ea, "gate_abstains", lambda conn, cfg, q: "out of scope" in q)
    hit = Hit("c1", "crr3-consolidated", "Art. 160(1)", "PD", "t", "L1", None, 0.9)
    calls = []

    def single(conn, provider, config, question, **kw):
        calls.append(("single", question))
        abstain = "out of scope" in question
        return Answer(question, abstain, "", "" if abstain else "partial [C1]", [], [hit], "",
                      usage_tokens=100, missing_info="gap" in question)

    def agent(conn, provider, config, question, **kw):
        calls.append(("agent", question))
        return Answer(question, False, "", "", [], [], "", usage_tokens=9000,
                      errors=["cost cap"])

    monkeypatch.setattr(ea, "answer_question", single)
    monkeypatch.setattr("reglens.agent.run.answer_agentic", agent)
    return tmp_path, calls


def test_routed_run_uses_dispatch_and_writes_manifest(sandbox):
    tmp, calls = sandbox
    items = [
        item("g1", [Citation("crr3-consolidated", "Art. 160(1)")], question="gap question?"),
        item("a1", [Citation("crr3-consolidated", "Art. 160(1)")], "multi_hop"),
        item("o1", [], "out_of_scope", question="out of scope?"),
    ]
    routes = {"g1": {"route": "single", "tokens": 1000}, "a1": {"route": "agent", "tokens": 1000}}
    s = ea.run(None, None, load_config(), items, routes=routes, log=lambda m: None)
    manifest = json.loads((tmp / s["file"]).read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in manifest["items"]}
    # gap -> agent fallback fails -> keep the single-pass answer; all tokens counted
    assert by_id["g1"]["route"] == "single" and by_id["g1"]["attempts"] == ["single", "agent"]
    assert by_id["g1"]["tokens"] == 1000 + 100 + 9000
    # planned agent fails -> single pass, as in the app
    assert by_id["a1"]["attempts"] == ["agent", "single"] and by_id["a1"]["route"] == "single"
    # the gate abstains: no router tokens, single pass
    assert by_id["o1"]["attempts"] == ["single"] and by_id["o1"]["router_tokens"] == 0
    assert manifest["kind"] == "routed" and len(by_id["a1"]["artifact_sha256"]) == 64
    assert by_id["g1"]["artifact"].startswith("answers/single-x/attempts/g1-")

    n = len(calls)
    ea.run(None, None, load_config(), items, routes=routes, log=lambda m: None)
    assert len(calls) == n  # cached by question text

    edited = [item("g1", items[0].expected_citations, question="gap question, reworded?")]
    ea.run(None, None, load_config(), edited, routes=routes, log=lambda m: None)
    assert ("single", "gap question, reworded?") in calls  # edited question: answered again
