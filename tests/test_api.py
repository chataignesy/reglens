"""HTTP API: request validation, the SSE stream, the answer payload and the gap endpoints.
The answer path is faked: no database, no models, no LLM calls."""

import json
import os

os.environ["REGLENS_SKIP_WARMUP"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import reglens.api.app as api  # noqa: E402
from reglens.answer.pipeline import Answer, Claim  # noqa: E402
from reglens.retrieve.search import Hit  # noqa: E402


@pytest.fixture
def client():
    return TestClient(api.app)


class FakeProvider:
    def with_cancel(self, token):
        self.cancel = token
        return self


def events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.mark.parametrize(
    "origin, allowed",
    [
        ("http://localhost:3000", True),
        ("http://localhost:3150", True),  # Windows can reserve port 3000 (excluded port range)
        ("http://127.0.0.1:4000", True),
        ("http://evil.example", False),
        ("http://localhost.evil.example:3000", False),
    ],
)
def test_cors_allows_local_web_ui_on_any_port(client, origin, allowed):
    r = client.options(
        "/api/meta", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )
    assert (r.headers.get("access-control-allow-origin") == origin) is allowed


def test_meta_lists_examples_and_access(client):
    m = client.get("/api/meta").json()
    assert m["examples"] and "not legal" in m["disclaimer"].lower()
    assert "api" in m["access"]


def test_ask_needs_a_key_for_api_access(client):
    r = client.post("/api/ask", json={"question": "What is the PD floor?", "access": "api"})
    assert r.status_code == 400 and "API key" in r.json()["detail"]


def test_ask_streams_progress_then_result(client, monkeypatch):
    seen_key = {}

    def fake_provider(cfg, access, key):
        seen_key["key"] = key
        return FakeProvider()

    def fake_run(req, provider, emit):
        emit({"stage": "retrieved", "passages": 8})
        emit({"stage": "tool", "tool": "search", "args": ["pd floor"], "keys": ["CRR Art. 160(1)"]})
        return {"answer": "0,05 % [C1]", "mode": req.mode}

    monkeypatch.setattr(api, "_provider", fake_provider)
    monkeypatch.setattr(api, "_run", fake_run)
    r = client.post("/api/ask", json={"question": "What is the PD floor?", "mode": "agent"},
                    headers={"X-Anthropic-Key": "sk-test-not-real"})
    assert r.headers["content-type"].startswith("text/event-stream")
    ev = events(r.text)
    assert [k for k, _ in ev] == ["progress", "progress", "result"]
    assert ev[1][1]["tool"] == "search" and ev[2][1] == {"answer": "0,05 % [C1]", "mode": "agent"}
    assert seen_key["key"] == "sk-test-not-real"
    assert "sk-test" not in r.text  # the key never comes back


def test_ask_reports_errors_without_details(client, monkeypatch):
    monkeypatch.setattr(api, "_provider", lambda *a: FakeProvider())

    def boom(req, provider, emit):
        raise RuntimeError("secret sk-test-not-real in a message")

    monkeypatch.setattr(api, "_run", boom)
    r = client.post("/api/ask", json={"question": "What is the PD floor?"},
                    headers={"X-Anthropic-Key": "sk-test-not-real"})
    [(kind, data)] = events(r.text)
    assert kind == "error" and "sk-test" not in data["message"]


def test_answer_payload_lists_only_cited_sources():
    hits = [Hit("a", "crr3-consolidated", "Art. 160(1)", "", "CRR › Art. 160(1)\nPD floor 0,05 %",
                "L1", None, 0.9),
            Hit("b", "eba-gl-dod", "para. 71", "", "EBA GL › para. 71\nprobation", "L3", None, 0.5)]
    ans = Answer("q", False, "", "The floor is 0,05 % [C2].",
                 [Claim("The floor is 0,05 %.", ["C2"], "law")], hits[::-1], "As of today",
                 model="m", usage_tokens=100,
                 trace=[{"tool": "route", "route": "single", "reason": "one lookup"},
                        {"tool": "search", "args": ["pd"], "keys": ["CRR Art. 160(1)"]}])
    ans.claims[0].check = "ok"
    p = api.answer_payload(ans, {"ok": 1, "claims": 1})
    assert [s["id"] for s in p["sources"]] == ["C1"]  # [C2] renumbered to the first source
    assert p["answer"] == "The floor is 0,05 % [C1]." and p["claims"][0]["citations"] == ["C1"]
    assert p["sources"][0] == {"id": "C1", "label": "CRR", "ref": "Art. 160(1)", "level": "law",
                               "level_key": "L1", "text": "CRR › Art. 160(1)\nPD floor 0,05 %",
                               "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/"
                                      "?uri=CELEX:32013R0575", "version": ""}
    assert p["route"] == {"route": "single", "reason": "one lookup"}
    assert p["steps"] == [{"tool": "search", "args": ["pd"], "passages": 1}]


def test_official_source_links_the_exact_consolidated_version():
    s = api.official_source("crr3-consolidated", "02013R0575-20260626")
    assert s == {"url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:"
                        "02013R0575-20260626", "version": "consolidated version of 26.06.2026"}
    g = api.official_source("eba-gl-dod", "2026-10-27")
    assert g["url"].startswith("https://www.eba.europa.eu/") and g["version"] == (
        "as downloaded 2026-10-27")


def test_gap_endpoints(client, monkeypatch, tmp_path):
    result = tmp_path / "gap.json"
    result.write_text(json.dumps({"recall": 1.0, "rows": [{
        "obligation_id": "OB-1", "status": "contradicted", "clauses": ["§15.1"], "rationale": "r",
        "source": "CRR Art. 191", "obligation": "o", "topic": "internal-audit", "quote": "q",
        "reviewer_status": "", "reviewer_comment": ""}]}), encoding="utf-8")
    run = {"id": "gap-20261101-151330", "label": "Local run", "is_demo": False, "path": result}
    demo = {"id": "demo", "label": "Committed demo run", "is_demo": True, "path": result}
    monkeypatch.setattr("reglens.gap.evaluate.list_runs", lambda: [run, demo])
    g = client.get("/api/gap").json()
    assert g["recall"] == 1.0 and g["file"] == "gap.json" and g["run_id"] == run["id"]
    assert g["is_demo"] is False  # a local run comes first; the demo is chosen explicitly
    assert client.get("/api/gap?run=demo").json()["is_demo"] is True
    assert client.get("/api/gap?run=nope").status_code == 404
    assert [r["id"] for r in client.get("/api/gap/runs").json()] == [run["id"], "demo"]
    csv = client.get("/api/gap/export?format=csv")
    assert "OB-1" in csv.content.decode("utf-8-sig") and "§15.1" in csv.text
    xlsx = client.get("/api/gap/export?format=xlsx")
    assert xlsx.content[:2] == b"PK"  # a zip container, i.e. a real .xlsx


def test_busy_server_refuses_more_questions(client, monkeypatch):
    monkeypatch.setattr(api, "_provider", lambda *a: FakeProvider())
    monkeypatch.setattr(api, "_run", lambda req, provider, emit: {"answer": "ok"})
    held = [api._slots.acquire(blocking=False) for _ in range(api.MAX_CONCURRENT)]
    try:
        r = client.post("/api/ask", json={"question": "What is the PD floor?"},
                        headers={"X-Anthropic-Key": "sk-test-not-real"})
        assert r.status_code == 429 and "Busy" in r.json()["detail"]
    finally:
        for ok in held:
            if ok:
                api._slots.release()
    r = client.post("/api/ask", json={"question": "What is the PD floor?"},
                    headers={"X-Anthropic-Key": "sk-test-not-real"})
    assert events(r.text)[-1] == ("result", {"answer": "ok"})  # the slot came back


def test_liveness_and_readiness(client, monkeypatch):
    assert client.get("/api/health").json() == {"ok": True}
    monkeypatch.setitem(api.WARMUP, "state", "failed")
    monkeypatch.setitem(api.WARMUP, "error", "OSError: no GPU")
    r = client.get("/api/ready")
    assert r.status_code == 503 and r.json()["models"] == "failed"
    assert r.json()["error"]
