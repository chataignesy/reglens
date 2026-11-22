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
| 4 | ✅ Done. **Shared orchestration:** `answer.route.dispatch` is the one place for routing fallbacks, used by the app and the eval (on cached records); the retrieval gate is shared too. A failing fallback agent now keeps the single-pass answer. **D7:** every eval run writes `data/evals/runs/<id>.json` (artifact path + SHA-256, route plan, attempts, all tokens incl. router and failed attempts); `judge --run <id>` grades exactly that run and refuses changed artifacts. **F4:** answer caches are keyed by code, model, settings, corpus generation (chunks + edges) and question text; route caches by question text; judge verdicts by judge prompt/model, question, reference and answer text. **D6:** ranges need every member (partial credit), alternatives are OR-groups, document parts must match; a test keeps part-less golden citations unambiguous. All old caches are invalid now, so step 8 starts clean. `docs/review/deep_checks.py` probes the pre-fix code and is kept as a record. |
| 5 | ✅ Done. **D9:** failed and cancelled CLI calls are logged with an `outcome`; usage they did not report is `usage_known: false`, not zero; the agent's cost-cap path counts the failed call's tokens. **F8:** the API agent loop checks the budget before each request (a fifth reserved for the final answer); the final turn uses `tool_choice: none`; no request once the budget is spent. **F5:** per-request cancel token: providers check it before every call, the `claude -p` process is killed on cancel, disconnect detected by an async SSE stream; at most 2 questions at once (HTTP 429 beyond); `/api/ready` reports warm-up and database. Verified live: disconnect during drafting killed the process and logged a cancelled call. **D8:** a standalone MCP server has no process-wide cap; RegLens's per-question server keeps its 10 calls. |
| 6 | ✅ Done. **F6:** `gap.match.validate`: covered / partial / contradicted need an existing clause and a quote, otherwise *unassessed (invalid output)*; unknown statuses are no longer turned into *missing*; non-verbatim quotes are flagged `not_verbatim`. `reglens gap --rescore` re-validates a saved run with no LLM calls. The committed demo still finds 15/15 under the strict rules (0 invalid verdicts, 3 non-verbatim quotes flagged). **F9:** recall is over all planted gaps; `recall_of_assessed`, `gaps_assessed` and `complete` are reported; incomplete runs are flagged in both UIs. **F7:** runs are listed (`/api/gap/runs`) and chosen explicitly (`?run=`); default is the newest local run, else the demo; the demo is labelled; exports follow the chosen run. The tuning caveat and the precision sample sit next to the figure; *unassessed* status card; empty-filter message. The 3 un-cached register batches (≈ 22k tokens) and a re-match stay deferred to step 8. |
| 7 | ✅ Done. **Docs:** ROADMAP status (phases 2–4 done, 5 in progress), DESIGN tables and token totals (10.6M tokens, ≈ €19, 8 Nov 2026), Next.js removed from "not built yet". **Wording:** the API key goes from the browser via the local API to Anthropic (README, DESIGN, UI); lexical search is named Postgres `ts_rank`, not BM25. **Dates:** "Answered <date> from: <source versions>" instead of "As of". **Sources:** citation panels show the version and link to the official text (the exact consolidated CRR version on EUR-Lex). **Applicability:** SI/LSI works in every mode (gate, router path, single pass, agent search on both runtimes; the agent is told the type). **Accessibility:** named radio groups with arrow-key behaviour and one tab stop, `aria-expanded` on source panels, Retry when the API is unreachable (gap-page items done in step 6). **Hardening:** HTTPS-only downloads (CELLAR's http redirects upgraded on EU hosts, others refused), reused raw files re-hashed against the lock, self-hosted Geist fonts (`geist` package: the build needs no network). 5 tests; checked in the browser. |
| 8 | Planned below: re-measure (needs approval for tokens). |

### Step 8 plan (8 Nov 2026)

Every answer, route and verdict cache is invalid after steps 1–7 (code, corpus and question
fingerprints), so the numbers are measured afresh. Each run writes a manifest, and every
published figure will cite its run id.

Estimates use the ledger's recent averages: router 1.2k, quick answer 5.9k, agent answer about
48k incl. retries, judge 1.75k tokens. The current router sent 42 of 104 in-scope questions to
the agent.

| Stage | Command | Calls | Tokens |
|---|---|---|---|
| a. Retrieval eval | `reglens eval-retrieval` | none | 0 (done: recall@10 0.805) |
| b. Smoke: route + routed answers + judge, 30 questions (phase0) | `eval-route --set phase0 --yes`, `eval-answers --set phase0 --route --yes`, `judge --run <id> --yes` | ≈ 30 + 30 + 25 | ≈ 0.7M |
| c. Full routed run, remaining 90 questions (smoke answers reused) | same with `--set all` | ≈ 90 + 90 + 80 | ≈ 2.3M |
| d. Optional: single-pass baseline, all 120 (for the routed vs single comparison) | `eval-answers --set all --yes`, `judge` | 120 + 104 | ≈ 0.9M |
| **Total** | | | **≈ 3.0M (b+c), 3.9M with d** |

Order: run (b) and look at it before (c). Stop if the smoke run shows a new failure pattern
(for example many `partial_read` checks, unresolved citations or invalid outputs).

**Register and gap re-match:** deferred, not part of this step. Rebuilding the 3 un-cached
register batches is cheap (≈ 22k tokens), but obligation IDs are numbered sequentially, so
inserting new obligations renumbers the rest and would force a full gap re-match (≈ 0.4M
tokens). The committed register and gap results stay consistent with each other. Making IDs
stable (content-derived) comes first, then rebuild.

**Smoke result (b), run `20261108-151941-routed-phase0`, 8 Nov 2026:**
- **Quality:** correctness 0.90 on 25 in-scope questions (20 fully correct, 5 partly, 0 wrong); multi-hop 0.857; 5/5 out of scope declined; citation recall 0.867; mechanical checks passed 0.973. This is the same correctness as the 0.90 before the review fixes.
- **Cost:** 1.70M tokens (answers 1.65M, router 47k, judge 54k): about 2.5x the 0.7M estimate.
- **Why:** agent answers now average about 11 tool calls (4.5 before) and 60–180k tokens each (about 54k before), 87% of them cache reads. The steps 1 / R1 rules (paged articles, read before citing, snippets do not count as read) make the agent read more. More turns re-read the growing context.
- **Where it went:** 13 agent answers used 1.56M tokens and scored 0.885; 12 quick answers used 0.09M and scored 0.917.
- **Judge (R2):** flagged 4 verdicts to check by hand: pd-002, mh-002, mh-006, mh-007.
- **Full run (c):** at this rate the remaining 90 questions would cost about 4M tokens, not 2.3M.

**Decision (8 Nov 2026): step 8 stops at the smoke run.** The full re-measure (c, d) is not run. The 120-question figures in README / DESIGN / results docs predate the review fixes and are labelled so; the smoke run is the post-fix measurement. Open follow-ups:
- cut agent cost (batch calls in one turn, fewer re-reads, call cap 8), then re-measure;
- hand-check the 4 flagged judge verdicts;
- stable obligation IDs, then rebuild the register and re-match the gap analysis.

Afterwards: replace the headline numbers in README, DESIGN, ROADMAP and the results docs,
each citing its run id, and hand-check the judge verdicts flagged as inconsistent (R2).

### Additions from the runtime review

[RUNTIME-REVIEW-2026-11-08.md](RUNTIME-REVIEW-2026-11-08.md) measured the running system. Its
priorities 1 (cancellation) and 5 (concurrency cap, readiness) are done in step 5. Priority 6
(filtered vector recall) is done by `hnsw.ef_search = 400` and `iterative_scan`: the forced-HNSW,
ECB-only case that returned 2 of 30 rows now returns 30 of 30, matching the exact scan.

New items, to go before step 8 (they change answers or how they are graded):

| | Finding | Change |
|---|---|---|
| R1 | The agent stops early: mh-003 used 2 of 10 tool calls and said it had not read the passages it needed. | Before the final answer, code checks for truncated passages it relies on that were never read in full, and gives the agent one more turn to read them while budget remains. Otherwise the answer is marked incomplete. |
| R2 | The judge contradicts itself: pd-002 scored 2 while its rationale said "should be 1". | Flag verdicts whose score disagrees with their own missing facts or rationale. Keep the raw verdict, list the flags in the run report, and hand-check them. |
| R3 | Scope compliance gets mixed up with claim support. | A separate scope signal in reports and the UI: the answer declined, answered in scope, or answered an out-of-scope question with related material. |

**Status (R1–R3): ✅ done.**
- **R1:** the tool trace records passages delivered only as truncated snippets. Claims citing one fail the mechanical check as `partial_read`, and the answer reports `missing_info`. The API agent gets one completeness round, if calls, turns and budget remain, when its draft relies on such passages or reports a gap. The `claude -p` path cannot continue a finished session, so there it is flagged only. The agent JSON has `missing_info`.
- **R2:** `eval.judge.consistency_flags` (score versus missing facts, contradictions, or a different score named in the rationale). Raw verdicts are kept; `inconsistent_verdicts` is listed in the run summary and printed for a manual check.
- **R3:** eval rows carry `scope` (declined / answered / answered_out_of_scope / declined_in_scope) and `reports_incomplete`; the summary has `scope_compliance` and the list of incomplete answers, separate from the mechanical check pass rate and the judged correctness. The answer view shows Scope, Completeness and Mechanical checks as separate lines.

### Additions from the second review

[SECOND-REVIEW-2026-11-08.md](SECOND-REVIEW-2026-11-08.md) checked commit `86315c1` and found seven remaining defects. The plan was one small code fix per finding, each with a regression test built from the review's reproduction, in `tests/test_second_review.py`. None of the fixes needs an LLM call.

| | Finding | Change |
|---|---|---|
| S1 (P1) | A single delivered window authorised the whole passage. The paragraph-30 case delivered 978 chars and resolved 4,677. | The toolbox records the characters delivered per chunk (`last_chunks`), and every trace entry has `chunks`. `_resolve` builds context from that delivered text only, never from unseen windows. A unit counts as read only when every window was delivered whole; otherwise it is `partial_read`. The API agent's completeness nudge uses the same rule. Old traces without `chunks` keep the key-level check. |
| S2 | Tools started after a cancel that arrived during an SDK request. | The API loop checks for cancellation after each model return and before each tool. `Cancelled` propagates and is never turned into a tool error. The request that had already finished is still in the ledger. |
| S3 | Cancel killed `claude -p` but not its MCP child. | `cancel.kill_tree` kills by PID or process group, never by name: `taskkill /T /F` on Windows, `killpg` elsewhere. It runs on both cancel and timeout. The test kills a real parent and its child. |
| S4 | The corpus fingerprint ignored metadata (`applies_to`, `legal_level`, `version`, `kind`, …) and was memoised. | All answer-relevant chunk columns and `sources.yaml` are hashed. The memo is gone (~0.1 s per call). |
| S5 | Retrieval recall flattened alternative ranges. Retrieving para. 72 of 72–73 scored 1.0, versus 0.5 at answer level. | Retrieval uses the same `citations.groups`: OR over complete AND-groups, as answer-level credit does. The retrieval eval is unchanged (rerank recall@10 0.805, hit@10 0.913), so no reported number moves. |
| S6 | A run could be judged against a question that was edited under the same id. | `judge.plan` / `judge` reject a `question_sha` mismatch. For older manifests they check the answer record's question. The real smoke run still plans cleanly (25 cached, 5 deterministic, 0 problems). |
| S7 | `{"verdicts":[null]}` crashed the gap batch. | The collection and each entry are type-checked before any field is read. A clause given as a string is accepted; other clause types are invalid. Any malformed reply becomes `unassessed` / `invalid` and no longer aborts the run. |

Other items from the review, also fixed:
- **Converter version on cache reuse:** a Docling cache made by a different converter version is converted again. The 7 current caches were adopted before provenance was recorded, so they are reused with a warning; `parse --force` refreshes them.
- **Progress events as cancellation points:** the API's progress emitter raises `Cancelled` instead of silently dropping events, so single-pass steps stop there too. The CLI trace watcher exits quietly.

**Status (S1–S7 + these): ✅ done** (149 tests). Still open from the review:
- adjudicate the 4 flagged smoke verdicts (practitioner judgement);
- vector model revision pinning, which stays with the deferred roadmap items. The model *name* is already in the code hash.

The cache namespaces change with this code, so the next eval run produces fresh answers rather than reusing the smoke artifacts. The smoke manifest stays valid for `judge --run`.

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
