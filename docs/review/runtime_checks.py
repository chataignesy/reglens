"""Runtime review against local Postgres/models; writes only review artifacts.

Phases: retrieval (no LLM), http (controlled fake LLM), live (small subscription sample).
Run: .venv/Scripts/python.exe docs/review/runtime_checks.py retrieval
"""

# Timed callbacks execute immediately; none are retained beyond the current iteration.
# ruff: noqa: B023

import argparse
import concurrent.futures
import io
import json
import os
import platform
import statistics
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "review" / "runtime"
OUT.mkdir(exist_ok=True)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("REGLENS_SKIP_WARMUP", "1")


def save(name, data):
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2, default=str), "utf-8")


def timed(fn):
    start = time.perf_counter()
    value = fn()
    return value, round(time.perf_counter() - start, 4)


def retrieval():
    import numpy as np
    import torch

    from reglens.eval.golden import load_golden
    from reglens.eval.retrieval import evaluate
    from reglens.index import db
    from reglens.index.embed import embed, embedder, reranker
    from reglens.retrieve.search import Filters, search

    conn = db.connect()
    result = {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "gpu": torch.cuda.get_device_name(0),
        "chunks_embeddings": conn.execute(
            "select count(*), count(embedding) from chunks"
        ).fetchone(),
    }
    _, result["embedding_load_s"] = timed(embedder)
    print("Embedding loaded", result["embedding_load_s"], flush=True)
    _, result["reranker_load_s"] = timed(reranker)
    print("Reranker loaded", result["reranker_load_s"], flush=True)
    indexed = {r[0] for r in conn.execute("select distinct source_id from chunks")}
    items = load_golden()
    result["eval"] = {}
    for mode in ("bm25", "dense", "hybrid", "rerank"):
        summary, elapsed = timed(lambda: evaluate(conn, items, mode=mode, indexed=indexed))
        result["eval"][mode] = {"elapsed_s": elapsed, **summary}
        save("retrieval", result)
        print(mode, elapsed, "recall", summary["recall@10"], flush=True)
    qs = [i.question for i in items if i.id in ("dod-001", "pd-002", "mh-003")]
    result["warm_latency"] = {}
    for mode in ("bm25", "dense", "hybrid", "rerank"):
        values = []
        for _ in range(3):
            for q in qs:
                _, elapsed = timed(lambda: search(conn, q, mode=mode, k=10))
                values.append(elapsed)
        result["warm_latency"][mode] = {
            "n": len(values),
            "median_s": statistics.median(values),
            "max_s": max(values),
            "samples_s": values,
        }
    # Compare actual ANN candidate recall with exact vector search under each filter.
    result["ann"] = []
    for q in qs:
        vector = np.array(embed([q])[0], dtype=np.float32)
        for label, filt in [
            ("default", Filters()),
            ("LSI", Filters(applies_to="LSI")),
            ("ECB", Filters(source_ids=["ecb-guide-internal-models"])),
        ]:
            where, params = filt.sql()
            sql = (
                "SELECT id FROM chunks WHERE embedding IS NOT NULL"
                + where
                + " ORDER BY embedding <=> %s LIMIT 30"
            )
            conn.execute("SET LOCAL enable_indexscan = on")
            approx, ann_s = timed(lambda: conn.execute(sql, [*params, vector]).fetchall())
            plan = conn.execute("EXPLAIN (FORMAT JSON) " + sql, [*params, vector]).fetchone()[0]
            conn.execute("SET LOCAL enable_indexscan = off")
            exact, exact_s = timed(lambda: conn.execute(sql, [*params, vector]).fetchall())
            conn.execute("SET LOCAL enable_indexscan = on")
            result["ann"].append(
                {
                    "query": q,
                    "filter": label,
                    "returned": len(approx),
                    "exact_count": len(exact),
                    "overlap_at_30": len(set(approx) & set(exact)) / max(len(exact), 1),
                    "ann_s": ann_s,
                    "exact_s": exact_s,
                    "plan": plan,
                }
            )
    result["gpu_peak_allocated_mib"] = torch.cuda.max_memory_allocated() / 1024**2
    result["gpu_reserved_mib"] = torch.cuda.memory_reserved() / 1024**2

    # Concurrent real search, separate DB connection per worker; same shared GPU models.
    def run_query(q):
        with db.connect() as c:
            hits, elapsed = timed(lambda: search(c, q, k=8))
            return {"elapsed_s": elapsed, "hits": len(hits)}

    result["concurrent"] = {}
    for workers in (1, 2, 4):
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(run_query, (qs * 2)[:6]))
        result["concurrent"][workers] = {"elapsed_s": time.perf_counter() - start, "requests": rows}
        print("concurrency", workers, result["concurrent"][workers], flush=True)
    save("retrieval", result)
    conn.close()


def http_checks():
    import httpx
    import openpyxl
    import uvicorn

    from reglens.api import app as api
    from reglens.llm.ledger import Usage
    from reglens.llm.provider import Completion, LLMError

    # Real TCP HTTP server, with only LLM generation replaced. Retrieval remains real.
    server = uvicorn.Server(
        uvicorn.Config(api.app, host="127.0.0.1", port=18080, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    base = "http://127.0.0.1:18080"
    result = {}
    try:
        with httpx.Client(base_url=base, timeout=180) as client:
            for route in (
                "health",
                "meta",
                "gap",
                "gap/export?format=csv",
                "gap/export?format=xlsx",
            ):
                response, elapsed = timed(lambda: client.get("/api/" + route))
                result[route] = {
                    "status": response.status_code,
                    "elapsed_s": elapsed,
                    "bytes": len(response.content),
                }
                if route == "gap":
                    result[route]["rows"] = len(response.json().get("rows", []))
                if route.endswith("xlsx") and response.status_code == 200:
                    wb = openpyxl.load_workbook(io.BytesIO(response.content), read_only=True)
                    result[route]["worksheet_rows"] = wb.active.max_row
            for label, body, headers in [
                ("missing_key", {"question": "What is default?"}, {}),
                ("short_question", {"question": "x"}, {}),
                ("invalid_mode", {"question": "What is default?", "mode": "invalid"}, {}),
                ("oversized_question", {"question": "x" * 2001}, {}),
            ]:
                r = client.post("/api/ask", json=body, headers=headers)
                result[label] = {"status": r.status_code}

            class Fake:
                def __init__(self, text=None, delay=0, error=False):
                    self.calls, self.text, self.delay, self.error = 0, text, delay, error
                    self.call_starts = []

                def complete(self, *args, **kwargs):
                    self.calls += 1
                    self.call_starts.append(time.monotonic())
                    time.sleep(self.delay)
                    if self.error:
                        raise LLMError("Controlled provider failure")
                    reply = self.text or json.dumps(
                        {
                            "abstain": False,
                            "answer": "Consult the passage [C1].",
                            "claims": [
                                {
                                    "text": "Consult the passage.",
                                    "kind": "interpretation",
                                    "citations": ["C1"],
                                }
                            ],
                        }
                    )
                    return Completion(reply, "offline-review-fake", Usage(0, 0))

            body = {
                "question": "Under the CRR, when is an obligor considered to be in default?",
                "mode": "single",
                "access": "subscription",
            }
            for label, provider in [
                ("valid", Fake()),
                ("malformed", Fake(text="not JSON")),
                ("provider_error", Fake(error=True)),
            ]:
                with patch.object(api, "_provider", return_value=provider):
                    r, elapsed = timed(lambda: client.post("/api/ask", json=body))
                result[label] = {
                    "status": r.status_code,
                    "elapsed_s": elapsed,
                    "provider_calls": provider.calls,
                    "stream": r.text,
                }
            # Disconnect after the first progress event and observe the worker's lifetime.
            finished = threading.Event()
            real_run = api._run

            def tracked(*args, **kwargs):
                try:
                    return real_run(*args, **kwargs)
                finally:
                    finished.set()

            provider = Fake(text="not JSON", delay=1)
            with (
                patch.object(api, "_provider", return_value=provider),
                patch.object(api, "_run", tracked),
            ):
                with client.stream("POST", "/api/ask", json=body) as stream:
                    first_line = next(stream.iter_lines())
                disconnected_at = time.monotonic()
                completed_after_disconnect = finished.wait(30)
            result["disconnect"] = {
                "first_line": first_line,
                "worker_finished": completed_after_disconnect,
                "provider_calls": provider.calls,
                "calls_started_after_disconnect": sum(
                    t > disconnected_at for t in provider.call_starts
                ),
                "seconds_until_worker_finished": time.monotonic() - disconnected_at,
            }
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    save("http", result)
    print(
        json.dumps(
            {k: {a: b for a, b in v.items() if a != "stream"} for k, v in result.items()}, indent=2
        ),
        flush=True,
    )


def live():
    from reglens.answer.pipeline import answer_question
    from reglens.answer.route import answer_routed
    from reglens.answer.verify import check_answer
    from reglens.config import load_config
    from reglens.eval.golden import load_golden
    from reglens.index import db
    from reglens.llm.provider import ClaudeCLIProvider

    cfg = load_config()
    provider = ClaudeCLIProvider(cfg, timeout_s=180)
    items = {i.id: i for i in load_golden()}
    result = []
    # Three quick answers, a near-miss scope case, and one routed multi-hop question.
    for item_id, mode in [
        ("dod-001", "single"),
        ("pd-002", "single"),
        ("scope-001", "single"),
        ("oos-014", "single"),
        ("mh-003", "routed"),
    ]:
        item = items[item_id]
        print("Live start", item_id, mode, flush=True)
        conn = db.connect()
        try:
            fn = answer_routed if mode == "routed" else answer_question
            ans, elapsed = timed(lambda: fn(conn, provider, cfg, item.question))
            check = check_answer(ans)
            row = {
                "id": item_id,
                "mode": mode,
                "elapsed_s": elapsed,
                "check": check,
                "expected_answer": item.expected_answer,
                "expected_citations": [as_citation(c) for c in item.expected_citations],
                "result": ans.to_dict(),
            }
        except Exception as exc:
            row = {"id": item_id, "mode": mode, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            conn.close()
        result.append(row)
        save("live", result)
        print(
            "Live done",
            item_id,
            {
                k: v
                for k, v in row.items()
                if k not in ("result", "expected_answer", "expected_citations")
            },
            flush=True,
        )
        if "error" in row:
            break  # establish provider compatibility before spending on further calls


def as_citation(c):
    return {"source": c.source, "ref": c.ref}


def judge_live():
    from reglens.config import load_config
    from reglens.eval.golden import load_golden
    from reglens.eval.judge import JUDGE_SYSTEM, _parse, judge_prompt
    from reglens.llm.provider import ClaudeCLIProvider

    items = {i.id: i for i in load_golden()}
    provider = ClaudeCLIProvider(load_config(), timeout_s=120)
    answers = json.loads((OUT / "live.json").read_text(encoding="utf-8"))
    rows = []
    for record in answers:
        item = items[record["id"]]
        answer = record["result"]
        if item.type == "out_of_scope":
            row = {
                "id": item.id,
                "score": 2 if answer["abstained"] else 0,
                "method": "deterministic scope check",
                "tokens": 0,
            }
        else:
            completion, elapsed = timed(
                lambda: provider.complete(
                    judge_prompt(item, answer["answer"]),
                    purpose="review_judge",
                    system=JUDGE_SYSTEM,
                    tier="bulk",
                    effort="low",
                )
            )
            row = {
                "id": item.id,
                **_parse(completion.text),
                "method": "fresh reference-only LLM judge",
                "tokens": completion.usage.total_tokens,
                "elapsed_s": elapsed,
            }
        rows.append(row)
        save("judge", rows)
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["retrieval", "http", "live", "judge"])
    phase = parser.parse_args().phase
    {"retrieval": retrieval, "http": http_checks, "live": live, "judge": judge_live}[phase]()
