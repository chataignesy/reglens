import json

import reglens.agent.run as agent_run
import reglens.answer.route as route
import reglens.eval.route as eval_route
from reglens.answer.pipeline import Answer
from reglens.config import load_config
from reglens.eval.golden import GoldenItem
from reglens.llm.ledger import Usage
from reglens.llm.provider import Completion
from reglens.retrieve.search import Hit


class FakeRouter:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete(self, prompt, **kw):
        self.calls.append(kw)
        return Completion(self.replies.pop(0), "claude-haiku-5-5", Usage(900, 20, 0, 0))


def test_route_question_parses_and_falls_back():
    fake = FakeRouter(['{"route": "agent", "reason": "chain"}', "no json", '{"route": "x"}'])
    assert route.route_question(fake, "q") == ("agent", "chain", 920)
    assert route.route_question(fake, "q")[0] == "single"
    assert route.route_question(fake, "q")[0] == "single"
    assert fake.calls[0]["tier"] == "bulk" and fake.calls[0]["purpose"] == "route"


def test_answer_routed_dispatches(monkeypatch):
    top = Hit("c1", "crr3-consolidated", "Art. 151(8)", "", "", "L1", None, 0.9)
    monkeypatch.setattr(route, "search", lambda *a, **k: [top])
    used = []

    def fake_answer(name):
        def f(conn, provider, config, question, **kw):
            used.append(name)
            return Answer(question, False, "", "ok", [], [], "", usage_tokens=100)

        return f

    monkeypatch.setattr(route, "answer_question", fake_answer("single"))
    monkeypatch.setattr(agent_run, "answer_agentic", fake_answer("agent"))
    fake = FakeRouter(['{"route": "agent", "reason": "chain"}', '{"route": "single"}'])
    a = route.answer_routed(None, fake, load_config(), "q1")
    b = route.answer_routed(None, fake, load_config(), "q2")
    assert used == ["agent", "single"]
    assert a.trace[0]["route"] == "agent" and a.usage_tokens == 100 + 920
    assert b.trace[0]["route"] == "single"


def test_router_eval_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(eval_route, "ROUTE_DIR", tmp_path / "routes")
    monkeypatch.setattr(eval_route, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data" / "evals").mkdir(parents=True)

    def item(id, type):
        return GoldenItem(id, f"{id}?", type, "a", [], "all", "t", "easy", "me", "verified")

    items = [item("f1", "factual"), item("m1", "multi_hop"), item("m2", "multi_hop"),
             item("o1", "out_of_scope")]
    fake = FakeRouter(['{"route": "single"}', '{"route": "agent"}', '{"route": "single"}'])
    s = eval_route.run(fake, items, log=lambda m: None)
    assert s["items"] == 3 and s["accuracy"] == 0.667
    assert s["agent_recall"] == 0.5 and s["agent_precision"] == 1.0
    assert [m["id"] for m in s["misrouted"]] == ["m2"]
    assert eval_route.cached_routes() == {"f1": "single", "m1": "agent", "m2": "single"}
    assert json.loads((tmp_path / "routes" / "m1.json").read_text())["route"] == "agent"
    eval_route.run(fake, items, log=lambda m: None)  # cached: no further calls
    assert len(fake.calls) == 3


def test_single_pass_gap_falls_back_to_agent(monkeypatch):
    top = Hit("c1", "crr3-consolidated", "Art. 162(1)", "", "", "L1", None, 0.9)
    monkeypatch.setattr(route, "search", lambda *a, **k: [top])

    def single(conn, provider, config, question, **kw):
        return Answer(question, False, "", "partial", [], [], "", usage_tokens=100,
                      missing_info=True)

    def agent(conn, provider, config, question, **kw):
        return Answer(question, False, "", "full", [], [], "", usage_tokens=5000)

    monkeypatch.setattr(route, "answer_question", single)
    monkeypatch.setattr(agent_run, "answer_agentic", agent)
    ans = route.answer_routed(None, FakeRouter(['{"route": "single"}']), load_config(), "q")
    assert ans.answer == "full" and ans.usage_tokens == 5000 + 100 + 920
    assert ans.trace[0]["route"] == "agent" and ans.trace[0]["reason"].startswith("fallback")


def test_agent_without_answer_falls_back_to_single_pass(monkeypatch):
    top = Hit("c1", "crr3-consolidated", "Art. 162(1)", "", "", "L1", None, 0.9)
    monkeypatch.setattr(route, "search", lambda *a, **k: [top])
    events = []

    def agent(conn, provider, config, question, **kw):
        return Answer(question, False, "", "", [], [], "", usage_tokens=9000,
                      errors=["the research agent reached its cost cap before answering"])

    def single(conn, provider, config, question, **kw):
        return Answer(question, False, "", "quick answer", [], [], "", usage_tokens=100)

    monkeypatch.setattr(agent_run, "answer_agentic", agent)
    monkeypatch.setattr(route, "answer_question", single)
    ans = route.answer_routed(None, FakeRouter(['{"route": "agent"}']), load_config(), "q",
                              progress=events.append)
    assert ans.answer == "quick answer" and ans.usage_tokens == 100 + 9000 + 920
    assert ans.trace[0]["route"] == "single" and "cost cap" in ans.trace[0]["reason"]
    assert any(e["stage"] == "agent_failed" for e in events)
