# Plan for the 8 November 2026 reviews

This plan responds to [REVIEW-2026-11-08.md](REVIEW-2026-11-08.md) (F1–F10) and
[DEEP-REVIEW-2026-11-08.md](DEEP-REVIEW-2026-11-08.md) (D1–D9).

**Checked on 2026-11-08:**
- All 12 probes in `docs/review/deep_checks.py` reproduce.
- F1 (`_lookup` resolves against the whole database), F6 (`ok = not quote or …`) and F8 (token
  limit checked only after a call) were confirmed by reading the code.

## Status

Work happens on branch `review-fixes`.

| Step | Status |
|---|---|
| 1 | ✅ Done. Also: "paragraph N" references inside articles became edges (+411). Retrieval recall@10 0.808 (103 questions). |
| 2 | ✅ Done. Answer contract in `answer/schema.py`: one retry for single-pass answers, none for the agent (a retry would re-run its tool loop); *unverified* state in API, web UI, Streamlit and CLI. The check is relabelled "mechanical citation checks", with its limits stated. |
| 3 | ✅ Done. **D1:** the Docling cache is keyed by PDF SHA-256 (`<id>.meta.json`, the 7 existing caches adopted, no re-conversion); `parse` skips a raw file that differs from `sources.lock.json`; `parse --force`; chunks carry `source_sha256`. **F3:** the extraction cache key covers prompt version, model, effort and passage text; `register/manifest.json` records source digests. 28 of 31 cached batches were adopted with identical text. 3 batches are uncached because step 1 moved passages: rebuilding the register is ≈ 22k tokens, deferred together with the gap re-match (step 6). |
| 4–8 | Open. |

## Principle

Most findings share one cause: **source identity and completeness are lost between stages**.
Parser, citation key, tool output, answer, metric and run record each lose part of the
information about what was read.

Fix that cause before tuning prompts or quoting new numbers. Each fix lands with a regression
test built from the review's reproduction. The fixes are code work and need **no LLM calls**.
Only step 8 re-measures with models, and it gets a token estimate and approval first.

## Steps

### 1. Evidence identity and completeness (P1): D2, D4, D3, F1, D5

| | Change | Test |
|---|---|---|
| D2 | Parser keeps the owning paragraph for unnumbered continuations after a point list. `get_definition` returns a definition together with its governing qualification (Art. 142(1)(5a) tail). | Fixture from the review; the real Art. 142 chunk |
| D4 | Citation keys and chunk identity include the section or numbering block for every PDF source with local numbering, not only sources that declare `parts`. Each key maps to exactly one logical unit (windows allowed). | Uniqueness test over all 4,631 chunks |
| D3 | `get_article`: stable order, `complete` flag, returned/total counts, an explicit truncation note and a continuation (`offset`). This applies to the 40-row limit and the 14,000-character cut. | Art. 124 and Art. 4 from real chunks |
| F1 | Final citations resolve only against passages actually delivered to the model. The toolbox records delivered chunk IDs; reference-only targets from `follow_reference` don't count as read. A cited key that wasn't delivered becomes an unresolved citation. | Unseen key, reference-only target, snippet, window |
| D5 | Self-reference guard compares article, paragraph and point, so Art. 178(1) → 178(3) is kept. | Review fixture |

Then re-parse and re-index. This is local, with no LLM calls; only changed chunks are
re-embedded. Retrieval eval follows (free).

### 2. Answer contract and honest verification (P1): F10, F2

- **F10:**
  - Typed schema validation of the answer JSON. One bounded retry on a parse or schema failure.
  - If it still fails, the answer has an explicit *unverified output* state, shown as such in
    the API and UI, never as an ordinary answer.
- **F2:**
  - Relabel the check as **"mechanical citation checks passed"** and list what it does not
    check (meaning, negation, conditions).
  - Same wording in README and DESIGN. The 0.99 figure is described as a mechanical pass rate.

### 3. Input provenance (P1): D1, F3

- **D1:** the Docling cache is keyed by PDF SHA-256 and converter version. The digest is stored
  in the chunks. `parse` refuses a conversion whose digest doesn't match `sources.lock`.
  `parse --force` is exposed.
- **F3:** the extraction cache key covers passage text, extraction prompt, model and settings.
  The register records source fingerprints.

### 4. Evaluation integrity (P1/P2): D6, F4, D7, shared orchestration

- **D6:** expected citations become structured: a range is AND (all members required),
  alternatives are OR, and part or section is kept. Golden references and cached records get the
  same identifiers.
- **F4:** caches are keyed by a fingerprint of:
  - question;
  - corpus/index generation;
  - prompt and relevant code (including `api_loop.py`);
  - model and settings.

  The judge cache covers question, candidate answer, reference and judge settings.
- **D7 + route duplication:**
  - One orchestration function (`answer_routed`) is used by CLI, API, Streamlit *and* the eval.
  - The eval writes a **run manifest**: per item, the answer artifact hash, route, fallback
    outcome and all tokens, including failed attempts.
  - `judge --run <id>` grades exactly that manifest.
  - Results docs link the run ID.

### 5. Limits, cancellation, accounting (P2): D9, F8, F5, D8

- **D9:** failed CLI calls still log reported usage, with an outcome field. Unknown usage is
  recorded as unknown, not zero.
- **F8:** the API loop checks the token budget *before* each request and reserves a final-answer
  allowance. After the stop, tool calls are refused and the answer is forced. Docs call the CLI
  cap a dollar cap.
- **F5:**
  - A cancellation event goes from the SSE disconnect through orchestration and is checked
    between tool and model calls. The `claude -p` subprocess is killed on cancel.
  - A small bounded executor (1–2 concurrent questions).
  - Separate liveness and readiness, with readiness reporting model warm-up failures.
- **D8:** the tool budget is per question, enforced by the agent runtime. A long-lived MCP
  process serves stateless tools; the per-run server for `claude -p` keeps its cap.

### 6. Gap analysis made conservative (P2): F6, F9, F7

- **F6:** *covered*, *partial* and *contradicted* require a valid clause and a matching quote.
  An invalid status or clause becomes *unassessed (invalid output)*, never *missing*.
- **F9:** report recall over all planted gaps, plus assessed coverage. A partial run is marked
  incomplete.
- **F7:** the run is chosen explicitly (`?run=`). A local run takes precedence over the demo,
  and the demo is clearly labelled when shown.
- **UI:** the tuning caveat and the precision sample sit next to the 15/15 figure.

### 7. Docs, wording and UX (P3)

- **Docs drift:**
  - ROADMAP status summary;
  - DESIGN still listing Next.js as unbuilt;
  - usage totals consistent across files;
  - claims dated and linked to run IDs.
- **API key wording:** keys go from the browser to the local RegLens API, then to Anthropic.
- **Dates:** "answer generated on" is shown separately from "corpus snapshot / source versions".
- **Retrieval naming:** call it `ts_rank` lexical retrieval, not BM25.
- **Citation panels:** official source URL and version.
- **Applicability:** the SI/LSI filter works in all modes, including agent tools.
- **Accessibility:** radio-group keyboard behaviour, `aria-expanded`, labelled gap search,
  retry for an unreachable API, empty-filter state, *unassessed* status card.
- **Build and download:** self-hosted fonts; the download entry point uses HTTPS and checks
  redirects; reused raw files are re-hashed.

### 8. Re-establish the numbers (LLM cost: ask first)

Steps 1, 2 and 4 change chunk identity, prompts and metrics, so every published score must be
re-measured from a run manifest.

1. Retrieval eval on all 120 questions. Free.
2. Smoke set, 30 questions on Sonnet: ≈ 0.7M tokens.
3. Full routed run plus judging, 120 questions: ≈ 3M tokens.

Step 3 is above the 1M threshold, so it needs explicit approval. The headline numbers in
README, DESIGN and the results docs are replaced from that manifest.

## Deferred (after the MVP, recorded in ROADMAP)

- Staged corpus generations with a promotion pointer and rollback.
- Effective-date intervals and point-in-time reasoning.
- Pinned embedding/reranker revisions stored with the vectors (cheap: could move into step 3).
- Reranker truncation measurement on long provisions.
- Prompt-injection tests on source and policy text.
- Checking that displayed prose matches the claim list.
- Semantic citation-support evaluation.
- Frozen holdout set.
- Untouched second synthetic policy.
- Independently labelled precision sample.

## Order and size

| Step | Findings | Effort | LLM tokens |
|---|---|---|---|
| 1 | D2 D4 D3 F1 D5 | large | 0 (re-index local) |
| 2 | F10 F2 | medium | 0 |
| 3 | D1 F3 | small | 0 |
| 4 | D6 F4 D7 | large | 0 |
| 5 | D9 F8 F5 D8 | medium | 0 |
| 6 | F6 F9 F7 | small | 0 |
| 7 | docs / UX | medium | 0 |
| 8 | re-measure | — | ≈ 0.7M smoke + ≈ 3M full |

Steps 1–4 come before the demo video, because the video shows citations and verification.
Steps 5–7 can follow. Step 8 is the last thing before the launch post.
