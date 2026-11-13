# Dependency fix and planned 30-question comparison — 2026-11-13

Personal open-source project; not affiliated with an employer or supervisor; not legal advice.

## Completed without new model calls

The dependency guard previously promoted any cited “in accordance with Article …” reference
into an unanswered requirement. This produced unnecessary Article 166(8) and Article 230
warnings in the two successful Codex answers. The guard now treats these neutral references
as research candidates rather than automatic proof of missing information. Pre-reading still
discovers them. Explicit qualifications such as “subject to” remain mandatory checks, and a
model-reported required calculation gap still escalates.

**239 tests passed**, including disposable Postgres integration checks. Ruff and diff checks
passed. [Two saved-evidence replays](dependency-scope-replay-2026-11-13.json) isolate the
deterministic change: the previous guard adds each warning, while the new guard does not.
The replay assumes complete input flags to test the guard only; it does not rewrite answers,
claim that the model has been rerun, or remove genuine reported gaps.

## Concrete live-run plan

The [fixed cohort](../../evals/cohorts/codex-claude-smoke30-2026-11-13.json) contains 12 factual,
8 multi-hop, 3 comparison, 3 applicability and 4 out-of-scope questions from the unchanged
reviewed 118-question snapshot. Known regressions and document-bound controls are included.
Selection precedes generation. This is a regression-enriched development sample, not a random
sample or an unseen holdout.

1. Generate new Codex answers with the dependency fix. Replay the old planned routes so
   classification does not add another changing variable; the actual route may still fall back.
2. Reuse the matching saved Claude answers from the previous full run. Validate the exact
   frozen references and original manifest/answer hashes; do not regenerate or overwrite them.
3. Grade both answer sets with the same Codex model, prompt and reference criteria. The grading
   prompt does not include provider labels. Keep the original Haiku grades as separate history.
4. Export paired answers, source maps, missing-fact lists, scores, citation coverage and known
   logical generation tokens. Measure current Codex latency; historical per-question Claude
   latency is unavailable, so do not invent a speed comparison.
5. Inspect score disagreements, failures and grading-consistency flags before giving a
   qualitative conclusion. Same-model grading can favour Codex; differences in code and agent
   orchestration also prevent treating this as a controlled model-only ranking.

The historical Claude subset's original Haiku grades are 16 fully correct, 8 partial and
2 wrong/empty in scope. These are preparation data, not the planned common-grader comparison.

## Budget and execution status

**Live generation and common grading have not started.** Explicit token-budget confirmation
was requested because the project requires it above one million tokens.

Central estimate: **2,740,000 Codex subscription tokens**, with a planning range of **2–4 million**:

- 6 initially planned research calls at 100,000 tokens each;
- 20 initially planned single-pass calls at 30,000 each;
- up to 52 model grading calls at 20,000 each;
- 500,000 reserved for fallbacks, retries and estimate uncertainty.

The runner stops before a request that cannot fit its remaining estimated reserve. An individual
response can exceed the reserve; this is not an absolute per-response output-token limit.
Unknown call usage stops further calls for review. Normal model/evidence failures remain cached,
so retries cannot select improved answers. No new Claude quota is required for this plan.

The [runner](run_codex_claude_smoke.py) is dry-run by default. After approval and with the local
inference service ready at port 18001, `--live --budget 4000000` enables the planned run.
The [exporter](summarize_codex_claude_smoke.py) makes hash-checked JSON, CSV and a local side-by-side
HTML answer viewer without calling a model. A full-cohort report requires completed grading.
