"""Local embeddings (BGE-M3) and reranker (bge-reranker-v2-m3) on the GPU — no token cost."""

from __future__ import annotations

from functools import lru_cache

EMBED_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


def _device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def embedder():
    from sentence_transformers import SentenceTransformer

    device = _device()
    model = SentenceTransformer(EMBED_MODEL, device=device)
    model.max_seq_length = 2048
    if device == "cuda":
        model.half()
    return model


@lru_cache(maxsize=1)
def reranker():
    from sentence_transformers import CrossEncoder

    device = _device()
    model = CrossEncoder(RERANK_MODEL, device=device, max_length=1024)
    if device == "cuda":
        model.model.half()
    return model


def embed(texts: list[str], *, batch_size: int = 8) -> list[list[float]]:
    vecs = embedder().encode(
        texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 64
    )
    return [v.tolist() for v in vecs]


def rerank(query: str, texts: list[str], *, batch_size: int = 8) -> list[float]:
    return [
        float(s) for s in reranker().predict([(query, t) for t in texts], batch_size=batch_size)
    ]
