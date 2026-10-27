# Retrieval results — Phase 1 (2026-10-27)

Retrieval-only evaluation on the 24 evaluable verified golden questions (out-of-scope excluded;
`cmp-002` cites a table, not a paragraph). No LLM calls — embeddings (BGE-M3) and reranker
(bge-reranker-v2-m3) run locally on the GPU. Reproduce: `uv run reglens eval-retrieval`.

**Index:** 12 sources, 4,277 chunks (~1.39M tokens), deterministic hierarchy prefix per chunk,
7,905 cross-reference / definition edges. Default search scope excludes EBA final-report
background and the CRR3 amending act (change tracking only).

## Overall

| Mode | recall@5 | recall@10 | hit@10 | MRR@10 |
|---|---|---|---|---|
| BM25 (Postgres full-text, rare-term query) | 0.31 | 0.39 | 0.67 | 0.32 |
| Dense (BGE-M3) | 0.45 | 0.57 | 0.83 | 0.54 |
| Hybrid (RRF) | 0.43 | 0.53 | 0.88 | 0.42 |
| **Hybrid + rerank** | **0.49** | **0.65** | 0.83 | **0.56** |

## By question type (recall@10 / hit@10)

| Mode | Single-answer (n=17) | Multi-hop (n=7) |
|---|---|---|
| BM25 | 0.49 / 0.71 | 0.16 / 0.57 |
| Dense | 0.72 / 0.94 | 0.20 / 0.57 |
| Hybrid | 0.63 / 0.88 | 0.28 / 0.86 |
| **Hybrid + rerank** | **0.82 / 0.94** | 0.22 / 0.57 |

## What moved the numbers

| Change | Rerank recall@10 |
|---|---|
| First run (BM25 OR-ed every question word; all sources and kinds) | 0.57 |
| + BM25 keeps only rare terms (document frequency ≤ 10%) | |
| + exclude CRR3 amending act from default scope (it duplicates CRR wording) | |
| + exclude EBA final-report background prose | **0.65** |

(BM25 alone went from 0.13 to 0.39 recall@10.)

## Reading

- Single-answer questions are close to the Phase 1 target (0.85): reranked hybrid finds the
  right paragraph in the top 10 for 16 of 17.
- Multi-hop questions need 3–5 citations across acts (CRR → RTS → EBA GL); one query cannot
  surface them all. This is the case for agentic retrieval with `follow_reference` (Phase 3).
- Some "misses" are arguably correct alternatives (e.g. ECB guide paras. 170–173 on the return to
  non-defaulted status; EBA DoD paras. 88–92 on facility-level default for retail) — candidates to
  add as accepted citations in the golden set.
