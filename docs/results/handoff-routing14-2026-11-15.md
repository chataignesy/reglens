# Broader verification and routing comparison — 15 November 2026

Personal project; not affiliated with an employer or supervisor; not legal or regulatory advice.

Two fresh arms on 14 identical frozen development questions: 13 in scope and one out-of-scope control. The product, corpus, model and references match; routing strategy differs. One trajectory per arm; this is not an independent holdout.

| Metric | LLM routing | Single-first |
|---|---:|---:|
| In-scope automated mean | 92.3% | 88.5% |
| Full / partial / wrong | 11 / 2 / 0 | 10 / 3 / 0 |
| Correct refusals | 1/1 | 1/1 |
| Routing + answer tokens | 609,457 | 316,536 |
| Known total tokens, including grading | 787,814 | 499,640 |

Routing + answer change: -48.1% for completed answer attempts. Known total usage: 1,287,454 against the approved 3M reserve, plus 1 request(s) with unreported usage. Known totals are lower bounds when usage is unknown. Every model-call and answer-attempt artifact was verified, including failed calls.

| Case | LLM score | Single-first score | LLM tokens | Single-first tokens |
|---|---:|---:|---:|---:|
| dod-005 | 2 | 2 | 48,898 | 35,619 |
| pd-003 | 2 | 2 | 29,675 | 16,525 |
| mh-006 | 1 | 1 | 87,057 | 18,396 |
| cmp-001 | 2 | 2 | 30,432 | 15,302 |
| cmp-002 | 2 | 2 | 30,117 | 18,753 |
| app-001 | 2 | 2 | 30,254 | 18,782 |
| lgd-007 | 2 | 2 | 31,162 | 15,843 |
| val-001 | 2 | 2 | 30,736 | 19,348 |
| lom-001 | 2 | 1 | 48,845 | 35,302 |
| mh-012 | 2 | 2 | 54,359 | 19,596 |
| oos-006 | 2 | 2 | 0 | 0 |
| mh-014 | 1 | 1 | 58,608 | 17,004 |
| app-004 | 2 | 2 | 28,212 | 16,954 |
| irb-007 | 2 | 2 | 101,102 | 69,112 |

## Interpretation and limits

The default remains LLM routing. Single-first is an opt-in policy with the same scope/retrieval gate and bounded required-gap fallback; it is not a completeness guarantee. Grade differences may reflect sampling as well as routing. Policy agreement with question-type labels is not an answer-quality metric.

Score regressions under the unchanged rubric: lom-001. Missing-fact lists, contradictions, gap flags, citations, traces and source references are retained in the machine-readable report. Exact-content judge caching uses the existing identity; token totals count only actual new calls.

The governance difference is an observed answer difference, not an established causal effect of
routing: both arms planned a single-pass answer and used a context-only rewrite. The candidate
omitted the duty to ensure adequate credit approval, monitoring and control processes. Neither
arm flagged its graded partial answers as missing information. Lexical coverage checks therefore
remain incomplete, and this pilot does not demonstrate quality equivalence or justify changing
the default. The amendment case is full credit with 100% mechanical checks in both arms; its
formerly unsupported article number is now supported by the enclosing introduction's citation.

Both arms pass mechanical checks at 100% and achieve 83.3% citation-group recall. Those metrics
do not establish answer completeness. The current LLM-arm partials are `mh-006` (analogous
LGD/CCF analysis omitted under the frozen rubric) and `mh-014` (numerical uncovered-part floors
and the rubric's CCF exemption omitted). The latter is a new partial trajectory, while the older
full-credit answer and grade remain preserved in the earlier benchmark report.

The frozen references and historical raw grades for mh-006/mh-014 are unchanged. Independent practitioner review and a separately authored sealed holdout remain pending at the user's request. No full benchmark was rerun.

The LLM arm was interrupted by subscription quota and explicitly resumed by the user. Completed answers were reused; the rejected request remains preserved as unknown usage, never zero. No product code changed between attempts or arms.

[All answers, grades, usage and audits](handoff-routing14-2026-11-15.json).
