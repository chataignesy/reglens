# Completeness follow-up after the Codex–Claude comparison

Personal project; not affiliated with any employer or supervisor. Not legal or regulatory advice.

## What changed and why

The comparison showed that a grounded answer could still omit an important part of the question.
This change improves how RegLens selects evidence and recognizes required missing evidence.
It does not change the frozen questions, reference answers, historical answers or scores.

1. **Amendment questions can reach the amending act.** An explicit change question naming an
   amending instrument now includes its source alongside the ordinary default sources. Source aliases
   come from the registry. Ordinary CRR3 questions keep their existing source scope; an explicit
   caller restriction always wins. Agents retain the original question's source selection for tools.
2. **Small requested paragraph ranges are read together.** A request for paragraphs 1–3 anchored to
   one document part now brings in missing units before drafting. Source and part must be unambiguous;
   paragraph numbers elsewhere in the guide do not count. Full logical units are retained together.
   A source-bound question can still trigger a missing-read warning for an available requested unit.
3. **Child rules bring in parent qualifications.** When a parent paragraph explicitly mentions the
   retrieved point, RegLens reads its full windows. This recovers conditions and implementation
   exceptions that the main point does not repeat.
4. **Relevant parallel paragraphs are considered.** The first relevant article can contribute up to
   two sibling candidates with at least three literal content terms from the question in their bodies.
   This supplies the retail provision when a broad PD-history question initially retrieves the
   non-retail point. This is bounded lexical discovery, not a legal-scope classifier.
5. **Required definitions are checked against the corpus.** If the model reports a required missing
   quoted definition, a small exact lookup confirms whether it exists. Singular/plural variants are
   tried; available definition keys become focused research hints even if the model guessed that
   further research would not help. Optional checklist uncertainty alone does not trigger this lookup.

All contextual additions share a cap of **four extra rows and 12,000 characters**, including existing
proviso expansion. Caller source, institution, date and applicability filters are preserved. This
is evidence selection, not a deterministic legal answer or proof of completeness. Cache fingerprints
include the new helpers and the shared tools used by the single-pass path.

## Verification

- **247 tests passed**, including disposable Postgres integration tests; Ruff checks passed.
- Eight new regression tests cover source opt-ins, explicit restrictions, range anchoring, whole
  windows, shared budgets, parent qualifications, sibling provisions and required definitions.
- Read-only checks against the actual corpus verify the amendment provision, foreword range, both
  PD-history branches, the available corporate definition, and explicit source-filter exclusions.
- Seven warm repetitions per case measured median total bounded expansion of **16.00 ms** for PD
  history, **13.86 ms** for the amendment case, and **15.02 ms** for the foreword case. These timings
  include existing proviso expansion; they are local warm measurements, not a production latency test
  or an isolated before/after estimate of the new logic's cost.

The Codex subscription runs used unchanged frozen references and judge prompt `75d32dd9`:

| Question | First five-case follow-up | Later one-case check |
|---|---|---|
| `cmp-001`: provision changing corporate PD floor | Full credit; identifies Article 1(86)(a) | — |
| `app-001`: foreword paragraphs 1–3 | Full credit; includes supervisory consistency purpose | — |
| `mh-015`: EUR 300m corporate maturity option | Full credit through agent fallback; definition read | — |
| `pd-003`: PD historical observation period | Partial: corporate exception recovered, retail omitted | Full credit after sibling discovery; retail included |
| `oos-006`: unsupported calculation request | Correct deterministic refusal; zero generation tokens | — |

The first run scored **87.5% across its four in-scope questions**. The later run assessed only the
changed PD-history case and scored full credit. Do not combine these into a new overall benchmark:
they used different code revisions and intentionally selected known failures. The later PD-history
answer also passed all deterministic claim checks and achieved complete expected-citation recall.

**Usage:** 232,315 tokens for the first run plus 30,912 for the later check: **263,227 known new tokens**,
including grading and a rejected generation attempt. No unknown-usage calls were reported. This is
subscription token usage, not a monetary charge estimate.

## Limitations retained in the record

- The first maturity draft was rejected for unexpected native tool use in the text-only Codex
  transport. RegLens rejected that result and its existing agent fallback produced the successful
  answer. The failed attempt is preserved and its 44,545 tokens are counted. The successful fallback
  does **not** demonstrate that the new definition guard alone caused the improvement; real-SQL and
  regression checks verify that guard separately. Transport reliability remains a follow-up item.
- The amendment answer received full semantic credit but one claim had an
  `unsupported_number(160)` warning. Its cited child amendment contains the floor, while the amended
  article number is introduced in the enclosing amendment text. This remains a citation-support
  diagnostic to improve; semantic grading does not erase it. First-run mean mechanical pass rate
  was 87.5%, and expected-citation recall was 75%.
- A silent partial answer remains possible. Definition detection currently handles quoted required
  terms; range detection needs an existing unambiguous document-part anchor. Sibling discovery uses
  literal English terms and can miss paraphrases. Large units may exceed the reading allowance.
- `mh-003` (ordinary downturn LGD comparator) and `mh-012` (post-default additional drawings) from the
  30-case comparison were not re-evaluated here. This is not a claim that all comparison findings are
  closed. The general component-completeness problem still needs focused work.
- The suspected rubric overreach for `mh-006` and `mh-014` remains an adjudication task. Frozen
  references and scores have not been edited to improve reported performance.
- No fresh full 30-case comparison or 118-case evaluation was run. Automated scores remain
  **unreviewed by a practitioner**; an independent holdout is still needed before generalizing.

## Reproduction and evidence

- Runtime checks: `docs/review/check_completeness_runtime.py --output <new-path.json>`; requires the
  local database and inference service on port 18001. It makes no model calls and writes exclusively.
- Live harness: `docs/review/run_completeness_followup.py` is a dry run by default. `--live` runs the
  five cases; `--live --ids pd-003` runs just the PD-history case. It records source hashes, receipts,
  failed calls and manifests; preserves original artifacts; and stops before new requests when its
  budget reserve is reached or usage becomes unknown. A request can still exceed its estimate.
- [Final runtime checks](completeness-runtime-final-2026-11-13.json) and
  [initial runtime checks](completeness-runtime-2026-11-13.json).
- [Portable answer and score record](../results/completeness-followup-2026-11-13.json).
- First run: `20261113-230339-837169-routed-codex-completeness5`.
- Later PD check: `20261113-230624-237791-routed-codex-completeness5`.
- Earlier baseline: [completed 30-case comparison](../results/codex-claude-smoke30-2026-11-13.md).
