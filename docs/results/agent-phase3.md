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

## Routing (2026-10-29)

A Haiku router (`reglens ask --route`) sends each question to single-pass or to the agent;
the retrieval gate runs first, so out-of-scope questions never reach it. Agent limits were
raised for quality: 10 tool calls, 2,000 chars per passage, 10,000 per result, $0.75 cap.
Independent tool calls are batched in one turn. A run with no tool call at all (tools not
available) is retried once.

**Router** (`reglens eval-route --set all`, 70 in-scope questions, ~1k tokens each): accuracy
0.81; it routes 11 of 14 multi-hop/comparison questions to the agent (recall 0.79), but also
10 of 56 single-answer questions (precision 0.52). Over-routing costs tokens, not quality.
Under-routed: mh-011, mh-012 ("one guideline topic"), cmp-001.

**Smoke set, 25 in-scope questions** (12 routed to the agent):

| | Single-pass | **Routed** |
|---|---|---|
| Correctness (mean score / 2) | 0.78 | **0.86** |
| — factual (15) | 0.97 | 0.97 |
| — multi-hop (7) | 0.43 | **0.86** (5 fully, 2 partly) |
| Fully correct / wrong | 16 / 2 | **19 / 1** |
| Citation recall | 0.62 | **0.82** |
| Tokens (25 questions) | 147k | 685k (+ ~25k router) |

- mh-003 now scores 2 (reads CRR Art. 181 and the RTS before answering).
- **Two losses:** cmp-002 (1 → 0): the ECB guide release table is cut by the 2,000-char
  passage cap before the 2026 rows (they start at char 2,373 of a 3,674-char chunk), so the
  agent abstained. app-001 (2 → 1): hedged on LSI scope.
- Routed factual questions (dod-002, dod-007, moc-001) kept their scores at 2-8× the tokens.

## Full-chunk passages (2026-10-30)

Passage cap 2,000 → 4,000 chars (longest chunk: 3,940, so nothing is truncated any more),
result cap 10,000 → 14,000. The 12 routed agent questions re-run and re-judged. The JSON
parser now also repairs unescaped quotes inside strings (mh-002 failed on `your "past due"`).

| Routed agent questions | Judge 2k cap → 4k cap | Tool calls | Tokens |
|---|---|---|---|
| cmp-002 ECB guide 2026 release | **0 → 2** | 2 → 11 | 20k → 151k |
| app-001 guide and LSIs | **1 → 2** | 7 → 5 | 64k → 52k |
| dod-007 materiality | **1 → 2** | 4 → 4 | 30k → 30k |
| dod-002, moc-001, mh-001, mh-002 | 2 → 2 | | |
| mh-006, mh-007 | 1 → 1 | | |
| mh-003 downturn LGD | **2 → 1** | 8 → 9 | 80k → 109k |
| mh-004 distressed restructuring | **2 → 1** | 7 → 5 | 72k → 50k |
| mh-005 financial collateral | **2 → 1** | 5 → 2 | 50k → 14k |

- Smoke set routed correctness **0.86 → 0.88** (multi-hop 0.86 → 0.64; others up); agent tokens
  609k → 588k.
- With larger results the agent often stops sooner (mh-005: 2 calls, misses the Art. 181(1)
  conditions; mh-001: 12 → 3 calls, still correct). cmp-002 shows the opposite failure: 11
  near-identical searches once the release table was found.
- **Caveat:** one sample per question and n = 7 multi-hop; a 3-point swing is within run-to-run
  and judge variance. A repeat run is needed before attributing the multi-hop drop to the cap.

**Repeat run** (`--repeat 2`, same 4k settings, 255k tokens): multi-hop again **0.64**.

| | Judge 2k \| 4k run 1, run 2 | Tool calls | Tokens |
|---|---|---|---|
| mh-001 | 2 \| 2, 2 | 12 \| 3, 5 | 118k \| 19k, 38k |
| mh-002 | 2 \| 2, 1 | 8 \| 8, 7 | 72k \| 88k, 83k |
| mh-003 | 2 \| 1, 1 | 8 \| 9, 3 | 80k \| 109k, 27k |
| mh-004 | 2 \| 1, 2 | 7 \| 5, 4 | 71k \| 50k, 33k |
| mh-005 | 2 \| 1, 1 | 5 \| 2, 2 | 50k \| 14k, 14k |
| mh-006 | 1 \| 1, 1 | 6 \| 5, 6 | 42k \| 41k, 41k |
| mh-007 | 1 \| 1, 1 | 3 \| 2, 3 | 16k \| 12k, 16k |
| **Total** | **12 \| 9, 9** of 14 | | 449k \| 333k, 253k |

Both 4k runs agree, and lose on the same questions (mh-003, mh-005). The likeliest mechanism:
full passages in search results *look* complete, so the agent stops sooner (mh-005: 2 calls in
both 4k runs vs 5 at 2k) and misses provisions it would otherwise have looked up. The 2k figure
is still a single run. Short search results kept the agent reading; full text is needed only for
the passages it decides to use (e.g. cmp-002's release table).

## Snippets + `get_passage` (2026-10-31)

`search` and `get_qa` now return 2,000-char snippets marked
`…[truncated; get_passage('<key>') for the full text]`; the new `get_passage` tool returns any
passage in full; `get_article` / `get_definition` stay full (4,000). The agent called
`get_passage` 13 times on the 12 routed questions.

| 12 routed agent questions | 2k cap | 4k cap | **Snippets + get_passage** |
|---|---|---|---|
| Score (of 24) | 18 | 19 | **20** |
| Multi-hop (of 14) | **12** | 9 (9 on repeat) | 10 |
| Other routed (of 10) | 6 | **10** | **10** |
| Wrong answers | 1 | 0 | 0 |
| Tokens | 609k | 588k | **482k** |

- **Smoke set, routed:** correctness **0.90** (single-pass 0.78; previous routed 0.86 / 0.88),
  citation recall 0.80.
- cmp-002 is fixed cheaply: 2 calls and 19k tokens (search → `get_passage` on the release
  table) instead of 11 calls and 151k.
- Multi-hop recovers part of the drop (9 → 10) but not to the single 2k run (12): mh-003 again
  stopped after 3 calls without reading RTS Art. 4; mh-005 now cites Art. 181(1)(c)-(d) but
  hedges on the floor.
- One run per configuration; multi-hop differences of 1-2 points are within the run-to-run
  variance seen above (mh-002 and mh-004 each moved by a point between identical runs).

## Next

1. ✅ Routing (Haiku classifier) and ✅ stopping rule — see above.
2. **Passage cap:** chunks reach ~3,700 chars, so a 2,000-char cap truncates tables and long
   points (cmp-002). Raise the cap to cover a full chunk and re-measure.
3. ✅ **API agent loop** for the bring-your-own-key demo (`agent/api_loop.py`): limits on tool
   calls, turns and tokens enforced in RegLens code. Not yet run against the live API.
4. Quality is prioritised over the 50k tokens/question target (multi-hop averages ~65k).
