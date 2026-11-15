"""Amendment introductions support provenance without weakening number checks."""

from dataclasses import replace

from reglens.agent import tools
from reglens.answer import context_plan
from reglens.answer.pipeline import Answer, Claim
from reglens.answer.research import guard
from reglens.answer.verify import check_answer


def records():
    child = tools.Row("child", "crr3-amending-act", "Art. 1(77)(b)", "Amendments",
                      "Paragraph 2 is replaced: the PD floor shall be 0.05%.", "L1", None,
                      "article", "1", None, "(77)(b)", cite="Child")
    parent = replace(child, id="parent", ref="Art. 1(77)", point="(77)", cite="Parent",
                     text="Article 999 is amended as follows:")
    return child, parent


def fixture(monkeypatch, child, parent):
    def rows(conn, where, params, **kwargs):
        if where == "id = %s":
            return [r for r in [child, parent] if r.id == params[0]]
        if where == "cite = %s":
            return [r for r in [child, parent] if r.cite == params[0]]
        if "point = %s" in where:
            return [parent] if params[-1] == parent.point else []
        return []
    monkeypatch.setattr(tools, "_rows", rows)
    monkeypatch.setattr(tools, "resolve_key", lambda c, k: rows(c, "cite = %s", [k]))
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rs: rs)


def test_expansion_reads_parent_and_guard_requires_citation_for_parent_fact(monkeypatch):
    child, parent = records()
    fixture(monkeypatch, child, parent)
    hits = context_plan.expand_context(object(), "Which provision changed the PD floor?",
                                       [child.hit(1)])
    assert [h.id for h in hits] == [child.id, parent.id]
    data = {"answer": "Article 999 now has a 0.05% floor [C1].",
            "claims": [{"text": "Article 999 now has a 0.05% floor", "citations": ["C1"]}]}
    gaps = guard("Which provision changed the PD floor?", data, hits, conn=object())
    assert any(g.startswith("Review required citation context") for g in gaps)
    data["claims"][0]["citations"].append("C2")
    assert not guard("Which provision changed the PD floor?", data, hits, conn=object())
    ans = Answer("q", False, "", data["answer"], [Claim(data["claims"][0]["text"],
                 ["C1", "C2"], "law")], hits, "")
    assert check_answer(ans)["supported_rate"] == 1


def test_passage_tool_delivers_parent_with_traceable_windows(monkeypatch):
    child, parent = records()
    fixture(monkeypatch, child, parent)
    box = tools.Toolbox(object())
    assert parent.text in box.get_passage("Child")
    assert set(box.last_chunks) == {child.id, parent.id}
    data = {"answer": "The floor is 0.05% [C1].",
            "claims": [{"text": "The floor is 0.05%", "citations": ["C1"]}]}
    assert not guard("What is the floor?", data, [child.hit()], conn=object())


def test_parent_scope_and_context_budget_are_preserved(monkeypatch):
    child, parent = records()
    fixture(monkeypatch, child, parent)
    assert context_plan.expand_context(object(), "q", [child.hit()], max_extra=0) == [child.hit()]
    monkeypatch.setattr(tools.Toolbox, "_eligible", lambda self, rs: [])
    assert context_plan.expand_context(object(), "q", [child.hit()]) == [child.hit()]
