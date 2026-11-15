# Focused Codex coverage evaluation — 14 November 2026

Personal project; not affiliated with an employer or supervisor; not legal or regulatory advice.

Completed 2 fresh routed answers against unchanged frozen references. Automated mean score: **75.00% → 100.00%** on this selected development cohort. This is not a full benchmark or an independent holdout.

Usage: **109,121 known tokens** of the 750,000-token reserve; 7 calls; zero unknown-usage calls. All answer attempts, model-call artifacts and source hashes were verified. Claude remains the default configuration.

| Question | Saved score | New score | Route / attempts | Missing-info flag |
|---|---:|---:|---|---|
| dod-005 | 1 | 2 | single | False |
| mh-012 | 2 | 2 | single | False |

Scores use 0/1/2; the mean divides by two. Grades are automated and unreviewed by a practitioner. Citation checks and gap flags do not certify completeness.

## Remaining omissions

The automated judge reported no missing key facts.

## Cost and verification

| Purpose | Tokens |
|---|---:|
| route | 24,618 |
| answer | 37,309 |
| answer_completion | 18,671 |
| judge | 28,523 |

Active model-call time: 115.4 seconds. Mechanical checks: 100.0%; citation-group recall: 75.0%.

This two-case check targets cure conditions and economic-loss research specificity. It does not rerun the other cases or provide an independent holdout.

Routing plus answer usage falls from **134,702 to 80,598 tokens** on this pair (40.2% lower).
The cure answer uses one focused context-only rewrite within the existing two-call limit;
economic loss needs no agent fallback and no longer retains a missing-information flag.
Total usage including grading falls from 165,203 to 109,121 tokens (33.9% lower).
Neither answer has missing key facts, contradictions or inconsistent-verdict flags according
to the automated judge. [Implementation and local verification](../review/COVERAGE-PRECISION-VERIFICATION-2026-11-14.md).

No product code was changed during this run. Historical answers, references and published scores remain unchanged. Fresh routes and isolated answer caches were used. Judge verdict caching follows the existing exact-content identity; purpose totals show actual new grading usage.

[All answers, grades, baseline comparisons and audit counts](codex-coverage-precision2-2026-11-14.json).

Run: `20261114-213122-572455-routed-codex-coverage-precision2`. Raw result: `C:\Development\RegLens\data\evals\comparisons\20261114-202925-271211-codex-coverage-precision2\result-20261114-203132-332360.json`.
