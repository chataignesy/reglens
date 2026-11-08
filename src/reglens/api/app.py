"""RegLens HTTP API for the Next.js UI. Run: uv run uvicorn reglens.api.app:app --port 8000

- `POST /api/ask` streams Server-Sent Events: `progress` events while the answer is produced
  (retrieval, routing, each agent tool call), then one `result` (or `error`) event.
- `GET /api/gap` returns the saved gap-analysis run; `GET /api/gap/export` a CSV or Excel file.

API keys: with bring-your-own-key the browser sends the key in the `X-Anthropic-Key` header for
each request. It is passed to the Anthropic SDK client and nowhere else: never logged, stored
or returned. Local runs can use the Claude subscription instead (`billing: subscription`).
"""

from __future__ import annotations

import io
import json
import os
import queue
import re
import threading
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from reglens.answer.pipeline import LEVEL_LABEL, Answer
from reglens.answer.verify import check_answer
from reglens.config import load_config
from reglens.llm.provider import AnthropicAPIProvider, ClaudeCLIProvider, LLMError
from reglens.retrieve.search import Filters
from reglens.ui.content import DISCLAIMER, EXAMPLES


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load the embedding and reranker models in the background, so the first question is fast
    (skipped with REGLENS_SKIP_WARMUP=1, e.g. in tests)."""
    if os.environ.get("REGLENS_SKIP_WARMUP") != "1":

        def load() -> None:
            from reglens.index.embed import embedder, reranker

            embedder()
            reranker()

        threading.Thread(target=load, daemon=True).start()
    yield


app = FastAPI(
    title="RegLens API", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan
)
app.add_middleware(  # the Next.js dev server proxies /api, so this only matters for direct calls
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


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
        "errors": ans.errors,
        "unverified": ans.unverified,
        "raw_output": ans.raw_output if ans.unverified else "",
        "unresolved": [k for t in ans.trace for k in t.get("unresolved_keys", [])],
    }


def _run(req: AskRequest, provider, emit) -> dict:
    from reglens.index import db

    cfg = load_config()
    conn = db.connect()
    try:
        if req.mode == "agent":
            from reglens.agent.run import answer_agentic

            ans = answer_agentic(conn, provider, cfg, req.question, progress=emit)
        elif req.mode == "auto":
            from reglens.answer.route import answer_routed

            ans = answer_routed(conn, provider, cfg, req.question, progress=emit)
        else:
            from reglens.answer.pipeline import answer_question

            filters = Filters(applies_to=req.applies_to)
            ans = answer_question(conn, provider, cfg, req.question, filters=filters,
                                  progress=emit)
    finally:
        conn.close()
    return answer_payload(ans, check_answer(ans))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/ask")
def ask(req: AskRequest, x_anthropic_key: str | None = Header(default=None)) -> StreamingResponse:
    provider = _provider(load_config(), req.access, x_anthropic_key)
    events: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            events.put(("result", _run(req, provider, lambda e: events.put(("progress", e)))))
        except LLMError as e:
            events.put(("error", {"message": str(e)}))
        except Exception as e:  # never leak the request (or its key) into the message
            events.put(("error", {"message": f"Internal error ({type(e).__name__})."}))

    threading.Thread(target=work, daemon=True).start()

    def stream() -> Iterator[str]:
        while True:
            try:
                kind, data = events.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"  # long agent runs: keep proxies from closing the stream
                continue
            yield _sse(kind, data)
            if kind in ("result", "error"):
                return

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)


def _gap_data() -> dict:
    from reglens.gap.evaluate import latest_result

    path = latest_result()
    if path is None:
        raise HTTPException(404, "No gap analysis run yet. Run `reglens gap --yes` first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data | {"file": path.name}


@app.get("/api/gap")
def gap() -> dict:
    return _gap_data()


@app.get("/api/gap/export")
def gap_export(format: Literal["csv", "xlsx"] = "xlsx") -> Response:
    import pandas as pd

    from reglens.gap.evaluate import EXPORT_COLUMNS

    df = pd.DataFrame(_gap_data()["rows"])
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
