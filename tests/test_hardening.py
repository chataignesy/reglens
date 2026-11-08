"""Review step 7: applicability in every mode, HTTPS-only downloads, verified reuse."""

import json
from datetime import date

import pytest

import reglens.agent.run as agent_run
import reglens.answer.route as route
import reglens.ingest.download as dl
from reglens.answer.pipeline import Answer
from reglens.config import load_config
from reglens.retrieve.search import Filters, Hit
from reglens.sources import load_sources

HIT = Hit("c1", "crr3-consolidated", "Art. 178(1)", "", "t", "L1", None, 0.9)


def test_institution_type_reaches_every_route(monkeypatch):
    seen = []
    monkeypatch.setattr(route, "search", lambda *a, **k: seen.append(("gate", k.get("filters")))
                        or [HIT])

    def single(conn, provider, config, question, **kw):
        seen.append(("single", kw.get("filters")))
        return Answer(question, False, "", "a", [], [], "", missing_info=True)

    def agent(conn, provider, config, question, **kw):
        seen.append(("agent", kw.get("filters")))
        return Answer(question, False, "", "b", [], [], "")

    monkeypatch.setattr(route, "answer_question", single)
    monkeypatch.setattr(agent_run, "answer_agentic", agent)
    monkeypatch.setattr(route, "route_question", lambda p, q: ("single", "r", 0))
    route.answer_routed(None, None, load_config(), "q", filters=Filters(applies_to="LSI"))
    assert [(name, f.applies_to) for name, f in seen] == [
        ("gate", "LSI"), ("single", "LSI"), ("agent", "LSI")]


def test_agent_tools_and_mcp_server_get_the_institution_type(monkeypatch):
    cfg_file = agent_run._mcp_config(10, "trace.jsonl", "SI")
    env = json.loads(open(cfg_file, encoding="utf-8").read())["mcpServers"]["reglens"]["env"]
    assert env["REGLENS_APPLIES_TO"] == "SI"
    assert "REGLENS_APPLIES_TO" not in json.loads(open(agent_run._mcp_config(
        10, "t.jsonl"), encoding="utf-8").read())["mcpServers"]["reglens"]["env"]

    from reglens.agent.tools import Toolbox

    captured = {}
    monkeypatch.setattr("reglens.agent.tools.search",
                        lambda conn, q, **k: captured.setdefault("f", k["filters"]) and [])
    monkeypatch.setattr("reglens.agent.tools._rows", lambda *a, **k: [])
    Toolbox(None, applies_to="SI").search("probation")
    assert captured["f"].applies_to == "SI"


def test_downloads_refuse_plain_http():
    with pytest.raises(ValueError, match="non-HTTPS"):
        dl._get("http://example.org/x.pdf", accept="application/pdf")


def test_redirects_are_upgraded_on_eu_hosts_and_refused_elsewhere():
    import urllib.request

    h = dl._HttpsOnly()
    req = urllib.request.Request("https://publications.europa.eu/resource/celex/32013R0575")
    upgraded = h.redirect_request(req, None, 303, "See Other", {},
                                  "http://publications.europa.eu/resource/cellar/x/DOC_1")
    assert upgraded.full_url == "https://publications.europa.eu/resource/cellar/x/DOC_1"
    with pytest.raises(urllib.error.URLError):
        h.redirect_request(req, None, 302, "Found", {}, "http://evil.example/x")


def test_reused_file_must_match_its_lock_hash(monkeypatch, tmp_path):
    src = next(s for s in load_sources() if s.url and not s.celex)
    path = tmp_path / src.id / f"{src.id}.{src.format}"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF tampered")
    monkeypatch.setattr(dl, "RAW_DIR", tmp_path)
    monkeypatch.setattr(dl, "PROJECT_ROOT", tmp_path)
    lock = {src.id: {"url": src.url, "sha256": "0" * 64, "file": f"{src.id}/{path.name}"}}
    monkeypatch.setattr(dl, "load_lock", lambda: lock)
    monkeypatch.setattr(dl, "save_lock", lambda new: None)
    fetched = []
    monkeypatch.setattr(dl, "_get", lambda url, **k: fetched.append(url) or b"%PDF fresh")
    dl.download(src, as_of=date(2026, 11, 8))
    assert fetched == [src.url] and path.read_bytes() == b"%PDF fresh"  # downloaded again
