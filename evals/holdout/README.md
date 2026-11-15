# Separately authored holdout intake

Personal project; not affiliated with an employer or supervisor. Not legal or regulatory advice.

**Status: out of scope at the user's request, 15 November 2026. No holdout questions have been created.**
The preparation below is retained for historical reference and is not an active task.
Codex has seen the development questions and fixes. Questions it authors in this chat would be
additional development tests, even with new wording, and must not be labelled independent.

## Author brief

Use only registered public EU credit-risk sources and the project's product scope. Draft about
20 questions across factual, application/scenario, comparison and scoped applicability tasks,
including some deliberate out-of-scope controls. Choose facts, assumptions and boundary cases
independently. Do not inspect the development questions, answer dumps, failure reports or
practitioner packets while authoring. A different practitioner should verify the references,
required facts, acceptable alternatives and optional context before sealing the set.

Use the fields documented in `evals/golden/README.md` with new IDs such as `holdout-001`, truthful
`author`, `status: verified` only after review, and explicit `grading_notes`. Reference source
versions and distinguish law, supervisory expectations and interpretation. Do not mark a
paraphrase of a known development case as an independent question.

## Seal and freeze

1. Complete the adjacent provenance template with real identities, dates, source versions,
   exposure disclosures and reference-review attestations. Keep the unexposed question JSONL
   outside the coding chat/workspace until authorship and review are complete.
2. Freeze the product revision and run plan before revealing questions to the implementer.
3. Run the existing overlap/freeze check locally:

   ```powershell
   .venv\Scripts\reglens.exe eval-freeze --input <independently-reviewed.jsonl> --role holdout
   ```

   The check rejects normalized exact question reuse from development and evaluation history.
   It cannot certify independent authorship or detect all semantic paraphrases; those need
   documented human review. Do not label a successful hash/overlap check proof of independence.
4. Record the frozen payload ID, file hash, provenance hash, code/config/corpus identity and a
   token estimate. Get approval if the planned live run exceeds the project threshold.
5. Score the sealed set once with the agreed protocol. Retain every failed attempt and all usage.
   Any subsequent product tuning on revealed questions converts those questions to development
   material. Future independent claims require a new, unexposed holdout.

No model calls, external outreach or practitioner decisions are part of preparing this intake.
