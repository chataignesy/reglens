"""RegLens HTTP API for the Next.js UI. Run: uv run uvicorn reglens.api.app:app --port 8000

- `POST /api/ask` streams Server-Sent Events: `progress` events while the answer is produced
  (retrieval, routing, each agent tool call), then one `result` (or `error`) event.
- `GET /api/gap` returns the saved gap-analysis run; `GET /api/gap/export` a CSV or Excel file.

API keys: with bring-your-own-key the browser sends the key in the `X-Anthropic-Key` header for
each request. It is passed to the Anthropic SDK client and nowhere else: never logged, stored
or returned. Local runs can use the Claude subscription instead (`billing: subscription`).
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import queue
import re
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from reglens.answer.pipeline import LEVEL_LABEL, Answer
from reglens.answer.verify import check_answer
from reglens.cancel import Cancelled, CancelToken
from reglens.config import load_config
from reglens.llm.provider import AnthropicAPIProvider, ClaudeCLIProvider, LLMError
from reglens.retrieve.search import Filters
from reglens.ui.content import DISCLAIMER, EXAMPLES

WARMUP: dict = {"state": "not started", "error": None}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load the embedding and reranker models in the background, so the first question is fast
    (skipped with REGLENS_SKIP_WARMUP=1, e.g. in tests)."""
    if os.environ.get("REGLENS_SKIP_WARMUP") != "1":

        def load() -> None:
            from reglens.index.embed import embedder, reranker

            WARMUP.update(state="loading", error=None)
            try:
                from reglens.inference_client import endpoint
                from reglens.inference_client import ready as inference_ready

                if endpoint():
                    inference_ready()
                else:
                    embedder()
                    reranker()
                WARMUP["state"] = "ready"
            except Exception as e:  # reported by /api/ready, not lost in a background thread
                WARMUP.update(state="failed", error=f"{type(e).__name__}: {e}"[:300])

        threading.Thread(target=load, daemon=True).start()
    else:
        WARMUP["state"] = "skipped"
    yield


app = FastAPI(
    title="RegLens API", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan
)
app.add_middleware(  # the web UI calls the API directly from the browser (web/src/lib/api.ts)
    CORSMiddleware,
    # Local web UI on any port: Windows can reserve 3000 (excluded port range), forcing another.
    # Only pages served from this machine qualify; remote sites never match.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Anthropic-Key"],
)

Mode = Literal["auto", "single", "agent"]
Access = Literal["api", "subscription"]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    mode: Mode = "auto"
    access: Access = "api"
    applies_to: Literal["SI", "LSI"] | None = None
    as_of: date | None = None
    conditions: dict[str, list[str]] | None = None
    require_known_validity: bool = False
    require_known_applicability: bool = False

    @field_validator("conditions")
    @classmethod
    def validate_conditions(cls, value):
        from reglens.context import validate_metadata

        if value and (len(value) > 4 or any(len(v) > 20 for v in value.values())):
            raise ValueError("Too many applicability conditions")
        validate_metadata({"applicability": value or {}})
        return value


@app.get("/api/health")
def health() -> dict:
    """Liveness: the process answers HTTP."""
    return {"ok": True}


@app.get("/api/ready")
def ready() -> Response:
    """Readiness: models loaded and the database reachable (503 until then)."""
    db_ok, db_error = True, None
    try:
        from reglens.index import db

        with db.connect() as conn:
            conn.execute("SELECT 1 FROM chunks LIMIT 1")
    except Exception as e:
        db_ok, db_error = False, type(e).__name__
    models_state, model_error = WARMUP["state"], WARMUP.get("error")
    models_ok = models_state in ("ready", "skipped")
    from reglens.inference_client import endpoint
    from reglens.inference_client import ready as inference_ready

    if os.environ.get("REGLENS_INFERENCE_URL"):
        try:
            endpoint()  # reject invalid configuration as unavailable, never silently local
            models_ok = bool(inference_ready().get("ready"))
        except Exception:
            models_ok = False
        models_state = "ready" if models_ok else "unavailable"
        model_error = None if models_ok else "Shared inference unavailable"
    body = {
        "ready": db_ok and models_ok,
        "models": models_state,
        "database": db_ok,
        "error": model_error or db_error,
        "busy": MAX_CONCURRENT - _slots._value,
    }
    return Response(
        json.dumps(body), status_code=200 if body["ready"] else 503, media_type="application/json"
    )


@app.get("/api/meta")
def meta() -> dict:
    cfg = load_config()
    access = ["api"] + (["subscription"] if cfg.billing == "subscription" else [])
    return {
        "disclaimer": DISCLAIMER,
        "examples": EXAMPLES,
        "access": access,
        "model": cfg.model((cfg.answer or {}).get("tier", "dev")),
    }


def _provider(cfg, access: Access, key: str | None):
    if access == "subscription":
        if cfg.billing != "subscription":
            raise HTTPException(400, "The local Claude subscription is not available here.")
        return ClaudeCLIProvider(cfg)
    if not key:
        raise HTTPException(400, "Enter your Anthropic API key, or use the local subscription.")
    return AnthropicAPIProvider(replace(cfg, billing="api"), api_key=key)


_CONSOLIDATED = re.compile(r"0\d{4}R\d{4}-(\d{4})(\d{2})(\d{2})$")


def official_source(source_id: str, version: str | None, registry: dict | None = None) -> dict:
    """Link to the official text and the version the passage was taken from. A consolidated
    regulation links to that exact consolidated version on EUR-Lex; other sources link to the
    registered document (no guessed deep links)."""
    from types import SimpleNamespace

    from reglens.sources import load_sources

    src = (
        (SimpleNamespace(**registry[source_id]) if source_id in registry else None)
        if (registry is not None)
        else next((s for s in load_sources() if s.id == source_id), None)
    )
    url = src.url if src else None
    v = version or ""
    if m := _CONSOLIDATED.match(v):
        url = f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{v}"
        label = f"consolidated version of {m.group(3)}.{m.group(2)}.{m.group(1)}"
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        label = f"as downloaded {v}"
    else:
        label = f"CELEX {v}" if v else ""
    return {"url": url, "version": label}


def answer_payload(ans: Answer, check: dict) -> dict:
    """The answer as the UI renders it: text with [C#] markers, the cited sources, the checks.
    Cited sources are renumbered 1, 2, ... in order of first mention (the pipeline numbers them
    by retrieval rank, so an answer might otherwise cite only [C2] and [C5])."""
    order: list[str] = []
    for cid in re.findall(r"\[(C\d+)\]", ans.answer) + [
        c for cl in ans.claims for c in cl.citations
    ]:
        if cid not in order and re.fullmatch(r"C\d+", cid):
            order.append(cid)
    renumber = {old: f"C{n}" for n, old in enumerate(order, 1)}
    sources = []
    for old in order:
        i = int(old[1:])
        if not 1 <= i <= len(ans.context):
            continue
        h = ans.context[i - 1]
        sources.append(
            {
                "id": renumber[old],
                "label": h.text.split(" › ", 1)[0],
                "ref": h.ref,
                "level": LEVEL_LABEL.get(h.legal_level, h.legal_level),
                "level_key": h.legal_level,
                "text": h.text,
            }
            | official_source(h.source_id, h.version, ans.source_registry)
        )
    text = re.sub(r"\[(C\d+)\]", lambda m: f"[{renumber.get(m.group(1), m.group(1))}]", ans.answer)
    route = next((t for t in ans.trace if t.get("tool") == "route"), None)
    steps = [t for t in ans.trace if t.get("tool") not in ("route", "answer")]
    return {
        "question": ans.question,
        "abstained": ans.abstained,
        "abstain_reason": ans.abstain_reason,
        "answer": text,
        "as_of": ans.as_of,
        "claims": [
            {
                "text": c.text,
                "kind": c.kind,
                "citations": [renumber.get(x, x) for x in c.citations],
                "check": c.check,
            }
            for c in ans.claims
        ],
        "sources": sources,
        "check": {"ok": check["ok"], "claims": check["claims"]},
        "route": route and {"route": route["route"], "reason": route.get("reason", "")},
        "steps": [
            {"tool": t["tool"], "args": t.get("args", []), "passages": len(t.get("keys", []))}
            for t in steps
        ],
        "model": ans.model,
        "tokens": ans.usage_tokens,
        "usage_unknown_calls": ans.usage_unknown_calls,
        "errors": ans.errors,
        "unverified": ans.unverified,
        # R3: completeness, separate from the mechanical checks and from scope (abstained)
        "missing_info": ans.missing_info,
        "research_needed": ans.research_needed,
        "missing_requirements": ans.missing_requirements,
        "coverage": ans.coverage,
        "research": ans.research,
        "semantic_review": ans.semantic_review,
        "corpus_generation": ans.corpus_generation,
        "partial_reads": len(ans.partial_cids),
        "raw_output": ans.raw_output if ans.unverified else "",
        "unresolved": [k for t in ans.trace for k in t.get("unresolved_keys", [])],
    }


def _run(req: AskRequest, provider, emit) -> dict:
    from reglens.index import db

    cfg = load_config()
    conn = db.connect()
    filters = Filters(
        applies_to=req.applies_to,
        as_of=str(req.as_of) if req.as_of else None,
        conditions=req.conditions,
        require_known_validity=req.require_known_validity,
        require_known_applicability=req.require_known_applicability,
    )
    try:
        if req.mode == "agent":
            from reglens.agent.run import answer_agentic

            ans = answer_agentic(conn, provider, cfg, req.question, progress=emit, filters=filters)
        elif req.mode == "auto":
            from reglens.answer.route import answer_routed

            ans = answer_routed(conn, provider, cfg, req.question, progress=emit, filters=filters)
        else:
            from reglens.answer.pipeline import answer_question

            ans = answer_question(conn, provider, cfg, req.question, filters=filters, progress=emit)
    finally:
        conn.close()
    return answer_payload(ans, check_answer(ans))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


MAX_CONCURRENT = 2  # questions answered at once: they share the GPU models and provider quota
_slots = threading.BoundedSemaphore(MAX_CONCURRENT)


@app.post("/api/ask")
def ask(
    req: AskRequest, request: Request, x_anthropic_key: str | None = Header(default=None)
) -> StreamingResponse:
    """Streams progress and the answer. When the client disconnects (Stop, closed tab), the
    question is cancelled: no further model call or tool call starts and a running
    `claude -p` process is killed (see reglens/cancel.py)."""
    if not _slots.acquire(blocking=False):
        raise HTTPException(
            429, f"Busy: {MAX_CONCURRENT} questions are being answered. Try again shortly."
        )
    token = CancelToken()
    try:
        provider = _provider(load_config(), req.access, x_anthropic_key).with_cancel(token)
    except BaseException:
        _slots.release()
        raise
    events: queue.Queue = queue.Queue()

    def emit(event: dict) -> None:
        token.check()  # a progress event is a cancellation point (second review S2)
        events.put(("progress", event))

    def work() -> None:
        try:
            events.put(("result", _run(req, provider, emit)))
        except Cancelled:
            pass  # nobody is listening any more
        except LLMError as e:
            events.put(("error", {"message": str(e)}))
        except Exception as e:  # never leak the request (or its key) into the message
            events.put(("error", {"message": f"Internal error ({type(e).__name__})."}))
        finally:
            _slots.release()

    threading.Thread(target=work, daemon=True).start()

    async def stream() -> AsyncIterator[str]:
        idle = 0.0
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    kind, data = await asyncio.to_thread(events.get, timeout=1)
                except queue.Empty:
                    idle += 1
                    if idle >= 15:  # long agent runs: keep proxies from closing the stream
                        idle = 0
                        yield ": keep-alive\n\n"
                    continue
                idle = 0
                yield _sse(kind, data)
                if kind in ("result", "error"):
                    return
        finally:
            token.cancel()  # a no-op once the work is done; stops it if the client left

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)


def _gap_data(run: str | None = None) -> dict:
    from reglens.gap.evaluate import find_run

    found = find_run(run)
    if found is None:
        if run:
            raise HTTPException(404, f"No gap analysis run '{run}'.")
        raise HTTPException(404, "No gap analysis run yet. Run `reglens gap --yes` first.")
    data = json.loads(found["path"].read_text(encoding="utf-8"))
    return data | {
        "file": found["path"].name,
        "run_id": found["id"],
        "run_label": found["label"],
        "is_demo": found["is_demo"],
    }


@app.get("/api/gap/runs")
def gap_runs() -> list[dict]:
    """Saved runs, newest local run first, then the committed demo run."""
    from reglens.gap.evaluate import list_runs

    return [{k: r[k] for k in ("id", "label", "is_demo")} for r in list_runs()]


@app.get("/api/gap")
def gap(run: str | None = None) -> dict:
    """One saved run: `run` from /api/gap/runs; default the newest local run, else the demo."""
    return _gap_data(run)


@app.get("/api/gap/export")
def gap_export(format: Literal["csv", "xlsx"] = "xlsx", run: str | None = None) -> Response:
    import pandas as pd

    from reglens.gap.evaluate import EXPORT_COLUMNS

    df = pd.DataFrame(_gap_data(run)["rows"])
    df["clauses"] = df["clauses"].map(lambda c: ", ".join(c) if isinstance(c, list) else c)
    df = df[EXPORT_COLUMNS]
    if format == "csv":
        body = df.to_csv(index=False).encode("utf-8-sig")
        media = "text/csv"
    else:
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name="Coverage matrix")
        body = buf.getvalue()
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    disposition = f'attachment; filename="coverage-matrix.{format}"'
    return Response(body, media_type=media, headers={"Content-Disposition": disposition})
