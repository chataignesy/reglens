# Focused Codex completeness evaluation — 14 November 2026

Personal project; not affiliated with an employer or supervisor; not legal or regulatory advice.

Completed eight fresh routed answers against unchanged frozen references. Automated mean score: **56.25% → 93.75%** on this selected development cohort. This is not a full benchmark or an independent holdout.

Usage: **582,354 known tokens** of the approved 3M; 36 calls; zero unknown-usage calls. All answer attempts, model-call artifacts and source hashes were verified. Claude remains the default configuration.

| Question | Saved score | New score | Route / attempts | Missing-info flag |
|---|---:|---:|---|---|
| dod-005 | 1 | 1 | single | False |
| app-001 | 2 | 2 | single | False |
| lgd-007 | 2 | 2 | single | False |
| val-001 | 1 | 2 | single | False |
| lom-001 | 1 | 2 | single → agent | False |
| mh-012 | 1 | 2 | single → agent | True |
| app-004 | 0 | 2 | single | False |
| irb-007 | 1 | 2 | single → agent | False |

Scores use 0/1/2; the mean divides by two. Grades are automated and unreviewed by a practitioner. Citation checks and gap flags do not certify completeness.

## Remaining omissions

- **dod-005**: Reclassification also requires a material payment during the probation period, no past-due amounts, and no remaining concerns about full repayment.

The cure answer also reports `missing_info: false`: a silent partial remains. The saved baseline
answer mentioned that all cure conditions must be met, which activated the local lexical guard;
this fresh answer omitted that sentence as well as the conditions, and did not activate it.
Thus, the local replay did not establish robust detection across new model outputs.

Conversely, `mh-012` receives full credit while retaining `missing_info: true` for further
economic-loss adjustments and indirect-cost detail. The guard can cause additional reading beyond
what the frozen rubric needs. A finite availability probe does not determine which legal details
are indispensable to a particular question.

## Cost and verification

| Purpose | Tokens |
|---|---:|
| route | 104,186 |
| answer | 142,674 |
| agent | 219,040 |
| judge | 116,454 |

Active model-call time: 481.3 seconds. Mechanical checks: 100.0%; citation-group recall: 87.5%.

The two controls are `lgd-007` (an adjacent cost-component list) and `app-001` (a foreword-bound answer where additional applicability research is optional). Compare their attempts and tokens as well as scores; a retained full score does not establish that added work was necessary.

Routing plus answer usage increased from **250,553 to 465,900 tokens** (about **86%**), excluding
grading from both figures. Governance, economic loss and maturity used single-to-agent fallbacks.
Both controls retained a single-pass route: `app-001` used 32,032 versus 30,292 baseline tokens;
`lgd-007` used 31,113 versus 29,235. These uncontrolled single-sample differences are descriptive.

The scope fix is exercised directly: `app-004` moves from zero to full credit on a single-pass
answer using scope/addressee evidence. Validation moves from partial to full without fallback.
There are no judge contradictions or consistency flags. The remaining silent cure partial and
extra research cost warrant further targeted work before proposing a fresh full benchmark.

No product code was changed during this run. Historical answers, references and published scores remain unchanged. Fresh routes and isolated answer caches were used. Judge verdict caching follows the existing exact-content identity; purpose totals show actual new grading usage.

[All answers, grades, baseline comparisons and audit counts](codex-completeness8-2026-11-14.json).

Run: `20261114-185751-241908-routed-codex-completeness8`. Raw result: `C:\Development\RegLens\data\evals\comparisons\20261114-175004-126803-codex-completeness8\result-20261114-175833-393925.json`.
