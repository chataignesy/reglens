# Full golden set — Phase 3 milestone (2026-10-31)

All 80 verified golden questions (70 in scope, 10 out of scope), answered by Claude Sonnet 5.5
with the Haiku router choosing single-pass or the agent (snippets + `get_passage`, 10 tool
calls), graded by the Haiku judge (0 / 1 / 2). For comparison, every in-scope question was also
answered single-pass. Reproduce:

```
uv run reglens eval-route --set all --yes
uv run reglens eval-answers --set all --route --yes      # routed
uv run reglens eval-answers --set all --yes              # single-pass only
uv run reglens judge --set all --yes && uv run reglens judge --set all --agent --yes
```

## Headline

| 70 in-scope questions | Single-pass only | **Routed** |
|---|---|---|
| Correctness (mean score / 2) | 0.81 | **0.88** |
| Fully correct / partly / wrong | 49 / 16 / 5 | **56 / 11 / 3** |
| — factual (55) | 0.90 | **0.93** |
| — multi-hop (12) | 0.46 | **0.67** |
| Citation recall | 0.77 | **0.85** |
| Claims passing the citation check | | **1.00** |
| Tokens | 408k | 1,259k |

- **Out of scope:** 9 / 10 declined.
- **Router:** sent 21 of 70 in-scope questions to the agent. On those 21, correctness is
  0.67 single-pass vs **0.88** with the agent: 10 improved, 1 dropped (mh-003, 2 → 1), none
  wrong.
- **Cost:** the agent questions are 30 % of the questions and 78 % of the tokens (≈ 47k each vs
  ≈ 6k single-pass).
- The 50 new questions (phase1 file) score 0.87, close to the 25 smoke questions (0.90), so the
  design was not over-fitted to the smoke set.

## By topic (routed, in-scope)

| Topic | n | Correctness | Citation recall |
|---|---|---|---|
| Definition of default | 12 | **1.00** | 0.92 |
| Rating systems | 4 | 1.00 | 1.00 |
| Margin of conservatism | 2 | 1.00 | 1.00 |
| LGD estimation | 8 | 0.94 | 0.88 |
| PD estimation | 6 | 0.92 | 0.75 |
| IRB scope | 5 | 0.90 | 0.93 |
| Output floor | 4 | 0.88 | 0.78 |
| Standardised approach | 9 | 0.83 | 0.89 |
| Defaulted exposures | 3 | 0.83 | 1.00 |
| Validation | 5 | 0.80 | 0.63 |
| Credit risk mitigation | 2 | 0.75 | 1.00 |
| IRB parameters | 3 | 0.67 | 0.56 |
| **Downturn LGD** | 4 | **0.63** | 0.63 |
| Other (applicability, CCF, governance) | 3 | 0.83 | 0.83 |

Downturn LGD is the weakest topic: the identification rules sit in the RTS on economic downturn,
which links to CRR Art. 181 and the EBA guidelines, a three-document chain.

## Failures (score 0)

| Question | Mode | Cause |
|---|---|---|
| irb-005 F-IRB maturity | single | **Retrieval miss:** CRR Art. 162 not in the top 8; the model correctly declined |
| sa-009 SA exposure value, on-balance-sheet | single | **Retrieval miss:** Art. 111(1) not retrieved; answered only the off-balance-sheet part |
| mh-011 downturn period identification | single | **Router miss:** routed single ("one guideline topic"); the answer said the details were unavailable |
| oos-007 leverage ratio | single | **Scope:** answered correctly from CRR Art. 92 (in the corpus), but leverage is outside credit risk |

All three in-scope failures are *honest* gaps (the answer says what it lacks), not
hallucinations; every claim made passed the citation check.

## What this suggests next

1. **Retrieval:** both single-pass misses are short, generic questions ("What maturity applies
   under F-IRB?") where the article is retrievable only by its exact wording; add glossary
   entries (maturity → "effective maturity", on-balance-sheet → "exposure value of an asset
   item") and check recall on these items.
2. **Fallback to the agent:** when a single-pass answer says passages are missing, re-run with
   the agent (would have caught all three in-scope failures; ~45k tokens each, only when needed).
3. **Router:** mh-011 / mh-012 type questions ("how is X identified / calculated under the
   guidelines") under-route; add examples of guideline-chain questions to the router prompt.
4. **Scope:** treat CRR provisions outside credit risk (Art. 92 leverage) as out of scope in the
   prompt, or narrow the CRR article filter to the credit-risk parts.

## After the four fixes (2026-10-31)

1. **Retrieval:** glossary entries for "maturity" and "on-balance-sheet" in the regulation's own
   wording, and the reranker now scores against the glossary-expanded query (it saw only the
   original question). Retrieval on 69 questions: recall@10 0.81 → **0.84**, hit@10 0.90 →
   **0.93**, MRR 0.70 → **0.73**; both missed articles now rank 1st.
2. **Agent fallback:** single-pass answers carry an explicit `missing_info` flag; a routed
   single-pass answer with a gap is re-run with the agent.
3. **Router prompt:** a stricter version raised agent recall 0.79 → 0.93 but sent 33 instead of
   21 questions to the agent (precision 0.39). Reverted: the fallback covers under-routing only
   when an answer actually has a gap.
4. **Scope:** Art. 92 is in scope only for the credit risk requirement and the output floor; a
   topic on the "not covered" list is out of scope even when a passage mentions it.

| 70 in-scope questions | Single-pass (before → after) | Routed (before → after) |
|---|---|---|
| Correctness | 0.81 → **0.86** | 0.88 → **0.91** |
| Fully / partly / wrong | 49/16/5 → 54/13/3 | 56/11/3 → **57/13/0** |
| — factual (55) | 0.90 → 0.95 | 0.93 → **0.98** |
| — multi-hop (12) | 0.46 → 0.50 | 0.67 → 0.63 |
| Citation recall | 0.77 → 0.80 | 0.85 → **0.90** |
| Tokens | 408k → 426k | 1,259k → 1,597k |

- **Out of scope:** 9/10 → **10/10** declined (leverage ratio now declined).
- **All four earlier failures are fixed:** irb-005 0 → 2 (retrieved, then fallback), sa-009
  0 → 2 (retrieved), mh-011 0 → 1 (fallback), oos-007 declined. **No wrong answers.**
- **Fallback** fired on 8 of 49 single-pass routes: it fixed lgd-002 (0 → 2) and val-001
  (1 → 2) and turned mh-011 from 0 to 1; on 3 questions the single-pass answer already scored 2
  (the flag is conservative). Cost: +27 % tokens for the routed run.
- **Multi-hop 0.67 → 0.63** is run-to-run variance in the agent (mh-001, mh-009: 2 → 1 in the
  same mode, mh-011: 0 → 1), the size seen in the repeat runs.
