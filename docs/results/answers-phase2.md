# Answer results — Phase 2 smoke runs

## Correctness (LLM judge, 2026-10-29)

Judge: `claude-haiku-5-5`, low effort, sees question + reference answer + RegLens answer (no
passages); score 2 = correct and complete, 1 = partly, 0 = wrong. Out-of-scope items and in-scope
abstentions are scored by rule (no call). Reproduce: `uv run reglens judge --set phase0 --yes`
(cached). **Cost: 39k tokens** for 25 calls (estimate 38–48k).

| | Correctness (mean score / 2) | Fully correct | Partly | Wrong |
|---|---|---|---|---|
| In-scope (25) | **0.72** | 14 | 8 | 3 |
| Single-answer (18) | **0.83** | | | |
| Multi-hop (7) | 0.43 | | | |
| Out-of-scope (5) | 5 / 5 abstained | | | |

**Spot-check of the judge (4 verdicts):**
- `lgd-001` = 2 — correct: every LGD floor matches.
- `mh-006` = 0 — fair: the answer details the Jeffreys test but misses Art. 185(b) and the annual
  reporting (multi-hop retrieval gap).
- `moc-001` = 0 — **judge wrong**: the answer (A and B are deficiency categories; C, the general
  estimation error, is a separate MoC component) is closer to EBA GL para. 36 than our reference.
- `app-001` = 1 — debatable: "the passages do not say whether it applies to LSIs" vs. the
  reference's "does not address LSIs" is arguably equivalent.

So the judge is reliable on clear facts but strict on framing; treat single-item scores as
indicative and the aggregate (0.83 single / 0.43 multi-hop) as the signal.

## Run 2 (2026-10-29): partial-answer prompt + glossary query expansion

| Metric | Run 1 (28 Oct) | Run 2 (29 Oct) |
|---|---|---|
| Out-of-scope declined | 5 / 5 | 5 / 5 |
| In-scope answered | 22 / 25 | **25 / 25** |
| Citation recall, single-answer | 0.78 | 0.75 |
| Citation recall, multi-hop | 0.18 | 0.18 |
| Claims passing the citation check | 0.98 | **0.99** |
| Avg tokens per question | 5.4k | 5.5k |
| Tokens for the run | 163k | 164k + 8k (re-ask after corpus fix) |

**What changed and why:**
- `app-001` (ECB guide and LSIs) and `mh-001` (large corporate) are now answered as **bounded
  partial answers** ("The passages only partly answer this… What they do say: …") instead of
  abstentions — the prompt change.
- `cmp-002` (June 2026 release of the ECB guide) was declined because the guide's "Document
  releases" table was **not in the index** (it precedes the Foreword and was filtered out). After
  adding it to the corpus scope, the answer is correct: release 4.1 removed all CCF-estimation content.
- Citation recall did not improve, and two items moved down:
  - `dod-003`: identical passages, the model cited ECB para. 147 instead of RTS Art. 2(2) —
    run-to-run variance.
  - `mh-005`: a **regression from query expansion** — "A-IRB" pulled retrieval towards own-LGD
    articles and dropped Art. 164(4) (retail LGD floors) from the 8 passages. Expansion helps on
    average (retrieval recall@10 0.79 → 0.81) but can displace an exact match.
- New check finding: `app-001` labels a claim "law" while citing the ECB guide restating the CRR —
  correctly flagged as `kind_mismatch`.

**Takeaway:** abstention behaviour is now right on all 30 questions; the remaining gap is
multi-hop retrieval (citation recall 0.18), which is the Phase 3 agent's job.

---

## Run 1 (2026-10-28)

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
