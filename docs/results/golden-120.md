# Golden set extension — 40 new questions (2026-11-05)

The golden set grew from 80 to **120 verified questions** (`evals/golden/phase2.jsonl`). The 40
new ones are weighted to known weak spots:

- 11 multi-hop questions;
- 8 comparison and applicability questions;
- 15 factual questions on downturn LGD, IRB parameters, CCF, CRM, MoC and validation;
- 6 *near-miss* out-of-scope questions (topics close to credit risk but outside the corpus).

Every reference was checked in the source text. Flagged items were reviewed by the author.

The setup is the same as the [Phase 3 milestone](golden-phase3.md):

- Claude Sonnet 5.5 answers.
- The Haiku router picks single-pass or the agent (snippets + `get_passage`, at most 10 tool calls).
- The Haiku judge grades each answer 0 / 1 / 2.

Reproduce:

```
uv run reglens eval-route --set phase2 --yes
uv run reglens eval-answers --set phase2 --yes             # single-pass only
uv run reglens eval-answers --set phase2 --route --yes     # routed
uv run reglens judge --set phase2 --yes && uv run reglens judge --set phase2 --agent --yes
```

## Headline

| 34 new in-scope questions | Single-pass only | **Routed** |
|---|---|---|
| Correctness (mean score / 2) | 0.72 | **0.87** |
| Fully correct / partly / wrong | 20 / 9 / 5 | **25 / 9 / 0** |
| — multi-hop (11) | 0.59 | **0.86** |
| — other (23) | 0.78 | **0.87** |
| Citation recall | 0.74 | **0.88** |
| Claims passing the citation check | | **0.99** |
| Tokens (answers) | 252k | 1,352k |

- **Out of scope:** 5 / 6 near-misses declined, both single-pass and routed (see oos-014 below).
- **Routing:** 21 of the 34 in-scope questions went to the agent. 3 more fell back to it after
  a single-pass answer reported missing information. The other 10 stayed single-pass.
- **Changes vs single-pass:** 8 better, 1 worse (dod-011, 2 → 1: it omits part of
  para. 77). All five wrong single-pass answers became partly or fully correct.
- **Harder than the first 80**, as intended: single-pass scores 0.72 here against 0.86 on the
  earlier set. Retrieval recall@10 is 0.76 against 0.84. The agent closes most of that gap.

## All 120 questions

The table combines the earlier set (after the [four fixes](golden-phase3.md)) with the new one.

| | Earlier 70 in-scope | New 34 in-scope | **All 104 in-scope** |
|---|---|---|---|
| Correctness, routed | 0.91 | 0.87 | **0.89** |
| Fully / partly / wrong | 57 / 13 / 0 | 25 / 9 / 0 | **82 / 22 / 0** |
| Citation recall | 0.90 | 0.88 | **0.89** |
| Out-of-scope declined | 10 / 10 | 5 / 6 | **15 / 16** |

## What went wrong, and what was fixed

1. **The agent's tools were hidden (fixed).** The first routed run spent ~1.1M tokens with no
   tool call in any of the 21 agent answers.

   *Cause:* the `claude -p` CLI can defer MCP tools behind its ToolSearch tool. RegLens starts the
   CLI with `--tools ""` to switch off the built-in tools, and that also removes ToolSearch, so
   the RegLens tools never loaded. It depended on the CLI's working directory. Small Haiku
   probes isolated it.

   *Fix:* the provider starts the CLI with `ENABLE_TOOL_SEARCH=false`. Two safeguards were added:
   - An agent answer with no tool call is treated as ungrounded: dropped, and the question is
     answered single-pass.
   - The eval records a failed item instead of stopping.

2. **Cost cap (fixed).** At its $0.75 cost cap, `claude -p` stops without an answer. That used to
   crash the run. Now the agent reports the cap, and both the router and the eval answer
   single-pass instead. The UI timeline shows "agent stopped".

3. **Raw newlines in JSON (fixed).** One agent answer (mh-023) put a raw control character
   inside a JSON string, so it failed to parse. The judge still graded the raw text 2. The
   parser now accepts it (`strict=False`).

4. **oos-014, a borderline near-miss (open).** *"How should a bank assess credit concentration
   risk in its ICAAP?"* The single-pass answer reported missing information, so the agent took
   over. The agent did not decline. It said the corpus has no ICAAP provisions, then summarised
   the EBA loan-origination expectations on concentration limits, with citations. The answer is
   honest and grounded, but it is still an abstention miss. ICAAP is Pillar 2 and out of scope.

5. **Partly-correct answers (9).** Most hedge where the reference is definite, for example
   app-004: "in all likelihood" instead of "yes, it applies to LSIs". Others leave out a
   secondary element (mh-014: the PD floor value; app-002: the dilution-risk exclusion). None
   contradicts the reference.

## Cost

About 2.9M tokens for this evaluation:

| Step | Tokens |
|---|---|
| Single-pass answers | 252k |
| Routed answers, broken first run (agent tools hidden) | 1,112k |
| Routed answers, clean re-run | 1,352k |
| Judging | 128k |
| Router and probes | small |

The tokens vary a lot between agent answers, from 18k to 178k (irb-007, after a fallback). That
is why the per-question cost cap matters.
