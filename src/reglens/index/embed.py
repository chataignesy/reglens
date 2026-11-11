"""Local embeddings (BGE-M3) and reranker (bge-reranker-v2-m3) on the GPU — no token cost."""

from __future__ import annotations

from functools import lru_cache

EMBED_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
EMBED_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
RERANK_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"


def model_identity() -> dict:
    return {
        "embedding": EMBED_MODEL,
        "embedding_revision": EMBED_REVISION,
        "reranker": RERANK_MODEL,
        "reranker_revision": RERANK_REVISION,
        "dimension": 1024,
        "normalised": True,
        "embedding_max_length": 2048,
    }


def _device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=2)
def embedder(model_name: str = EMBED_MODEL, revision: str = EMBED_REVISION, max_length: int = 2048):
    from sentence_transformers import SentenceTransformer

    device = _device()
    model = SentenceTransformer(model_name, revision=revision, device=device)
    model.max_seq_length = max_length
    if device == "cuda":
        model.half()
    return model


@lru_cache(maxsize=1)
def reranker():
    from sentence_transformers import CrossEncoder

    device = _device()
    model = CrossEncoder(RERANK_MODEL, revision=RERANK_REVISION, device=device, max_length=1024)
    if device == "cuda":
        model.model.half()
    return model


def embed(
    texts: list[str], *, batch_size: int = 8, identity: dict | None = None
) -> list[list[float]]:
    spec = identity or model_identity()
    vecs = embedder(
        spec["embedding"], spec["embedding_revision"], int(spec.get("embedding_max_length", 2048))
    ).encode(
        texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 64
    )
    return [v.tolist() for v in vecs]


def rerank(query: str, texts: list[str], *, batch_size: int = 8) -> list[float]:
    return [
        float(s) for s in reranker().predict([(query, t) for t in texts], batch_size=batch_size)
    ]
