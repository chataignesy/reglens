"""Regression checks for complete evidence reads, without model calls."""

from dataclasses import replace

from reglens.agent import tools
from reglens.answer import context_plan as plan
from reglens.answer.research import guard
from reglens.retrieve.intent import source_filters
from reglens.retrieve.search import Filters
from reglens.sources import load_sources


def row(cid, para="2", title="Foreword", text="purpose", point=None, article=None):
    return tools.Row(
        cid,
        "ecb-guide-internal-models",
        f"para. {para}",
        title,
        text,
        "L3",
        None,
        "paragraph",
        article,
        para,
        point,
        cite=f"Guide {title} {para}",
    )


def fixture(monkeypatch, rows):
    monkeypatch.setattr(tools, "_rows", lambda *a, **k: rows)
    monkeypatch.setattr(tools, "resolve_key", lambda c, key: [r for r in rows if r.cite == key])
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rs: rs)


def test_amendment_intent_is_narrow_and_preserves_caller_filters(monkeypatch):
    monkeypatch.setattr("reglens.sources.load_sources", lambda **kw: load_sources())
    original = Filters(applies_to="LSI", as_of="2026-01-01", require_known_validity=True)
    changed = source_filters(None, "Which CRR3 provision changed the PD floor?", original)
    assert "crr3-amending-act" in changed.source_ids
    assert changed.applies_to == "LSI" and changed.as_of == original.as_of
    assert changed.require_known_validity and original.source_ids is None
    for question in ["What is the CRR3 PD floor?", "What changed in the ECB guide?"]:
        assert source_filters(None, question, original) is original
    for restricted in [
        replace(original, source_ids=[]),
        replace(original, source_ids=["crr3-consolidated"]),
        replace(original, default_scope=False),
    ]:
        assert source_filters(None, "What changed in CRR3?", restricted) is restricted


def test_requested_range_uses_source_and_part_and_complete_windows(monkeypatch):
    rows = [row("two-a"), row("two-b", text="continued")]
    fixture(monkeypatch, rows)
    seen = []

    def query(conn, where, params, **kw):
        seen.append(params)
        return rows if params[-1] == "2" else []

    monkeypatch.setattr(tools, "_rows", query)
    hits = [row("one", "1").hit(1)]
    groups = plan.requested_units(object(), "Read paragraphs 1-3 of the foreword", hits)
    assert [[r.id for r in g] for g in groups] == [["two-a", "two-b"]]
    assert seen == [[hits[0].source_id, "Foreword", str(n)] for n in [1, 2, 3]]
    assert not plan.requested_units(object(), "Read paragraphs 1-99 of the foreword", hits)
    assert not plan.requested_units(object(), "Read paragraphs 1-3", hits)
    ambiguous = hits + [replace(hits[0], source_id="other")]
    assert not plan.requested_units(object(), "Read paragraphs 1-3 of the foreword", ambiguous)
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rs: rs[:1])
    assert not plan.requested_units(object(), "Read paragraphs 1-3 of the foreword", hits)


def test_source_bound_question_still_flags_missing_requested_read(monkeypatch):
    group = [row("two-a"), row("two-b", text="continued")]
    monkeypatch.setattr(plan, "requested_units", lambda *a: [group])
    data = {"answer": "The guide is not binding.", "research_needed": False}
    gaps = guard("Read paragraphs 1-3 of the foreword", data, [], conn=object())
    assert gaps and data["missing_info"] and data["research_needed"]
    assert not plan.requested_gaps(None, "q", [], delivered={r.id: len(r.text) for r in group})
    assert plan.requested_gaps(None, "q", [], delivered={"two-a": 6})


def test_context_budget_never_splits_requested_units(monkeypatch):
    fixture(monkeypatch, [])
    group = [row("two-a", text="x" * 40), row("two-b", text="y" * 40)]
    monkeypatch.setattr(plan, "requested_units", lambda *a: [group])
    monkeypatch.setattr("reglens.answer.research.expand_provisos", lambda c, h, f, **kw: h)
    hits = [row("one", "1").hit(1)]
    assert plan.expand_context(object(), "q", hits, max_extra=1) == hits
    assert plan.expand_context(object(), "q", hits, max_chars=79) == hits
    full = plan.expand_context(object(), "q", hits, max_extra=2, max_chars=80)
    assert [h.id for h in full] == ["one", "two-a", "two-b"]


def test_known_required_definition_overrides_model_unretrievable_guess(monkeypatch):
    target = row("def", title="Definition")
    fixture(monkeypatch, [target])
    asked = []
    monkeypatch.setattr(tools, "definition_rows", lambda c, term: asked.append(term) or [target])
    requirement = "The definition of 'large corporates' needed to classify group sales."
    data = {
        "missing_info": True,
        "research_needed": False,
        "missing_requirements": [requirement],
        "answer_requirements": [],
    }
    assert guard("Can this corporate use fixed M?", data, [], conn=object())
    assert data["research_needed"] and asked == ["large corporates"]
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rs: [])
    assert not plan.known_definition_gaps(object(), data)
    assert not plan.known_definition_gaps(object(), {"research_checks": [requirement]})


def test_definition_plural_fallback_is_exact_and_bounded(monkeypatch):
    seen = []
    target = row("def")

    def query(c, where, params, **kw):
        seen.append(params[-1])
        return [target] if params[-1] == "‘large corporate’%" else []

    monkeypatch.setattr(tools, "_rows", query)
    assert tools.definition_rows(None, "large corporates") == [target]
    assert len(seen) == 3
    assert not tools.definition_rows(None, "%large corporate%")


def test_parent_qualification_delivers_all_windows_within_shared_budget(monkeypatch):
    child = row("point", para="1", title="Rule", point="(h)", article="180")
    parent = [
        row("parent-a", para="1", title="Rule", text="introduction", article="180"),
        row("parent-b", para="1", title="Rule", text="conditional exception", article="180"),
    ]
    fixture(monkeypatch, parent)
    monkeypatch.setattr(plan, "requested_units", lambda *a: [])
    budgets = []

    def query(c, where, params, **kw):
        if where == "id = %s":
            return [child]
        assert params == [child.source_id, "180", "1", "%point (h)%"]
        return parent[1:]

    def dependencies(c, hits, filters, **kwargs):
        budgets.append(kwargs)
        return hits

    monkeypatch.setattr(tools, "_rows", query)
    monkeypatch.setattr("reglens.answer.research.expand_provisos", dependencies)
    hits = plan.expand_context(object(), "History?", [child.hit(1)])
    assert [h.id for h in hits] == ["point", "parent-a", "parent-b"]
    assert budgets == [{"max_extra": 2, "max_chars": 12000 - sum(len(r.text) for r in parent)}]


def test_broad_question_reads_relevant_sibling_and_parent_with_shared_cap(monkeypatch):
    child = row("child", "1", point="(h)", article="180")
    peer = row("retail", "2", text="retail historical observation period", article="180")
    irrelevant = row("other", "3", text="unrelated provision", article="180")
    parent = row("parent", "1", text="point (h) qualification", article="180")
    fixture(monkeypatch, [parent, peer, irrelevant])
    monkeypatch.setattr(plan, "requested_units", lambda *a: [])
    monkeypatch.setattr("reglens.answer.research.expand_provisos", lambda c, h, f, **kw: h)

    def query(c, where, params, **kw):
        if where == "id = %s":
            return [child]
        if "DISTINCT" in where:
            return [irrelevant, peer]
        return [parent]

    monkeypatch.setattr(tools, "_rows", query)
    hits = plan.expand_context(object(), "What historical observation period?", [child.hit(1)])
    assert [h.id for h in hits] == ["child", "retail", "parent"]
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rs: [])
    assert plan.expand_context(object(), "What historical observation period?", [child.hit(1)]) == [
        child.hit(1)
    ]
