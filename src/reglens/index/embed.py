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


@lru_cache(maxsize=2)
def reranker(model_name: str = RERANK_MODEL, revision: str = RERANK_REVISION):
    from sentence_transformers import CrossEncoder

    device = _device()
    model = CrossEncoder(model_name, revision=revision, device=device, max_length=1024)
    if device == "cuda":
        model.model.half()
    return model


def local_embed(
    texts: list[str], *, batch_size: int = 8, identity: dict | None = None
) -> list[list[float]]:
    spec = identity or model_identity()
    vecs = embedder(
        spec["embedding"], spec["embedding_revision"], int(spec.get("embedding_max_length", 2048))
    ).encode(
        texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 64
    )
    return [v.tolist() for v in vecs]


def local_rerank(
    query: str, texts: list[str], *, batch_size: int = 8, identity: dict | None = None
) -> list[float]:
    spec = identity or model_identity()
    model = reranker(spec["reranker"], spec["reranker_revision"])
    return [float(s) for s in model.predict([(query, t) for t in texts], batch_size=batch_size)]


def embed(
    texts: list[str], *, batch_size: int = 8, identity: dict | None = None
) -> list[list[float]]:
    from reglens.inference_client import endpoint, request

    if endpoint():
        # Bound each HTTP operation, including large indexing batches.
        vectors = []
        for start in range(0, len(texts), 8):
            vectors.extend(
                request(
                    "/embed",
                    {
                        "texts": texts[start : start + 8],
                        "identity": identity or model_identity(),
                        "batch_size": min(batch_size, 32),
                    },
                )["vectors"]
            )
        return vectors
    return local_embed(texts, batch_size=batch_size, identity=identity)


def rerank(
    query: str, texts: list[str], *, batch_size: int = 8, identity: dict | None = None
) -> list[float]:
    from reglens.inference_client import endpoint, request

    if endpoint():
        scores = []
        for start in range(0, len(texts), 8):
            scores.extend(
                request(
                    "/rerank",
                    {
                        "texts": texts[start : start + 8],
                        "query": query,
                        "identity": identity or model_identity(),
                        "batch_size": min(batch_size, 32),
                    },
                )["scores"]
            )
        return scores
    return local_rerank(query, texts, batch_size=batch_size, identity=identity)
