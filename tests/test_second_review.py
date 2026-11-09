"""Second review 2026-11-08: S1 window-level evidence, S2-S3 cancellation, S4-S6 evaluation
identity and scoring, S7 malformed gap verdicts."""

from dataclasses import replace

import pytest

import reglens.agent.run as run
import reglens.agent.tools as tools
from reglens.agent.tools import Row, Toolbox, partial_reads, trace_entry

KEY = "EBA GL downturn LGD (GL/2019/03) para. 30"
W1 = Row("p30-1", "eba-gl-downturn-lgd", "para. 30", "GL", "A" * 3699 + " 25 %", "L3", "v",
         "paragraph", "b1", "30", None, KEY)
W2 = replace(W1, id="p30-2", text="B" * 978)  # the short final window


@pytest.fixture
def unit(monkeypatch):
    monkeypatch.setattr(tools, "resolve_key", lambda conn, k: [W1, W2] if k == KEY else [])
    monkeypatch.setattr(run, "_lookup", lambda conn, k, received: [W1, W2] if k == KEY else [])


# S1


def test_one_delivered_window_does_not_authorise_the_whole_passage(unit):
    box = Toolbox(None)
    out = box._out([W2])  # only the final window, in full, no truncation marker
    trace = [trace_entry(1, "get_article", ["x"], out, box.last_chunks)]
    assert trace[0]["chunks"] == {"p30-2": 978} and "truncated" not in trace[0]
    assert partial_reads(trace, conn=object()) == {KEY}

    got = tools.delivered_chars(trace)
    partial: set[str] = set()
    context, mapping = run._resolve(None, [KEY], [KEY], delivered={KEY}, got=got, partial=partial)
    assert mapping[KEY] == ["C1"] and partial == {KEY}
    assert len(context[0].text) == 978 and "25 %" not in context[0].text  # unseen text left out


def test_every_window_delivered_whole_is_a_full_read(unit):
    box = Toolbox(None)
    trace = [trace_entry(1, "get_passage", [KEY], box._out([W1, W2]), box.last_chunks)]
    partial: set[str] = set()
    context, _ = run._resolve(None, [KEY], [KEY], got=tools.delivered_chars(trace),
                              partial=partial)
    assert partial == set() and partial_reads(trace, conn=object()) == set()
    assert "25 %" in context[0].text


def test_a_truncated_window_contributes_only_the_delivered_characters(unit):
    box = Toolbox(None, snippet_chars=2000)
    trace = [trace_entry(1, "search", ["q"], box._out([W1], snippets=True), box.last_chunks)]
    context, _ = run._resolve(None, [KEY], [KEY], got=tools.delivered_chars(trace),
                              partial=set())
    assert len(context[0].text) == 2000


def test_old_traces_without_chunk_records_keep_key_level_checks():
    assert tools.delivered_chars([{"keys": [KEY]}]) is None


# S2


def test_tools_do_not_start_after_cancel_during_an_sdk_request(monkeypatch, tmp_path):
    from test_api_loop import FakeClient, _response, _tool_use

    import reglens.agent.api_loop as loop
    from reglens.cancel import Cancelled, CancelToken
    from reglens.config import load_config
    from reglens.llm.ledger import Ledger
    from reglens.llm.provider import AnthropicAPIProvider

    cfg = replace(load_config(), billing="api", ledger_path=tmp_path / "ledger.jsonl")
    token = CancelToken()
    started = []
    monkeypatch.setattr(Toolbox, "search", lambda self, query, k=6, source=None:
                        started.append(query) or "No passages found.")
    client = FakeClient([_response("tool_use", [_tool_use(1), _tool_use(2)])])
    create = client.messages.create

    def cancel_in_flight(**kw):  # the browser disconnects while the request runs
        token.cancel()
        return create(**kw)

    client.messages.create = client.beta.messages.create = cancel_in_flight
    provider = AnthropicAPIProvider(cfg, client=client, fallback=False).with_cancel(token)
    with pytest.raises(Cancelled):
        loop.run_api_agent(None, provider, "q", system="S", tier="dev", effort=None,
                           max_calls=10, max_turns=13, max_tokens=200_000)
    assert started == [] and len(client.calls) == 1
    assert len(Ledger(cfg).entries()) == 1  # the finished request is still accounted for


# S3


def test_cancel_kills_the_whole_process_tree(tmp_path):
    import subprocess
    import sys
    import threading
    import time

    from reglens.cancel import Cancelled, CancelToken, cancellable_runner

    pid_file = tmp_path / "child.pid"
    parent = (
        "import subprocess, sys, time\n"
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(c.pid))\n"
        "time.sleep(60)\n"
    )
    token = CancelToken()

    def cancel_when_child_runs():
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text():
                break
            time.sleep(0.1)
        token.cancel()

    threading.Thread(target=cancel_when_child_runs, daemon=True).start()
    with pytest.raises(Cancelled):
        cancellable_runner(token, poll_s=0.1)([sys.executable, "-c", parent], timeout=60)
    child = int(pid_file.read_text())

    def alive(pid: int) -> bool:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True).stdout
            return str(pid) in out
        import os

        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    for _ in range(50):
        if not alive(child):
            break
        time.sleep(0.1)
    assert not alive(child)


# S4


class _Conn:
    """Answers the fingerprint query from in-memory chunk rows (applies_to, level, version)."""

    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, *a):
        import hashlib

        digest = hashlib.md5(repr(self.rows).encode()).hexdigest()
        # the real query must name the metadata columns for the digest to depend on them
        for col in ("applies_to", "legal_level", "version", "kind"):
            assert col in sql
        return type("R", (), {"fetchone": lambda s: (digest, "edges")})()


def test_corpus_fingerprint_changes_on_metadata_only_updates():
    from reglens.eval.fingerprint import corpus_fingerprint

    before = corpus_fingerprint(_Conn([("c1", "h", "SI", "L1", "v1")]))
    after = corpus_fingerprint(_Conn([("c1", "h", "all", "L3", "v2")]))
    assert before != after  # and nothing is memoised between calls


# S5


def test_retrieval_recall_needs_a_complete_alternative(monkeypatch):
    import reglens.eval.retrieval as rv
    from reglens.eval.citations import credit
    from reglens.eval.golden import Citation, GoldenItem
    from reglens.retrieve.search import Hit

    cite = Citation("eba-gl-pd-lgd", "para. 71", (Citation("eba-gl-pd-lgd", "paras. 72-73"),))
    item = GoldenItem("x-1", "q", "single", "a", [cite], "all", "t", "easy", "me", "verified")
    monkeypatch.setattr(rv, "search", lambda *a, **k: [
        Hit("c72", "eba-gl-pd-lgd", "para. 72", None, "t", "L3", None, 1.0)])
    out = rv.evaluate(None, [item], mode="rerank", k=10, indexed={"eba-gl-pd-lgd"})
    got = [("eba-gl-pd-lgd", None, "para.72")]
    assert out["recall@10"] == credit(cite, got) == 0.5  # same structure as answer-level
    assert out["hit@10"] == 1.0  # something relevant was retrieved


# S6


def test_judge_rejects_a_question_edited_under_the_same_id(monkeypatch, tmp_path):
    import json

    import reglens.eval.judge as judge
    from reglens.eval.answers import file_sha
    from reglens.eval.fingerprint import question_hash
    from reglens.eval.golden import GoldenItem

    art = tmp_path / "a.json"
    art.write_text(json.dumps({"question": "Old question?", "answer": "x", "abstained": False}))
    monkeypatch.setattr(judge, "PROJECT_ROOT", tmp_path)
    manifest = {"items": [{"id": "pd-002", "route": "single", "artifact": "a.json",
                           "artifact_sha256": file_sha(art),
                           "question_sha": question_hash("Old question?")}]}

    def item(q):
        return GoldenItem("pd-002", q, "single", "a", [], "all", "t", "easy", "me", "verified")

    edited = judge.plan(manifest, [item("Something unrelated?")], "m")
    assert edited["needs_call"] == [] and "question changed" in edited["problems"][0]
    del manifest["items"][0]["question_sha"]  # an older manifest: the answer record still tells
    edited = judge.plan(manifest, [item("Something unrelated?")], "m")
    assert "different question" in edited["problems"][0]
    assert judge.plan(manifest, [item("Old question?")], "m")["problems"] == []


# S7


@pytest.mark.parametrize("reply", [
    '{"verdicts": [null]}',
    '{"verdicts": ["covered"]}',
    '{"verdicts": [42, {"id": "O1", "status": "covered", "clauses": 7, "quote": "q"}]}',
    '{"verdicts": "none"}',
    '{"verdicts": [{"id": "O1", "status": "covered", "clauses": {"a": 1}, "quote": "q"}]}',
])
def test_malformed_gap_verdicts_become_unassessed(reply):
    from reglens.gap.match import parse_verdicts
    from reglens.gap.policy import Clause
    from reglens.gap.register import Obligation

    ob = Obligation("O1", "CRR Art. 185(b)", "crr3-consolidated", "Art. 185(b)", "c", "L1",
                    "all", "institution", "validate", "q", True, "validation", "shall")
    [v] = parse_verdicts([ob], reply, [Clause("§1", "1. Scope", "text")])
    assert v.status == "unassessed" and v.evidence == "invalid"


def test_a_clause_given_as_a_string_is_accepted():
    from reglens.gap.match import parse_verdicts
    from reglens.gap.policy import Clause
    from reglens.gap.register import Obligation

    ob = Obligation("O1", "k", "s", "r", "c", "L1", "all", "a", "o", "q", True, "t", "shall")
    reply = '{"verdicts": [{"id": "O1", "status": "covered", "clauses": "§1", "quote": "text"}]}'
    [v] = parse_verdicts([ob], reply, [Clause("§1", "1. Scope", "the text")])
    assert v.status == "covered" and v.evidence == "verified"


# Converter version on Docling cache reuse (second review, design table)


def test_docling_cache_is_reconverted_after_a_converter_upgrade(monkeypatch, tmp_path):
    import json
    import sys
    import types

    import reglens.ingest.pdf as pdf

    monkeypatch.setattr(pdf, "DOCLING_DIR", tmp_path)
    src = tmp_path / "x.pdf"
    src.write_bytes(b"%PDF same bytes")
    (tmp_path / "x.md").write_text("old text", encoding="utf-8")
    meta = tmp_path / "x.meta.json"

    def cache(converter):
        meta.write_text(json.dumps({"pdf_sha256": pdf.file_sha256(src), "converter": converter}))

    doc = types.SimpleNamespace(export_to_markdown=lambda: "new text")
    fake = types.ModuleType("docling.document_converter")
    fake.DocumentConverter = lambda: types.SimpleNamespace(
        convert=lambda p: types.SimpleNamespace(document=doc))
    monkeypatch.setitem(sys.modules, "docling.document_converter", fake)
    monkeypatch.setattr(pdf, "converter_version", lambda: "docling 2.143.0")

    cache("docling 2.143.0")
    assert pdf.pdf_to_markdown("x", src) == "old text"  # same converter: reused
    cache("unknown (adopted cache)")
    assert pdf.pdf_to_markdown("x", src) == "old text"  # unknown: reused, with a warning
    cache("docling 2.100.0")
    assert pdf.pdf_to_markdown("x", src) == "new text"  # upgraded converter: converted again
    assert json.loads(meta.read_text())["converter"] == "docling 2.143.0"
