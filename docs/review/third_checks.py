"""Third-review boundary verification. No paid calls; database writes use temp tables only."""

import concurrent.futures
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import patch

OUT = Path(__file__).with_name("third-check")
OUT.mkdir(exist_ok=True)
os.environ["REGLENS_SKIP_WARMUP"] = "1"


def boundary():
    from reglens.agent.api_loop import run_api_agent
    from reglens.agent.run import _resolve
    from reglens.agent.tools import Toolbox, partial_reads, resolve_key, trace_entry
    from reglens.cancel import Cancelled, CancelToken, cancellable_runner
    from reglens.config import load_config
    from reglens.eval import fingerprint
    from reglens.eval.citations import credit
    from reglens.eval.golden import Citation, GoldenItem
    from reglens.eval.retrieval import evaluate
    from reglens.index.db import connect
    from reglens.llm.provider import AnthropicAPIProvider
    from reglens.retrieve.search import Hit

    result = {}
    with tempfile.TemporaryDirectory(prefix="reglens-second-") as tmp:
        cfg = replace(load_config(), ledger_path=Path(tmp) / "ledger.jsonl")
        token, calls = CancelToken(), []

        def sdk_response(**kwargs):
            token.cancel()  # disconnect while the request was in flight
            return Obj(
                model="fake",
                usage=Obj(input_tokens=100, output_tokens=10),
                stop_reason="tool_use",
                content=[
                    Obj(type="tool_use", name="search", id=f"t{i}", input={"query": "q"})
                    for i in range(2)
                ],
            )

        client = Obj(messages=Obj(create=sdk_response))
        provider = AnthropicAPIProvider(cfg, client=client, fallback=False).with_cancel(token)
        with patch.object(
            Toolbox, "search", side_effect=lambda *a: calls.append("search") or "none"
        ):
            try:
                run_api_agent(
                    None,
                    provider,
                    "q",
                    system="s",
                    tier="dev",
                    effort=None,
                    max_calls=10,
                    max_turns=4,
                    max_tokens=200_000,
                )
            except Cancelled:
                pass
        result["sdk_cancel"] = {"tools_started_after_cancel": len(calls)}

        # A subprocess that itself starts a child, as the CLI starts an MCP server.
        import psutil

        pidfile = Path(tmp) / "child.pid"
        program = (
            "import subprocess,sys,time; from pathlib import Path; "
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
            f"Path({str(pidfile)!r}).write_text(str(p.pid));time.sleep(30)"
        )
        token = CancelToken()

        def cancel_when_started():
            for _ in range(100):
                if pidfile.exists():
                    token.cancel()
                    return
                time.sleep(0.03)

        monitor = threading.Thread(target=cancel_when_started, daemon=True)
        monitor.start()
        try:
            cancellable_runner(token)([sys.executable, "-c", program], input="", timeout=10)
        except Cancelled:
            pass
        child = int(pidfile.read_text())
        alive = psutil.pid_exists(child)
        result["process_tree_cancel"] = {"child_survived": alive}
        if alive:  # clean up only the child this probe created
            p = psutil.Process(child)
            p.kill()
            p.wait(timeout=5)

    conn = connect()
    try:
        # Find a real multiwindow passage with a short last window.
        key = conn.execute(
            "SELECT cite FROM chunks WHERE part > 0 AND kind!='background' "
            "AND source_id NOT IN ('crr3-amending-act','eba-qa-credit-risk') GROUP BY cite "
            "HAVING count(*)>1 AND min(length(text))<2000 ORDER BY cite LIMIT 1"
        ).fetchone()[0]
        rows = resolve_key(conn, key)
        shown = min(rows, key=lambda r: len(r.text))
        text = Toolbox(conn)._out([shown], snippets=True)
        trace = [trace_entry(1, "search", ["q"], text, chunks={shown.id: len(shown.text)})]
        ctx, mapping = _resolve(
            conn, [key], [key], delivered={key}, got={shown.id: len(shown.text)}
        )
        result["window_provenance"] = {
            "key": key,
            "available_rows": len(rows),
            "delivered_rows": 1,
            "delivered_chars": len(shown.text),
            "resolved_chars": len(ctx[0].text),
            "mapping": mapping,
            "partial_reads": sorted(partial_reads(trace, conn=conn)),
        }

        # Use temp tables shadowing public tables; no user corpus is changed.
        conn.execute("CREATE TEMP TABLE chunks AS SELECT * FROM public.chunks LIMIT 2")
        conn.execute("CREATE TEMP TABLE edges AS SELECT * FROM public.edges LIMIT 2")
        before = fingerprint.corpus_fingerprint(conn)
        conn.execute(
            "UPDATE pg_temp.chunks SET applies_to='LSI', legal_level='qa', version='2099-01-01'"
        )
        after = fingerprint.corpus_fingerprint(conn)
        result["metadata_cache_identity"] = {
            "before": before,
            "after": after,
            "same": before == after,
        }
        conn.rollback()
    finally:
        conn.close()

    # Ranges on accepted alternatives must remain an AND group in BOTH evaluators.
    c = Citation("eba-gl-dod", "para. 71", (Citation("eba-gl-dod", "paras. 72-73"),))
    item = GoldenItem("probe", "q", "factual", "a", [c], "all", "t", "easy", "r", "verified")
    h = Hit("p72", "eba-gl-dod", "para. 72", None, "text", "L3", None, 1)
    with patch("reglens.eval.retrieval.search", return_value=[h]):
        got = evaluate(None, [item], mode="bm25", indexed={"eba-gl-dod"})
    result["alternative_range"] = {
        "retrieval_credit": got["recall@10"],
        "answer_credit": credit(c, [("eba-gl-dod", None, "para.72")]),
    }
    from reglens.eval.answers import load_run
    from reglens.eval.golden import load_golden
    from reglens.eval.judge import plan
    from reglens.gap.match import parse_verdicts

    try:
        result["malformed_gap_output"] = {
            "status": parse_verdicts([Obj(id="OB-1")], '{"verdicts":[null]}', [])[0].status
        }
    except Exception as exc:
        result["malformed_gap_output"] = {"exception": type(exc).__name__, "message": str(exc)}
    manifest = load_run("20261108-151941-routed-phase0")
    item = next(i for i in load_golden() if i.id == "pd-002")
    result["changed_question_old_run"] = plan(
        manifest,
        [replace(item, question="An unrelated question replacing the original?")],
        load_config().model("bulk"),
    )
    (OUT / "boundary.json").write_text(json.dumps(result, indent=2), "utf-8")
    print(json.dumps(result, indent=2))


def http_checks():
    import httpx
    import uvicorn

    from reglens.api import app as api
    from reglens.index.db import connect
    from reglens.llm.ledger import Usage
    from reglens.llm.provider import Completion
    from reglens.retrieve.search import Hit

    with connect() as conn:
        row = conn.execute(
            "SELECT id,source_id,ref,title,text,legal_level,version FROM chunks "
            "WHERE source_id='crr3-consolidated' AND article='178' LIMIT 1"
        ).fetchone()
    hit = Hit(*row, 1)
    providers = []

    class Fake:
        def __init__(self):
            self.calls = 0
            providers.append(self)

        def with_cancel(self, token):
            self.cancel = token
            return self

        def complete(self, *args, **kwargs):
            self.cancel.check()
            self.calls += 1
            time.sleep(0.8)
            return Completion("bad JSON", "fake", Usage(0, 0))

    server = uvicorn.Server(
        uvicorn.Config(api.app, host="127.0.0.1", port=18081, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    result = {}
    try:
        with httpx.Client(base_url="http://127.0.0.1:18081", timeout=30) as client:
            for path in ("ready", "gap/runs", "gap?run=demo", "gap/export?run=demo&format=xlsx"):
                r = client.get("/api/" + path)
                result[path] = {"status": r.status_code, "bytes": len(r.content)}
            body = {
                "question": "Definition of default?",
                "mode": "single",
                "access": "subscription",
            }
            with (
                patch.object(api, "_provider", side_effect=lambda *a: Fake()),
                patch("reglens.answer.pipeline.search", return_value=[hit]),
            ):
                with client.stream("POST", "/api/ask", json=body) as stream:
                    first = next(stream.iter_lines())
                time.sleep(1.8)
                result["disconnect"] = {
                    "first": first,
                    "calls": providers[-1].calls,
                    "cancelled": providers[-1].cancel.cancelled,
                    "available_slots": api._slots._value,
                }
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    fs = [pool.submit(client.post, "/api/ask", json=body) for _ in range(2)]
                    for _ in range(100):
                        if api._slots._value == 0:
                            break
                        time.sleep(0.01)
                    third = client.post("/api/ask", json=body)
                    responses = [f.result() for f in fs]
                result["admission"] = {
                    "third_status": third.status_code,
                    "accepted_statuses": [r.status_code for r in responses],
                    "available_slots": api._slots._value,
                }
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    (OUT / "http.json").write_text(json.dumps(result, indent=2), "utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    boundary()
    http_checks()
