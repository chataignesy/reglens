# RegLens: current Codex and saved Claude answers — 30-question comparison

**The comparison is complete. Neither setup is a clear quality winner on this cohort.**
Using the same Codex grader, Codex scored higher on 3 in-scope questions, Claude on 3,
and 20 tied. Codex avoided the two wrong/empty outcomes in the saved Claude answers;
Claude received one more full-credit grade. The current Codex run recorded about
half the logical answer-generation tokens of the historical Claude run for these questions.

Personal open-source project; not affiliated with an employer or supervisor; not legal or
regulatory advice. Scores are automated development-evaluation results, not professional sign-off.

Open the [side-by-side answer viewer](codex-claude-smoke30-2026-11-13.html) to select any question
and inspect both full answers, their grades, reference text, citations and reported gaps.
[CSV](codex-claude-smoke30-2026-11-13.csv) and [complete paired JSON](codex-claude-smoke30-2026-11-13.json)
are also available.

## Results in plain language

| Measure | Current Codex | Saved Claude, regraded by the same judge |
|---|---:|---:|
| In-scope questions | 26 | 26 |
| Mean reference score, divided by maximum | **84.6%** | **82.7%** |
| Fully correct under the rubric | **18/26 (69.2%)** | **19/26 (73.1%)** |
| Partially correct | 8 | 5 |
| Wrong or empty | 0 | 2 |
| Usable in-scope answer text | 26/26 | 25/26 |
| Out-of-scope refusals | 4/4 | 3/4 |
| Reference citation-group recall | 81.1% | 84.9% |
| Mechanical claim-check macro pass rate | 100% | 99.6% |
| Reported logical generation tokens, excluding router | **929,724** | **1,831,281** |

84.6% is a mean of 0/1/2 scores, **not** a claim that 84.6% of answers are fully correct.
Both grading reports contain all 30 items, no ungraded items and no automatic verdict-consistency
flags. Their status remains `automated_unreviewed`. The scope-review issues below show why an
absence of consistency flags does not establish that a grading decision is fair.

By question type, both scored 95.8% on the 12 factual questions, 83.3% on the 3 comparison
questions and 83.3% on the 3 applicability questions. On the 8 multi-hop questions the scores
were 68.8% for Codex and 62.5% for Claude. These figures describe the selected development cases,
not performance on an independently sampled population.

## Where the answers differ

| Case | Codex / Claude common score | Assessment |
|---|---:|---|
| `mh-008`: corporate risk weight and output-floor transition | 2 / 1 | Codex covers both the ordinary rule and transition; the saved Claude answer misses the ordinary risk weight. |
| `mh-013`: CCF exposure-value floor | 2 / 0 | Codex gives a usable, cited answer; the saved Claude result is empty. This is a meaningful system-level recovery. |
| `mh-014`: partly government-guaranteed mortgage | 1 / 0 | Codex identifies the decisive exemption for the covered part; Claude leaves that part unresolved. The Codex deduction also raises a rubric-scope issue discussed below. |
| `mh-006`: PD validation and ECB submission | 1 / 2 | Both cover the requested PD and submission rules. The Codex deduction is for analogous LGD/CCF checks; whether those are mandatory for this question needs adjudication. |
| `mh-012`: economic loss | 1 / 2 | Codex omits additional drawings after default. Claude includes that component and the prescribed discounting detail. |
| `mh-015`: maturity option for a EUR 300 million corporate | 1 / 2 | Codex leaves the corporate-size classification unresolved; Claude connects it to the definition and answers the scenario. |

The other 20 in-scope pairs tie. The improved `oos-006` refusal is attributable to the new
deterministic scope guard; it is not evidence that the Codex model itself refuses better.

## Findings that matter more than the small average-score difference

**1. The models can make correct claims while omitting essential facts.**
Both answers to `pd-003` state the ordinary observation-period minimum but omit its conditional
implementation exceptions. Both `mh-003` answers explain fallback machinery while omitting the
normal downturn-LGD condition relative to long-run average LGD. Mechanical citation and number
checks pass despite those omissions. Those checks establish neither completeness nor full
semantic support for every claim.

**2. The research decision still trusts model self-reporting too much.**
In `mh-015`, Codex sets `missing_info=true` but `research_needed=false`. The routed execution
therefore ends after single-pass answering, even though the large-corporate definition exists
in the local processed corpus. This is a useful honest qualification rather than an invented
answer, but a research assistant should fetch the known missing definition. The next fix should
verify whether an explicitly required gap has an available corpus target before accepting that
further research cannot help.

Only two Codex answers report missing information, although eight receive partial scores.
Six common-judge partial answers therefore carry no missing-information warning. Some deductions
are debatable, as below, but clear omissions such as the implementation exception demonstrate
that the completeness flag is not a reliable success signal.

The two specific neutral-reference warnings from the initial Codex pilot are absent in the
new `mh-013` and `mh-014` outputs. The saved-evidence replay isolates the guard fix; fresh
generation also changed the answers, so the live absence alone does not prove full dependency coverage.

**3. Retrieval needs explicit question coverage and source selection.**
`app-001` asks about Foreword paragraphs 1–3. The Codex context includes paragraphs 1 and 3,
not 2; its answer acknowledges that paragraph 2 was not supplied but still reports no missing
information. It omits a purpose expressed in that paragraph. A source-bound question should
still require reading its explicitly requested passage range.

For `cmp-001`, both answer the consolidated rule rather than identifying the amending-act
provision requested by the question. `sources.yaml` excludes the amending act from default
search, while explicit source selection can include it. Local processed artifacts contain
Article 1(86). An explicit amendment-provenance question should include that source in retrieval.
Post-pause database connectivity was unavailable for a fresh SQL audit; this availability check
used source code and processed artifacts, not a new live-database count.

The local processed Article 180 parent qualifiers also contain the implementation exception
missed by both observation-period answers. Bounded reading of relevant parent qualifiers is
a more promising shared improvement than merely switching the model.

**4. Two rubric-scope questions need review before these scores become a headline benchmark.**

- `mh-006` asks about PD back-testing and submission. The sole Codex deduction is omission of
  analogous LGD/CCF checks. The answer covers the PD duties and submission rule. A practitioner
  should decide whether the additional parameter checks are mandatory scoring facts here.
- `mh-014` asks whether PD and LGD floors apply. Codex answers the covered/uncovered distinction
  correctly. Its deduction includes the unasked CCF exemption and the numeric uncovered-part
  floors. The mandatory status of these additional facts should be stated explicitly.

These are engineering review observations, not score adjudications. All raw scores and frozen
references remain unchanged. Record any later scope decisions separately and version future
rubric changes; do not edit this snapshot after seeing the provider results.

## Why the common grader was necessary

The saved Claude answers originally scored **76.9% on this selected cohort** under Haiku.
Regrading the exact same text with Codex gives **82.7%**. `dod-008`, `lgd-006` and `app-002`
each change from 1 to 2. This is a grading change, not an improvement in Claude generation.

The 5.8-point change caused by the grader is larger than the 1.9-point difference between
the providers under the common grader. That sensitivity is another reason to avoid declaring
a model winner. The common grader still belongs to the Codex model family, so self-grading
bias remains possible even though provider labels are absent from its prompts.

## Runtime, usage and interruption

The user approved 2–4 million Codex subscription tokens. Actual known new usage was:

| Phase | Known tokens |
|---|---:|
| Generate the 30 Codex answers, including retries and fallback | 929,724 |
| Grade Codex answers | 339,240 |
| Regrade saved Claude answers | 345,392 |
| **Known new total** | **1,614,356** |

One refused grading call did not report usage; it remains explicitly unknown, not zero.
There were 52 successful generation calls, 51 successful grading calls and that one refused
call. No new Claude answers were generated. The old Claude token column is historical logical
work recorded in its manifest, not additional usage in this run.

The Codex generation count is about 49% lower than the historical logical Claude count for
the same cohort. Models, tokenizers, prompts, helper accounting and orchestration differ;
this is a reported-workload comparison, not a monetary saving or equal subscription-quota
depletion comparison. Codex API-equivalent prices remain unconfigured.

Generation took **12 minutes 44 seconds**. Measured answer-execution time had a median of
**19.6 seconds** and a maximum of **68.0 seconds**; those per-question measurements exclude
the separate route gate. Resumed common grading took **4 minutes 53 seconds**. Historical
per-question Claude latency is unavailable, so a reliable speed ratio cannot be calculated.

Generation ran at approximately 19:18–19:31 Berlin time. The first grader call hit the CLI's
usage limit. After the user asked to continue, grading resumed at 22:19 and finished at 22:24.
The intervening wall time includes quota waiting and a chat pause; it is not evidence that
the service was necessarily unavailable for that entire interval.

All answers were reused by hash during recovery. Grading-only manifests preserve the exact
answer entries under new run IDs; no answer was regenerated or selected for a better score.

## What was held fixed, and what was not

The cohort contains 12 factual, 8 multi-hop, 3 comparison, 3 applicability and 4 scope questions.
It was fixed before generation and deliberately includes known regressions. Both sets use
the same frozen question/reference snapshot, and the historical planned routes are replayed.
The local embedding/reranker identities match the historical run; no corpus ingestion was done.

Codex uses `gpt-6.1-sol`, the bounded RegLens JSON tool loop and product code at `f5101a5`.
The saved Claude answers use the earlier `claude-sonnet-5-5` system at `3517a13` and its native
MCP workflow. Both are graded with `gpt-6.1-sol`, prompt version `75d32dd9`. Code and workflow
differences prevent attributing score or token differences solely to the underlying models.
This is a development regression cohort, not a new holdout or a full 118-question rerun.

The prior 239-test check covers the product code used for generation. This run additionally
verified all new answer and grading hashes, the frozen references, all 118 historical answer
hashes, the old full-run manifest/grades and the unchanged interrupted comparison result.
No task-owned inference worker remains running. New recovery/export scripts passed Ruff;
the side-by-side viewer was checked against all 30 paired records.

## Recommended next work

Keep both backends available. Before expanding the benchmark, prioritise required-gap escalation,
explicit passage-range coverage and amendment-aware source selection. Adjudicate the two scope
questions in the grading rubric, then rerun the affected regressions and add an unseen holdout.
The present data do not justify replacing the default backend on accuracy grounds.

Audit and reviewer notes: [integrity record](../review/codex-claude-smoke30-audit-2026-11-13.json).
The paired JSON retains the exact source-run path/hash, all known call receipts and the original
Haiku scores. Recovery is reproducible with
`docs/review/resume_codex_claude_smoke_grading.py`; report export uses
`docs/review/summarize_codex_claude_smoke.py` and makes no model calls.
