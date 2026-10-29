# Agent results — Phase 3 (2026-10-29)

The 7 multi-hop questions of the smoke set, answered by the **agent** (Claude Sonnet 5.5 with the
RegLens MCP tools `search`, `get_article`, `follow_reference`, `get_definition`, `get_qa`; at most
8 tool calls and $0.50 per question) versus the **single-pass** pipeline (one retrieval, 8 passages).
Correctness graded by the Haiku judge (0/1/2). Reproduce:
`uv run reglens eval-answers --set phase0 --agent --type multi_hop --yes` and
`uv run reglens judge --set phase0 --agent --type multi_hop --yes` (both cached).

## Headline

| Multi-hop (7 questions) | Single-pass | **Agent** |
|---|---|---|
| Correctness (mean score / 2) | 0.43 | **0.71** |
| Fully correct / partly / wrong | 1 / 4 / 2 | **3 / 4 / 0** |
| Citation recall | 0.18 | **0.72** |
| Claims passing the citation check | 0.97 | **1.00** |
| Tokens (7 questions) | 46k | 439k (**9.5×**; mostly cache reads) |

## Per question

| | Judge SP → Agent | Citation recall SP → Agent | Tokens SP → Agent |
|---|---|---|---|
| mh-001 large corporate, own LGD? | 1 → **2** | 0.33 → **1.00** | 5k → 117k |
| mh-002 materiality + probation | 1 → 1 | 0.00 → 0.67 | 6k → 43k |
| mh-003 downturn LGD chain | **2 → 1** | 0.25 → 0.25 | 6k → 11k |
| mh-004 distressed restructuring | 1 → **2** | 0.50 → **1.00** | 7k → 93k |
| mh-005 financial collateral A-IRB | 0 → **2** | 0.00 → **1.00** | 6k → 40k |
| mh-006 back-testing + ECB reporting | 0 → 1 | 0.00 → 0.50 | 8k → 38k |
| mh-007 floors on retail mortgages | 1 → 1 | 0.20 → 0.60 | 7k → 96k |

## Reading

- The agent **follows the chain the single pass cannot see**: e.g. mh-001 goes Art. 151(8)
  (large corporates use supervisory LGD) → Art. 142(1)(5a) (definition) → Art. 161(1) → Art. 162;
  mh-005 finds Art. 181(1)(c)-(d) and the Art. 164(4) floors that the expanded single-pass query lost.
- **No wrong answers** any more, and every claim passed the deterministic citation check.
- **One regression (mh-003):** the agent stopped after one search (11k tokens) and answered from the
  EBA downturn guidelines only, saying it had not read CRR Art. 181 or the RTS articles. Its
  self-assessment was right; its stopping decision was not.
- **Cost is the trade-off:** ~63k tokens per multi-hop question vs ~6.5k single-pass. Most of it is
  cache reads (≈ €0.06 per question API-equivalent).

## Follow-up: stopping rule (mh-003 re-run)

The agent prompt now asks it to check the legal basis before answering: read the CRR/RTS
provisions the passages cite, and search for the law when every passage is supervisory. Tool
calls are now logged in each answer record (`trace`), and shortened or combined keys in the
prose ("para. 26", "A; B") are matched to the passages received.

| mh-003 | Before | After |
|---|---|---|
| Tool calls | 1 (inferred) | 6 (search ×2; get_article ×4: CRR Art. 181(1), RTS Arts. 1 and 3, one failed lookup) |
| Citation recall | 0.25 | **0.50** (now cites CRR Art. 181(1)(b)) |
| Judge | 1 | 1 (still misses RTS Art. 4 / recital 14: minimum 12-month downturn) |
| Tokens | 11k | 55k |

The behaviour changed as intended: the agent now grounds the requirement in law instead of
answering from the guidelines alone. It still did not read RTS Art. 4 (duration). One key in the
prose was a range ("RTS … Art. 1(1)-(2)") and still shows as `[C?]`.

## Next

1. **Routing:** single-pass by default (single-answer correctness is already 0.92), agent for
   questions that need several provisions — e.g. when the single-pass answer reports missing
   passages, or a cheap classifier flags multi-hop.
2. **Stopping:** require at least one `follow_reference` before answering when the first passages
   cite other provisions (would have caught mh-003).
3. **Cost:** shorter tool results (passage cap 1,800 → ~1,200 chars) and 6 instead of 8 calls; re-measure.
