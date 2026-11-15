# Source-linked conditions and research precision: verification

Personal project; not affiliated with an employer or supervisor. Not legal or regulatory advice.

## Outcome

The follow-up addresses both issues observed in the eight-question run. All **267 local tests
pass**, including disposable Postgres checks. A new two-question Codex run gives full credit to
both cure conditions and economic-loss components, with neither answer reporting a gap. The
prior run gave partial/full respectively and left the full-credit economic-loss answer flagged.

The [new live report](../results/codex-coverage-precision2-2026-11-14.md) retains all answers,
grades, receipts and audit counts. The full118 and eight-question results remain unchanged.
There was no product-code change, corpus publication or question/reference change during this run.

## Implementation

- Duration questions can require an immediately following condition list when the source
  explicitly links it to the previous paragraph's period. The time-rule topic must match;
  document/block identity and every caller filter are retained. Up to four document-diverse
  anchors are probed. Conditions are checked even when not cited or mentioned by the draft.
- A condition's main predicate is checked before its explanatory tail. Mentioning incidental
  restructuring vocabulary no longer covers an omitted payment or arrears requirement. Split
  windows are joined only after the whole logical list has been delivered.
- Broad relevant neighbours remain candidates for the pre-draft context budget. Mandatory
  unread-unit signals require a scope relationship, explicit child list, time-linked condition
  or a directly requested facet. Merely sharing a topic no longer forces repeated peer research.
- A valid first draft with structural omissions from already-delivered evidence can use the
  existing second-call allowance for a focused rewrite. Format repair and completion share the
  same two-call maximum. Remaining gaps stay visible and can use normal bounded routed fallback;
  no third single-pass draft is allowed. The trace records `answer_completion` and its targets.
- No ordinary-answer semantic judge was added. Agent tool/turn/token budgets and the shared
  four-extra-row / 12,000-character context cap remain unchanged. New helper code affects cache
  identity, including the single/routed/API/Codex and Claude/MCP post-answer guard paths.

## Local evidence

Eight new no-model regressions cover silent omissions, explicit scenario exclusions, unrelated
conditions, anchor crowding by another document, incidental explanation words, successful and
unsuccessful second drafts, and sharing the second call with contract repair. A new disposable
SQL test covers block boundaries, filtering, split-window delivery/caps and the API/Codex
pre-final signal. Ruff and `git diff --check` pass.

The [raw-draft replay](coverage-precision-local-2026-11-14.json) uses provider outputs captured
before the earlier guard changed their gap flags. It detects the actual silent cure omission,
clears the economic-loss draft's unnecessary structural research signal, retains genuine
governance and unread maturity-list gaps, and leaves the scope, validation and two controls clear.
Run `.venv\Scripts\python.exe docs/review/check_coverage_precision.py` to reproduce it locally.

## Fresh live evidence and cost

The stated conservative estimate was 750,000 tokens (375,000 per question for routing, all
answer/retry/fallback turns, repairs and grading), below the project's 1M approval threshold.
The run used **109,121 known tokens**, seven new calls, zero quota rejections and zero unknown
usage. All seven call artifacts, both final answer artifacts, receipts, source identity and
the run manifest were verified. Historical evidence hashes still match.

| Case | Prior focused score / gap | New score / gap | New execution |
|---|---|---|---|
| `dod-005` | Partial / unflagged | Full / no gap | Single draft plus one context-only rewrite |
| `mh-012` | Full / flagged | Full / no gap | One single-pass draft; no agent |

Routing plus answers use **80,598 tokens versus 134,702** for these same two cases in the prior
run, a **40.2% reduction**. Including grading, usage falls from 165,203 to 109,121 (33.9%).
The cure answer costs more because it now states the missing conditions; removing the economic
loss fallback saves more than that increase. Active model-call time is 115.4 seconds. Mechanical
citation checks pass 100%; citation-group recall is 75%. These are different signals.

This comparison is descriptive: two previously used development questions, one fresh trajectory
each, unchanged automated judge `gpt-6.1-sol` / prompt `75d32dd9`, no practitioner review. It is
not evidence that all eight cases or the full benchmark now score perfectly or cost 40% less.
The new three-way distinction (discovery, missing reading, omitted delivered facts) still depends
on finite structural and lexical patterns. Synonyms, other source structures and undiscovered
qualifications remain limits; no missing flag is a completeness certificate.

## Next work

The two demonstrated follow-up failures are resolved on this focused check. Remaining broader
quality work includes amendment-introduction citations, cost/routing measurements on a wider
cohort, practitioner adjudication and a separately authored holdout. Any additional model run
needs its own estimate and the usual approval if over the threshold. No full rerun was launched.
