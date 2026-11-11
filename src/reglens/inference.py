"""Optional local GPU owner: uvicorn reglens.inference:app --host 127.0.0.1 --port 8001.

One service per machine (including across worker processes), four admitted requests, one
executing on the GPU. The client never falls back to a second local model on failure.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from reglens.index import embed as models

_admission = threading.BoundedSemaphore(4)
_gpu = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    guard = socket.socket()
    # A second --workers process must fail instead of allocating another GPU model copy.
    if os.name == "nt":
        guard.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        guard.bind(("127.0.0.1", int(os.environ.get("REGLENS_INFERENCE_GUARD_PORT", "18082"))))
        guard.listen(1)
        await asyncio.to_thread(warmup)
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        guard.close()


def warmup():
    models.embedder()
    models.reranker()


app = FastAPI(title="RegLens local inference", lifespan=lifespan)


class Work(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=128)
    query: str | None = Field(default=None, max_length=20000)
    identity: dict = Field(default_factory=models.model_identity)
    batch_size: int = Field(default=8, ge=1, le=32)

    @model_validator(mode="after")
    def bounded(self):
        if sum(map(len, self.texts)) > 200000:
            raise ValueError("Input exceeds 200000 characters; split into batches")
        return self


@app.get("/ready")
def ready():
    if not getattr(app.state, "ready", False):
        raise HTTPException(503, "Models not ready")
    return {"ready": True, "identity": models.model_identity(), "concurrency": 1, "admission": 4}


def execute(work: Work, rerank: bool):
    ready()
    if work.identity != models.model_identity():
        raise HTTPException(409, "Pinned model identity differs from the inference service")
    if not _admission.acquire(blocking=False):
        raise HTTPException(429, "Inference queue full")
    try:
        if not _gpu.acquire(timeout=30):
            raise HTTPException(503, "Inference queue wait exceeded 30 seconds")
        try:
            if rerank:
                return {
                    "scores": models.local_rerank(
                        work.query or "", work.texts, batch_size=work.batch_size
                    )
                }
            return {
                "vectors": models.local_embed(
                    work.texts, batch_size=work.batch_size, identity=work.identity
                )
            }
        finally:
            _gpu.release()
    finally:
        _admission.release()


@app.post("/embed")
def embed(work: Work):
    return execute(work, False)


@app.post("/rerank")
def rerank(work: Work):
    if not work.query:
        raise HTTPException(422, "Reranking requires a query")
    return execute(work, True)
