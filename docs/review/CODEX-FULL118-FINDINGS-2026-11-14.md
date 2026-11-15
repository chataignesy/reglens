# Review of the completed Codex frozen118 benchmark

Personal project; not affiliated with any employer or supervisor. Not legal or regulatory advice.

## Outcome

The full run is complete on product revision `d8c8b40`. All 118 questions have fresh answer/refusal
records and final grades against the unchanged frozen references. The mean in-scope score is
**86.4%**: **76 full, 26 partial, one wrong/unanswered**, with **15/15 out-of-scope refusals**.
The grades are automated and unreviewed by a practitioner. The score gives partial answers half
credit; it is not the percentage of fully correct answers, which is **76/103 = 73.8%**.

The run used **5,776,251 known new Codex subscription tokens**, plus one quota rejection with
unreported usage. It stopped at the subscription limit and resumed after the reported reset,
preserving all prior answers. No source-code or reference changes were made during the run.

See the [full results](../results/codex-frozen118-2026-11-14.md),
[all answers and grades](../results/codex-frozen118-2026-11-14.json), and
[question-level scores](../results/codex-frozen118-2026-11-14.csv).

## What the results show

**The focused retrieval fixes work in the full run.** The amended-floor provision (`cmp-001`),
foreword range (`app-001`), corporate/retail PD-history rules (`pd-003`), and maturity question
(`mh-015`) all received full credit. For maturity, the first draft reported a missing definition;
the guard found its actual corpus key and caused the single-to-agent fallback. This run therefore
exercised that guard directly, unlike the earlier small run's transport-error fallback.

**Reliable citations do not establish complete answers.** The mechanical claim-check mean was 99.0%,
but 26 answers were graded partial. **22 of those 26 did not mark themselves incomplete.** Some
rubric-scope cases still require adjudication, but the model's completeness flag is plainly not a
reliable general stopping condition. The current safeguards cover useful specific patterns; they
do not close the broader coverage problem.

**One answer failed because the correct scope text was not retrieved.** For `app-004`, the question
asks whether EBA definition-of-default guidelines apply to less significant institutions. The
answer says the supplied passages cannot establish this. Its context contains technical application
paragraphs 86/88/94 and ECB material, rather than the EBA scope/addressee provisions. A read-only
database check confirms that EBA paragraphs 7 and 8 are indexed. The draft reports the required
scope gap but stays on the single-pass path, so it never reads them. The raw grade of zero is
preserved: under this rubric, failure to answer is scored alongside a wrong answer, even though
the response avoids making an affirmative false legal claim.

The earlier 30-case Codex answer for `app-004` received full credit after an agent fallback. This
run's single-pass answer received zero. That regression is a useful reminder that a syntactically
valid answer can still stop before obtaining an available required fact.

**Missing conditions and incomplete lists recur.** Examples include cure requirements (`dod-005`),
validation requirements (`val-001`), model governance responsibilities (`lom-001`), and the set of
maturity exceptions (`irb-007`). `mh-012` still omits post-default drawings and the prescribed discount
rate according to the frozen rubric. The detailed omission list is in the results report; these
are grading observations, not independently certified regulatory conclusions.

**One mechanical citation warning remains.** `cmp-001` receives full semantic credit but has
`unsupported_number(160)`: the claim identifies the amended article while citing its child
amendment text, which omits the enclosing introduction. The evidence selection/citation structure
should include that introduction. The mechanical warning is preserved alongside the semantic grade.

## Priorities for the next implementation

1. Add bounded scope/addressee probes when an applicability answer declares a required missing
   scope fact. Preserve source/date/institution restrictions and whole logical units. The existing
   quoted-definition probe is too narrow to handle the `app-004` gap.
2. Strengthen coverage checks for questions asking for components, conditions or exception lists.
   Use question-level requirements and source structure, and explicitly distinguish required facts
   from optional background. Test on unseen paraphrases and adjacent topics to limit overfitting.
3. Include the enclosing introduction when citing nested amendment points, so the amended article
   and its replacement text can both be supported by the delivered evidence.
4. Reduce routing overhead only after checking answer-quality effects. Fresh routing used
   **1,417,530 tokens**, about **24.5% of all known run usage**. A cheaper or local routing approach is
   worth testing, together with dependable escalation when the initial answer is incomplete.
5. Adjudicate the suspected rubric overreach for `mh-006` and `mh-014` separately. Their frozen
   references and raw scores remain unchanged. Then add an independent holdout before treating
   gains on this development set as evidence of general quality.

No further product changes or model runs were made in response to these findings during this
benchmark. They define follow-up work; this report does not claim that every issue is fixed.

## Performance and comparison limits

Across all attempts, active model-call times were approximately **9.9 minutes routing, 45.0 minutes
answer generation, and 9.0 minutes grading**. These exclude the overnight quota pause, local SQL
work and service startup. This is a sequential subscription-CLI run, not a concurrent production
load test.

There were 392 recorded requests: 391 successful responses and one quota rejection with unknown
usage. Of 103 in-scope grades, 100 were newly generated and three exact-content cached verdicts
were reused (`pd-001`, `floor-001`, `cmp-002`). Fifteen out-of-scope grades were deterministic.
Fresh answer generation did not reuse pilot answers.

On the fixed 26 in-scope questions overlapping the earlier smoke comparison, the current Codex
mean is **92.3%**, versus **84.6%** for the earlier Codex answers and **82.7%** for the saved Claude
answers under the earlier common judge. Six current Codex answers improved and one regressed
relative to the earlier Codex set. These observations are not a controlled model comparison:
code, routing, sampling and generation dates differ, and the questions have already guided fixes.

The earlier full Claude score used a different judge model, so it should not be ranked directly
against this full Codex score. No additional Claude generation or grading was performed here.
