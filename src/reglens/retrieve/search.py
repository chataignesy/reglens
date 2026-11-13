"""Retrieval: BM25-style full-text, dense (BGE-M3), hybrid (RRF) and hybrid + rerank."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import psycopg

MODES = ("bm25", "dense", "hybrid", "rerank")
RRF_K = 60


@dataclass
class Hit:
    id: str
    source_id: str
    ref: str
    title: str | None
    text: str
    legal_level: str
    version: str | None
    score: float
    published_on: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    application_from: str | None = None
    application_until: str | None = None
    temporal_verified: bool = False
    applicability: dict[str, list[str]] = field(default_factory=dict)
    generation: str = "legacy"
    hierarchy: list[str] = field(default_factory=list)


@dataclass
class Filters:
    source_ids: list[str] | None = None  # explicit sources (overrides the default scope)
    legal_levels: list[str] | None = None
    applies_to: str | None = None  # "SI" / "LSI": also includes "all"
    # Default scope: operative text only (no EBA final-report background) and no
    # change-tracking sources (search_default: false in sources.yaml).
    exclude_kinds: tuple[str, ...] = ("background",)
    default_scope: bool = True
    as_of: str | None = None
    conditions: dict[str, list[str]] | None = None
    require_known_validity: bool = False
    require_known_applicability: bool = False

    def __post_init__(self):
        from datetime import date

        from reglens.context import validate_metadata

        if self.as_of:
            self.as_of = date.fromisoformat(str(self.as_of)).isoformat()
        validate_metadata({"applicability": self.conditions or {}})

    def sql(self, conn=None) -> tuple[str, list]:
        where, params = [], []
        if self.source_ids:
            where.append("source_id = ANY(%s)")
            params.append(self.source_ids)
        elif self.default_scope:
            if excluded := _off_by_default(conn):
                where.append("NOT (source_id = ANY(%s))")
                params.append(excluded)
        if self.exclude_kinds:
            where.append("NOT (kind = ANY(%s))")
            params.append(list(self.exclude_kinds))
        if self.legal_levels:
            where.append("legal_level = ANY(%s)")
            params.append(self.legal_levels)
        if self.applies_to:
            where.append("applies_to IN (%s, 'all')")
            params.append(self.applies_to)
        if self.as_of:
            for col in ("effective_from", "application_from"):
                where.append(f"({col} IS NULL OR {col} <= %s::date)")
                params.append(self.as_of)
            for col in ("effective_until", "application_until"):
                where.append(f"({col} IS NULL OR %s::date < {col})")
                params.append(self.as_of)
            if self.require_known_validity:
                where.append("temporal_verified")
        for key, values in (self.conditions or {}).items():
            where.append("((NOT (applicability ? %s)) OR (applicability -> %s) ?| %s)")
            params.extend([key, key, values])
            if self.require_known_applicability:
                where.append("applicability ? %s")
                params.append(key)
        return (" AND " + " AND ".join(where)) if where else "", params


def _off_by_default(conn=None) -> list[str]:
    from reglens.sources import load_sources

    return [s.id for s in load_sources(conn=conn) if not s.search_default]


def _doc_freqs(conn: psycopg.Connection) -> tuple[dict[str, int], int]:
    """Lexeme -> number of chunks containing it (computed once per process)."""
    return _generation_freqs(conn)


def _generation_freqs(conn) -> tuple[dict[str, int], int]:
    # The per-generation data lives on the connection: concurrent readers of old/new
    # generations never overwrite a process-global partially populated dictionary.
    cached = getattr(conn, "_reglens_freqs", None)
    if cached is None:
        cached = (
            dict(conn.execute("SELECT word, ndoc FROM ts_stat('SELECT tsv FROM chunks')")),
            conn.execute("SELECT count(*) FROM chunks").fetchone()[0],
        )
        conn._reglens_freqs = cached
    return cached


def _rare_terms_query(
    conn: psycopg.Connection, question: str, *, max_df: float = 0.1, max_terms: int = 10
) -> str:
    """OR-query of the question's informative lexemes: common ones ('exposur', 'institut') are
    dropped, since OR-ing every word lets long generic chunks win."""
    vec = conn.execute("SELECT to_tsvector('english', %s)::text", (question,)).fetchone()[0]
    lexemes = set(re.findall(r"'([^']+)'", vec))
    df, n = _doc_freqs(conn)
    ranked = sorted(lexemes, key=lambda w: df.get(w, 0))
    rare = [w for w in ranked if df.get(w, 0) and df[w] / n <= max_df][:max_terms]
    terms = rare or [w for w in ranked if df.get(w, 0)][:3]
    return " | ".join(f"'{t}'" for t in terms) or "''"


def _fetch(conn: psycopg.Connection, scored: list[tuple[str, float]]) -> list[Hit]:
    if not scored:
        return []
    from reglens.context import METADATA
    from reglens.index.generations import current

    rows = conn.execute(
        "SELECT id, source_id, ref, title, text, legal_level, version, "
        + ",".join(METADATA)
        + ", hierarchy "
        "FROM chunks WHERE id = ANY(%s)",
        ([i for i, _ in scored],),
    ).fetchall()
    by_id = {r[0]: r for r in rows}
    generation = current(conn)
    return [
        Hit(
            *by_id[i][:7],
            score=s,
            generation=generation,
            hierarchy=by_id[i][-1],
            **{
                k: str(v) if k in METADATA[:5] and v is not None else v
                for k, v in zip(METADATA, by_id[i][7:-1], strict=True)
            },
        )
        for i, s in scored
        if i in by_id
    ]


def bm25(conn, question: str, k: int, filters: Filters) -> list[tuple[str, float]]:
    where, params = filters.sql(conn)
    rows = conn.execute(
        "SELECT id, ts_rank(tsv, q, 1) AS s FROM chunks, to_tsquery('simple', %s) q "
        f"WHERE tsv @@ q{where} ORDER BY s DESC LIMIT %s",
        [_rare_terms_query(conn, question), *params, k],
    ).fetchall()
    return [(r[0], float(r[1])) for r in rows]


def dense(conn, question: str, k: int, filters: Filters) -> list[tuple[str, float]]:
    import numpy as np

    from reglens.index.embed import embed
    from reglens.index.generations import metadata

    vec = np.array(
        embed([question], identity=metadata(conn).get("models") or None)[0], dtype=np.float32
    )
    where, params = filters.sql(conn)
    rows = conn.execute(
        "SELECT id, 1 - (embedding <=> %s) AS s FROM chunks "
        f"WHERE embedding IS NOT NULL{where} ORDER BY embedding <=> %s LIMIT %s",
        [vec, *params, vec, k],
    ).fetchall()
    return [(r[0], float(r[1])) for r in rows]


def rrf(*ranked: list[tuple[str, float]]) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for lst in ranked:
        for rank, (cid, _) in enumerate(lst, 1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


def search(
    conn: psycopg.Connection,
    question: str,
    *,
    mode: str = "rerank",
    k: int = 10,
    filters: Filters | None = None,
    candidates: int = 30,
    expand: str = "both",
) -> list[Hit]:
    """`expand`: add glossary wording to the query for "none", "bm25" only, or "both"
    (BM25, dense and the reranker)."""
    from reglens.retrieve.glossary import expand_query
    from reglens.retrieve.intent import source_filters

    filters = source_filters(conn, question, filters or Filters())
    expanded = expand_query(question) if expand != "none" else question
    q_bm25 = expanded
    q_dense = expanded if expand == "both" else question
    if mode == "bm25":
        return _fetch(conn, bm25(conn, q_bm25, k, filters))
    if mode == "dense":
        return _fetch(conn, dense(conn, q_dense, k, filters))
    fused = rrf(bm25(conn, q_bm25, candidates, filters), dense(conn, q_dense, candidates, filters))
    if mode == "hybrid":
        return _fetch(conn, fused[:k])
    if mode != "rerank":
        raise ValueError(f"mode must be one of {MODES}")
    from reglens.index.embed import rerank

    pool = _fetch(conn, fused[:candidates])
    # the reranker also sees the glossary wording (recall@10 0.81 -> 0.84 on the golden set)
    from reglens.index.generations import metadata

    scores = rerank(q_dense, [h.text for h in pool], identity=metadata(conn).get("models") or None)
    for h, s in zip(pool, scores, strict=True):
        h.score = s
    return sorted(pool, key=lambda h: -h.score)[:k]
