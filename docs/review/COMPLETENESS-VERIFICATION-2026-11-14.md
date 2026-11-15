# Scope and list-coverage follow-up: local verification

Personal project; not affiliated with any employer or supervisor. Not legal or regulatory advice.

Live follow-up completed after user approval: [eight-question results](../results/codex-completeness8-2026-11-14.md).
Seven full / one partial; 582,354 tokens of the approved 3M. Scope recovery worked, but a silent
cure-condition partial and additional research cost remain. The local-only record and original
planning estimate below are retained as the pre-run account.

Implemented on the existing `codex/frozen118-followup` checkout. The old frozen references,
manifests, answer records, grades and published benchmark results are unchanged. No model calls,
corpus publication or inference startup occurred in this session.

## Implemented behavior

- A source-matched applicability question can obtain indexed scope/addressee paragraphs before
  drafting. A still-unread eligible whole unit produces a specific required-gap handoff even
  when the draft says further research is unavailable. Registry applicability labels are not
  treated as legal evidence.
- Requested lists can recover split child points and relevant mandatory peers in the same
  article or narrowly shared section. Guidance block identifiers are not treated as articles.
  Enumerated items with wholly absent distinctive vocabulary cause a coverage-review signal;
  generic statements that all conditions must be met do not establish coverage of those conditions.
- Expansion still shares four extra rows / 12,000 characters with existing helpers. Candidate
  queries are bounded to 40 rows per anchor, at most four anchors plus one scope probe, eight
  target units and 12 reported signals. Whole-unit resolution rejects ambiguous sources and
  units over 80 windows. Already delivered candidates are ranked last, so reading the first
  eight cannot hide remaining known children. Existing tool, turn and token budgets remain intact.
- Shared guard integration covers single/routed answers, the API/Codex pre-final nudge and all
  agents' final delivery checks. Traced evidence includes reads omitted from final citations.
  Corpus keys are checked separately from resolved C# keys. The new helper affects cache identity.

## Evidence

`pytest -q` with `REGLENS_TEST_ADMIN_URL` set to the local database: **258 passed**, including
disposable Postgres checks. Ruff passes for `src`, `tests` and the free verification script.
Ten new structural regression tests cover scope, whole-window budgets, omitted conditions,
dot labels, inline-reference specificity, guidance blocks, pre-final corpus keys, explicit empty
source restrictions, source/part ambiguity and target-cap continuation. A new disposable-database test exercises source,
institution, date, legal-level and applicability-condition filters, including a partially excluded
logical unit and a missing user input. No test calls a model.

Reproduce the real-corpus checks from the repo root:

```powershell
.venv\Scripts\python.exe docs/review/check_required_coverage.py
```

The [machine-readable result](required-coverage-local-2026-11-14.json) records the answer-code hash,
specific target keys and guard signals. All six representative saved failures produce a signal:
scope (`app-004`), cure conditions (`dod-005`), validation tools (`val-001`), governance (`lom-001`),
economic-loss components (`mh-012`) and maturity exceptions (`irb-007`). The actual EBA scope
paragraphs 7/8, CRR 185(c), EBA PD/LGD paragraph 143 and all five CRR 162(3) child points are found
through structure rather than question IDs or hard-coded conclusions.

For each of those six contexts, three new negative development questions (publication date,
document identification and an unspecified bank's applicability) produce no evidence targets.
An explicit empty source restriction also produces none. Six new paraphrases still produce
targeted signals; an adjacent life-insurance-collateral conditions question detects incomplete
coverage in an intentionally incomplete synthetic draft using real indexed structure.
These are development controls, not
an independent holdout or generated-answer evaluation.

Running the guard over all 103 saved in-scope answers flags 10: nine saved partial answers and
the unanswered scope case. It also flags five of the 76 saved full-credit answers: `lgd-007`,
`crm-001`, `mh-013`, `mh-020`, `cmp-006`. The last two are existing unresolved-requirement signals;
the first three show the new checks can request review beyond an already full-credit rubric.
That specificity cost remains visible. Seventeen saved partial answers still receive no signal.
These counts are guard diagnostics, **not new grades or a measured score improvement**.

Finite probes, literal source wording, English question patterns and lexical signals have limits.
Matching vocabulary does not prove entailment; synonyms can cause unnecessary review; omitted
facts without the recognised structure may pass undetected. Candidate/section bounds can leave
undiscovered requirements. Tool-budget exhaustion leaves detected requirements visible rather
than certifying completion. New paraphrases of development questions remain development tests.

## Proposed live verification and approval boundary

Use a fresh eight-question Codex answer-and-grade cohort: the six representative failures plus
an adjacent list question and a scoped optional-detail control, with new IDs/artifact namespace
for new wording. Retain every attempt; compare missing facts, gap flags, citations, tokens and
time with the saved baseline. No full benchmark rerun is proposed.

Conservative planning allowance per question (all turns, not a single provider request):

| Work | Tokens |
|---|---:|
| Fresh route | 15,000 |
| Single draft and possible contract retry | 50,000 |
| Agent turns / fallback, including final-turn reserve allowance | 240,000 |
| Format repair allowance | 25,000 |
| Grading | 30,000 |
| Extra contingency | 15,000 |
| Total per question | 375,000 |
| Eight questions | **3,000,000** |

Estimate command executed without model calls:

```powershell
.venv\Scripts\reglens.exe --config config.codex.yaml estimate --input 350000 --output 25000 --calls 8
```

The CLI reports 3M tokens and requires approval. Its per-call label here represents a per-question
aggregate planning envelope. This is an estimate, not a hard aggregate cap; enforce a run-level
reserve and stop on quota rejection or unknown usage when implementing the live cohort runner.
The [project budget rule](../../CLAUDE.md) says: "if a run exceeds **1M tokens** ... ask first."
**Live execution is pending that approval.** The completed benchmark's 8M approval does not carry
over. Semantic recovery, score changes and real model cost/time are therefore not yet measured.
