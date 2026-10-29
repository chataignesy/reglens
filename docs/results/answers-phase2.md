# Answer results — Phase 2 smoke run (2026-10-28)

Smoke set: the 30 Phase 0 golden questions. Model: `claude-sonnet-5-5` (dev tier) via `claude -p`,
effort `medium`, 8 reranked passages per question. Reproduce: `uv run reglens eval-answers --set
phase0 --yes` (answers are cached per prompt version; re-runs are free).

**Cost:** 162,983 tokens for 30 questions (avg 5.4k; 2 questions needed no LLM call), about
€0.48 API-equivalent. Estimate beforehand: ~180k.

## Results

| Metric | All | Single-answer (18) | Multi-hop (7) | Out-of-scope (5) |
|---|---|---|---|---|
| Correct abstention / answer | 27 / 30 | 16 / 18 answered | 6 / 7 answered | **5 / 5 abstained** |
| Citation recall (expected citations the answer cites) | 0.64 | **0.78** | 0.18 | — |
| Claims passing the citation check | 143 / 146 (**0.98**) | | | |
| Avg tokens per question | 5.4k | 5.5k | 6.6k | 3.7k |

**Abstention gate:** 2 of 5 out-of-scope questions (AML, NSFR) were stopped before any LLM call
(best rerank score < 0.05); the model declined the other 3 itself, including FRTB, whose best
passage scored 0.78.

## What went wrong

**Three in-scope questions were declined** — all because retrieval did not bring the decisive passage:
- `mh-001` (large corporate, A-IRB): Art. 151(8) was not in the 8 passages; the model said exactly that.
- `cmp-002` (ECB guide June 2026 release): the "Document releases" table was not retrieved.
- `app-001` (ECB guide and LSIs): the passages answer it partially (the guide describes the ECB's
  own practice), but the model chose to abstain rather than give a bounded answer.

**Multi-hop citation recall is low (0.18)**, for the same reason as in retrieval: one query does not
surface CRR + RTS + EBA GL passages together. The model is honest about gaps ("the passages do not
state the threshold…") instead of filling them from memory.

**Citation check findings (3 of 146 claims):**
- `sa-001` — a real mis-citation: the 10 % transitional risk weight is attributed to Art. 465(8),
  but the number is in a different paragraph. Caught by the number check.
- `mh-007` — a "the passages do not state…" remark written as an uncited claim.
- `mh-003` — one unclear number flag ("1").

The checker itself was tuned on this run: numbers written as words count only next to a period
unit ("three months"), and numbers taken from the question are allowed. Without that it raised
false alarms (e.g. "Part Ten" read as 10).

## Next levers

1. **Retrieval for multi-hop** (Phase 3): follow cross-references and definitions from the top
   passages (e.g. Art. 160(1) → Art. 147(2) exposure classes; Art. 142(1)(5a) → Art. 151(8)).
2. **Prompt:** prefer a bounded partial answer over abstention when passages cover part of the
   question; keep "what is missing" in the answer text, not as claims.
3. **Query rewriting** for practitioner terms (F-IRB, LGD in-default).
4. **LLM judge** for answer correctness against `expected_answer` (not yet measured; Batch API).
