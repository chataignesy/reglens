"""Structural completeness regressions; no model calls or legal answer fixtures."""

from dataclasses import replace

from reglens.agent import tools
from reglens.answer import context_plan
from reglens.answer.research import guard
from reglens.retrieve.search import Filters


def row(cid, body, *, article=None, point=None, hierarchy=None, source="eba-gl-dod"):
    return tools.Row(cid, source, "para. " + cid, "Guidelines", body, "L3", None,
                     "article" if article else "paragraph", article, "3", point,
                     cite="Evidence " + cid, hierarchy=hierarchy or ["Guidelines", "Rule"])


def database(monkeypatch, records):
    from reglens.sources import load_sources

    registry = load_sources()
    monkeypatch.setattr("reglens.sources.load_sources", lambda **kwargs: registry)
    def query(conn, where, params, **kwargs):
        if where == "id = %s":
            return [r for r in records if r.id == params[0]]
        if where == "id = ANY(%s)":
            return [r for r in records if r.id in params[0]]
        if where == "cite = %s":
            return [r for r in records if r.cite == params[0]]
        if "hierarchy" in where and "unnest" in where:
            return [r for r in records if r.source_id == params[0]
                    and any(x in {"Scope of application", "Addressees"} for x in r.hierarchy)]
        return [r for r in records if r.source_id == params[0] and r.article == params[1]]
    monkeypatch.setattr(tools, "_rows", query)
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rows: rows)


def complete(answer="The general rule applies [C1]."):
    return {"answer": answer, "abstain": False,
            "claims": [{"text": answer, "citations": ["C1"], "kind": "supervisory"}],
            "missing_info": False, "research_needed": False, "missing_requirements": []}


def test_indexed_scope_gap_overrides_unavailable_guess(monkeypatch):
    technical = row("technical", "Technical default rules")
    scope = row("scope", "These guidelines are addressed to financial institutions.",
                hierarchy=["Guidelines", "Addressees"])
    database(monkeypatch, [technical, scope])
    data = complete() | {"missing_info": True,
                         "missing_requirements": ["The required scope text was not retrieved"]}
    gaps = guard("Do the EBA definition of default guidelines apply to smaller institutions?",
                 data, [technical.hit()], conn=object())
    assert any(scope.cite in g for g in gaps)
    assert data["research_needed"]
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rs: [])
    assert not guard("Do the EBA default guidelines apply?", complete(),
                     [technical.hit()], conn=object(), filters=Filters(source_ids=[]))


def test_split_list_is_expanded_and_unread_children_flagged(monkeypatch):
    intro = row("intro", "Qualifying short-term exposures shall include the following:", article="999")
    children = [row(str(n), f"qualifying short-term exposures category {n}",
                    article="999", point=f"({n})") for n in range(5)]
    database(monkeypatch, [intro, *children])
    q = "Which qualifying short-term exposures are permitted?"
    expanded = context_plan.expand_context(object(), q, [intro.hit(1)])
    assert len(expanded) == 5  # existing four-row cap
    data = complete()
    assert guard(q, data, expanded, conn=object())
    assert data["missing_info"] and data["research_needed"]
    assert not guard("What is the publication date?", complete(), [intro.hit()], conn=object())


def test_silent_enumerated_condition_omission_is_visible():
    h = row("conditions", "All of the following conditions must be met:\n"
            "(a) a material payment has been made;\n"
            "(b) there are no past-due amounts;\n"
            "(c) no concerns remain about full repayment.").hit()
    data = complete("All conditions must be met [C1].")
    assert guard("What are the conditions for reclassification?", data, [h])
    assert data["missing_info"]
    full = complete("A material payment, no past-due amounts and no repayment concerns [C1].")
    assert not guard("What are the conditions for reclassification?", full, [h])
    assert not guard("When was this published?", complete(), [h])


def test_whole_scope_windows_and_constraints(monkeypatch):
    technical = row("technical", "technical rule")
    a = row("scope-a", "scope first window", hierarchy=["Guidelines", "Scope of application"])
    b = replace(a, id="scope-b", text="scope continuation")
    database(monkeypatch, [technical, a, b])
    q = "Do the EBA definition of default guidelines apply to small institutions?"
    assert context_plan.expand_context(object(), q, [technical.hit()], max_extra=1) == [technical.hit()]
    data = complete()
    assert guard(q, data, [technical.hit()], conn=object(), delivered={a.id: len(a.text)})
    assert not guard(q, complete(), [technical.hit()], conn=object(),
                     delivered={a.id: len(a.text), b.id: len(b.text)})
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rs: rs[:1])
    assert not guard(q, complete(), [technical.hit()], conn=object())


def test_dot_lists_and_conditional_summary_are_checked_but_inline_references_are_not():
    dot = row("governance", "The management body should:\na. approve strategy;\n"
              "b. ensure staff are skilled and resourced.").hit()
    assert guard("What must the body approve?", complete("Approve strategy [C1]."), [dot])
    inline = replace(dot, text="Use point (a) of Section 2 and point (b) of Section 3.")
    assert not guard("Which validation tools are used?", complete(), [inline])
    conditions = replace(dot, text="All of the following conditions must be met:\n"
                         "(a) a material payment;\n(b) no concerns about full repayment.")
    assert guard("How long is the waiting period?",
                 complete("One year; all conditions must be met [C1]."), [conditions])


def test_paragraph_block_is_not_an_article_and_heading_terms_do_not_count(monkeypatch):
    anchor = row("anchor", "economic loss should include recoveries", article="b0",
                 hierarchy=["Guide", "LGD", "Loss calculation", "Definition"])
    target = replace(anchor, id="rate", cite="Evidence rate",
                     text="Guide › economic loss\nEconomic loss should use a discount rate.",
                     hierarchy=["Guide", "LGD", "Loss calculation", "Discounting"])
    unrelated = replace(target, id="optional", cite="Evidence optional",
                        text="Guide › economic loss\nUnrelated metadata should be stored.")
    database(monkeypatch, [anchor, target, unrelated])
    original_query = tools._rows
    def query(conn, where, params, **kwargs):
        if "hierarchy[" in where:
            return [anchor, target, unrelated]
        return original_query(conn, where, params, **kwargs)
    monkeypatch.setattr(tools, "_rows", query)
    from reglens.answer.required_evidence import evidence_units

    groups = evidence_units(object(), "Which elements enter economic loss?", [anchor.hit()])
    assert target.id in {r.id for g in groups for r in g}
    assert unrelated.id not in {r.id for g in groups for r in g}


def test_pre_final_guard_reviews_delivered_enumerations_with_corpus_keys(monkeypatch):
    import json

    from reglens.agent.api_loop import _completeness_note

    r = row("conditions", "Conditions include:\n(a) material payment;\n"
            "(b) no concerns about full repayment.")
    r.cite = tools.key_of(r.hit())
    database(monkeypatch, [r])
    data = complete(f"All conditions apply [{r.cite}].")
    data["claims"][0]["citations"] = [r.cite]
    trace = [{"keys": [r.cite], "chunks": {r.id: len(r.text)}}]
    assert _completeness_note(json.dumps(data), trace, object(),
                              "What conditions are required?")
    data["answer"] = f"A material payment and no concerns about full repayment [{r.cite}]."
    data["claims"][0]["text"] = data["answer"]
    data["answer_requirements"] = [{
        "requirement": "State the reclassification conditions", "status": "supported",
        "citations": [r.cite], "retrievable": False,
    }]
    assert _completeness_note(json.dumps(data), trace, object(),
                              "What conditions are required?") is None


def test_empty_source_restriction_stops_probe_even_if_sql_treats_it_as_default(monkeypatch):
    technical = row("technical", "Technical rule")
    scope = row("scope", "Scope evidence", hierarchy=["Guidelines", "Addressees"])
    database(monkeypatch, [technical, scope])
    from reglens.answer.required_evidence import evidence_units

    assert not evidence_units(object(), "Do the default guidelines apply?", [technical.hit()],
                              Filters(source_ids=[]))


def test_target_cap_does_not_hide_remaining_known_children(monkeypatch):
    intro = row("intro", "The following qualifying exposures are permitted:", article="999")
    children = [row(str(n), "qualifying exposures category", article="999", point=f"({n})")
                for n in range(10)]
    database(monkeypatch, [intro, *children])
    read = [intro, *children[:8]]
    got = {r.id: len(r.text) for r in read}
    gaps = guard("Which qualifying exposures are permitted?", complete(), [intro.hit()],
                 conn=object(), delivered=got)
    assert any(children[-1].cite in g for g in gaps)
    assert not guard("Which qualifying exposures are permitted?", complete(), [intro.hit()],
                     conn=object(), delivered={r.id: len(r.text) for r in [intro, *children]})


def test_scope_rejects_ambiguous_source_and_part_keys(monkeypatch):
    from reglens.answer.required_evidence import evidence_units
    from reglens.sources import load_sources

    technical = row("technical", "Technical rule")
    scope = row("scope", "Scope evidence", hierarchy=["Guidelines", "Addressees"])
    other = replace(scope, id="other-part", title="Other part")
    database(monkeypatch, [technical, scope, other])
    question = "Do the default guidelines apply?"
    assert not evidence_units(object(), question, [technical.hit()])
    # Even equally named documents must not be guessed from registry scope labels.
    source = next(s for s in load_sources() if s.id == technical.source_id)
    monkeypatch.setattr("reglens.sources.load_sources", lambda **kw: [
        source, replace(source, id="other-source"),
    ])
    assert not evidence_units(object(), question, [technical.hit(),
                              replace(technical, source_id="other-source").hit()])
