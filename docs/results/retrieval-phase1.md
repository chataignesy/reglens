# Retrieval results — Phase 1 (2026-10-27)

## Latest: 80 verified golden questions (69 evaluable)

| Mode | recall@10 | hit@10 | MRR@10 | Single-answer (n=57) | Multi-hop (n=12) |
|---|---|---|---|---|---|
| BM25 | 0.59 | 0.71 | 0.40 | 0.66 | 0.23 |
| Dense (BGE-M3) | 0.74 | 0.84 | 0.65 | 0.81 | 0.38 |
| Hybrid (RRF) | 0.76 | 0.88 | 0.58 | 0.84 | 0.36 |
| **Hybrid + rerank** | **0.79** | 0.87 | **0.69** | **0.89** | 0.31 |

The 50 questions added in Phase 1 cover the standardised approach, IRB scope and parameters,
rating systems, PD/LGD estimation, defaulted exposures, downturn, validation, CRM and the output
floor. Typical remaining single-answer misses are **vocabulary gaps**: practitioners say
"foundation IRB" or "LGD in-default", the CRR says "institutions that have not received permission
to use own estimates of LGD" and "exposures already in default" — a case for query rewriting.

The sections below document the first 24-question run and how each change moved the numbers.

Retrieval-only evaluation on the 24 evaluable verified golden questions (out-of-scope excluded;
`cmp-002` cites a table, not a paragraph). No LLM calls — embeddings (BGE-M3) and reranker
(bge-reranker-v2-m3) run locally on the GPU. Reproduce: `uv run reglens eval-retrieval`.

**Index:** 13 sources, 4,629 chunks (~1.69M tokens) with a deterministic hierarchy prefix,
10,265 edges (cross-references, CRR3 amendments, Art. 4 definitions, Q&A → CRR article).
**Default search scope:** operative text of CRR, RTS, EBA guidelines and the ECB guide. Excluded by
default (still searchable explicitly): EBA final-report background, the CRR3 amending act
(change tracking) and the 243 EBA Q&As (reached via their CRR article).

## Overall

| Mode | recall@5 | recall@10 | hit@10 | MRR@10 |
|---|---|---|---|---|
| BM25 (Postgres full-text, rare-term query) | 0.41 | 0.47 | 0.75 | 0.42 |
| Dense (BGE-M3) | 0.53 | 0.61 | 0.88 | 0.65 |
| Hybrid (RRF) | 0.53 | 0.61 | 0.92 | 0.50 |
| **Hybrid + rerank** | **0.58** | **0.69** | 0.88 | **0.67** |

## By question type (recall@10 / hit@10)

| Mode | Single-answer (n=17) | Multi-hop (n=7) |
|---|---|---|
| BM25 | 0.61 / 0.82 | 0.15 / 0.57 |
| Dense | 0.77 / 1.00 | 0.20 / 0.57 |
| Hybrid | 0.76 / 1.00 | 0.24 / 0.71 |
| **Hybrid + rerank** | **0.88 / 1.00** | 0.22 / 0.57 |

## What moved the numbers (hybrid + rerank, recall@10 overall / single-answer)

| Step | Overall | Single |
|---|---|---|
| First run: BM25 OR-ed every question word; all sources and kinds | 0.57 | — |
| BM25 keeps only rare terms; exclude CRR3 amending act and EBA background from default scope | 0.65 | 0.82 |
| Golden set: accept equivalent citations (ECB guide restating EBA DoD paras. 71–73; EBA DoD paras. 88/92 for facility-level default) | 0.65 | 0.85 |
| Add 243 EBA Q&As, but reach them via their CRR article instead of default search | **0.69** | **0.88** |

Tried and rejected: a larger rerank candidate pool (50, 80) — no gain, slightly lower MRR.
BM25 alone went from 0.13 to 0.47 recall@10 across these steps.

## Reading

- **Single-answer questions meet the Phase 1 target** (recall@10 ≥ 0.85): reranked hybrid puts a
  correct paragraph in the top 10 for all 17.
- **Multi-hop questions stay low (0.22)**: they need 3–5 citations across acts (CRR → RTS → EBA GL),
  which one query cannot surface. That is the case for agentic retrieval with
  `follow_reference` / `get_definition` / `get_qa` over the edge graph (Phase 3).
- **Q&As compete with the law** in a flat search: with them in default scope MRR fell from 0.67 to
  0.54. Linking them to articles keeps answers grounded in the primary text first.
