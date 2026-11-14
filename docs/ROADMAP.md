# RegLens — plan & roadmap

Architecture update (11 November 2026): staged corpus publication, explicit legal constraints,
shared inference and frozen evaluations are implemented. See [implementation steps](ARCHITECTURE-IMPLEMENTATION.md)
and [operation and remaining limits](ARCHITECTURE-OPERATIONS.md).

Project rules and budget policy: [../CLAUDE.md](../CLAUDE.md). Last updated: 2026-11-14.
Next-session entry point: [HANDOFF.md](HANDOFF.md).

## Goal

Ship a public, open-source MVP that a credit risk modeller or validator can use to
(A) get cited answers on EU/ECB credit risk regulation and (B) run a gap analysis of a policy
against regulation — and publish **measured** evidence (benchmarks) of why the design works.

**Timeline assumption:** part-time (~8–10 h/week), start 2026-10-26, public launch early March 2027.
Dates are targets; phase exit criteria matter more than dates.

**Budget:** development supports Claude subscription access and opt-in Codex subscription access,
so usage is tracked in **tokens**
(`reglens usage`). Phase budgets are in **API-equivalent EUR** as a yardstick (target €150, ceiling
€250 for the MVP); any single run above 1M tokens needs approval first.

## Status at a glance

| Phase | Dates | Status |
|---|---|---|
| 0 — Foundations | 26 Oct – 8 Nov 2026 | ✅ Done |
| 1 — Ingestion & retrieval | 9 – 29 Nov 2026 | ✅ Done early (27 Oct) — single-answer recall@10 0.89 on 80 questions; see [results](results/retrieval-phase1.md) |
| 2 — Grounded Q&A | 30 Nov – 20 Dec 2026 | ✅ Done early — pipeline, verifier, LLM judge ([results](results/answers-phase2.md)) |
| 3 — Agentic retrieval & MCP | 4 – 24 Jan 2027 | ✅ Done early — router, bounded agent, MCP server; routed correctness 0.89 on 104 in-scope questions ([results](results/golden-120.md)) |
| 4 — Policy gap analysis | 25 Jan – 21 Feb 2027 | ✅ Done early — register, synthetic policy, 15/15 planted gaps (tuned; [results](results/gap-phase4.md)) |
| 5 — Polish & launch | 22 Feb – 7 Mar 2027 | **In progress** — UI and architecture foundations implemented; full118, focused8 and precision2 evaluations complete; wider quality, cost and independent verification remain |

## Current priority — Q&A completeness (14 November 2026)

The latest [full Codex benchmark](results/codex-frozen118-2026-11-14.md) measured **86.4% mean score**
across 103 in-scope questions: 76 full, 26 partial, one wrong/unanswered. All 15 out-of-scope
requests were refused. Full-credit rate is 73.8%; the mean awards partial credit. Mechanical checks
averaged 99.0%, but 22 of the 26 graded partial answers reported no gap. The set is reviewed
development material, and the grades remain automated, without practitioner sign-off.

The foundation milestone is implemented; the following product-quality work is still open:

| Order | Work | Status / evidence | Acceptance direction |
|---|---|---|---|
| 1 | Required scope/addressee retrieval and escalation | **Implemented and exercised live**; `app-004` improves from zero to full credit in one pass | Caller constraints and missing-user-input controls pass locally; evidence remains development-set only |
| 2 | Coverage of conditions, components and exceptions | **Implemented bounded signals**, including source-linked conditions and context-only rewrites; discovery alone does not force research | Demonstrated cure/economic-loss issues resolved in [precision2](results/codex-coverage-precision2-2026-11-14.md); broader completeness remains unproven |
| 3 | Targeted verification of 1–2 | **Complete**: 267 tests; focused8 seven full / one partial (582,354 tokens); subsequent precision2 two full / no gaps (109,121 tokens) | Precision2 answer/routing usage falls 40.2% for that pair; no claim of a new full or eight-case score on the latest revision |
| 4 | Enclosing amendment introductions in citations | Queued; `cmp-001` retains `unsupported_number(160)` despite full semantic credit | Deliver and cite the context needed to support the amended article number |
| 5 | Routing efficiency | Later; 24.5% of known full-run tokens went to routing | Compare cost and quality on a fixed cohort after coverage behaviour is reliable |
| Parallel review track | Rubric adjudication and independent holdout | Practitioner review pending for `mh-006` / `mh-014`; no independent holdout yet | Preserve original references/scores; create explicit adjudications and separately authored holdout questions |

Use [the handoff](HANDOFF.md) for saved artifacts, code entry points and verification constraints.
The demonstrated cure-condition omission and economic-loss over-research are resolved in the
two-case follow-up. Broader verification and the queued citation/routing/holdout work remain.
A later full rerun should use a fresh run identity after focused checks
justify it. Existing frozen references, historical answers and scores remain immutable.

The completed run's 8-million-token approval does not authorise a new evaluation. Estimate new
model calls and obtain confirmation when the project threshold requires it. Phase history and
older measurements below retain their original dates; they are not current quality guarantees.

## Success metrics (MVP targets, calibrate after Phase 1)

| Area | Metric | Target |
|---|---|---|
| Retrieval | Recall@10 of the correct article(s) on golden set | ≥ 0.90 |
| Answers | Citation accuracy (cited paragraph supports the claim) | ≥ 95% |
| Answers | Faithfulness (LLM judge, spot-checked by hand) | ≥ 0.90 |
| Answers | Correct abstention on out-of-corpus questions | ≥ 90% |
| Gap analysis | Recall of planted gaps in the synthetic policy | ≥ 0.85 |
| Efficiency | Avg. tokens per Q&A query (Sonnet tier) | ≤ 50k |
| Budget | Total MVP usage (API-equivalent) | ≤ €150 (ceiling €250) |

## MVP corpus

Status per source is in [sources.yaml](../sources.yaml); exact versions and checksums in
[sources.lock.json](../sources.lock.json).

| Source | Scope | Status |
|---|---|---|
| CRR consolidated (02013R0575-20260626) | Art. 4; Art. 92 + output floor transitional rules; Part Three Title II Ch. 2–4 | ✅ downloaded |
| CRR3 amending act (2024/1623) | Recitals, application dates (change tracking) | ✅ downloaded |
| RTS 2022/439 (IRB assessment), 2018/171 (default materiality), 2021/930 (downturn) | Full | ✅ downloaded |
| EBA GL/2016/07, GL/2017/16, GL/2019/03, GL/2020/05, GL/2020/06 | Full (LOM: credit-risk sections) | ✅ downloaded |
| ECB guide to internal models, **June 2026** | General topics + credit risk chapters | ✅ downloaded |
| ECB validation reporting instructions, **Feb 2019** | Full — pre-CRR3, check for an update | ✅ downloaded |
| EBA Single Rulebook Q&A (credit risk) | 243 final Q&As (CRR, topic Credit risk) | ✅ crawled |

**Size:** ~1.76M tokens as full documents at a calibrated 3.01 chars/token (legal text is ~33% denser
than the usual 4). The MVP working set is a subset — mainly the CRR and ECB guide are trimmed to
credit-risk scope in Phase 1.

**Note:** EUR-Lex has already published a consolidated CRR dated 2027-01-01. The default is the
version in force on the as-of date; `reglens download --as-of 2027-01-01` fetches the next one.

---

## Phase 0 — Foundations · 26 Oct – 8 Nov 2026 · €5

| Task | Owner | Status |
|---|---|---|
| Git repo, `uv` project, ruff/pytest, `.gitignore`, `.env.example`, MIT licence, README + disclaimer | Claude | ✅ |
| Private GitHub repo `MistVista/reglens` (public at launch) | Claude | ✅ |
| Config with model tiers (Haiku / Sonnet / Opus) | Claude | ✅ |
| Usage ledger (`data/ledger.jsonl`), `reglens usage` / `estimate` — token-first | Claude | ✅ |
| LLM provider layer: `claude -p` on the subscription; API provider deferred to Phase 2 | Claude | ✅ |
| `sources.yaml` registry; downloader (EUR-Lex via CELLAR API, EBA/ECB by URL) + lock file | Claude | ✅ |
| Measure token counts; calibrate chars/token | Claude | ✅ |
| Golden-set schema, validator (`reglens golden`), field guide, 3 draft examples | Claude | ✅ |
| **First 30 golden questions** (incl. ≥ 5 out-of-scope), all verified | **You** + Claude | ✅ |
| Outline of the synthetic Model Validation Policy ([outline](synthetic-policy/outline.md)) — your review pending | You + Claude | ✅ |
| Check employment contract / inform employer about the side project | **You** | ✅ |

**Exit:** corpus downloaded and counted ✅; 30 golden questions ✅; ledger records a test call ✅.

## Phase 1 — Ingestion & retrieval · 9 – 29 Nov 2026 · €10

- Parser for EUR-Lex XHTML that keeps the legal structure (Part → Title → Chapter → Section → Article → paragraph → point); Docling for EBA/ECB PDFs.
- Trim to MVP scope (CRR credit-risk parts, ECB guide credit chapters).
- EBA Q&A extraction for credit-risk articles.
- Chunking at article/paragraph level with full metadata and **deterministic hierarchy prefix**.
- Cross-reference extraction ("referred to in Article X") and Art. 4 definition links → edge table.
- Postgres + pgvector + full-text index; local embeddings (BGE-M3) and local reranker.
- Hybrid retrieval + reranker + metadata filters.
- **Retrieval-only eval** (recall@k, MRR) — no LLM tokens. Compare: BM25 vs dense vs hybrid vs hybrid+rerank.
- Grow golden set to ~80 questions.

**Exit:** recall@10 ≥ 0.85 on golden set. **LinkedIn post 1:** "Why regulation breaks naive RAG" (+ first retrieval chart).

**Status (2026-10-27):**
- ✅ EUR-Lex XHTML parser (hierarchy, paragraphs, points, recitals, amending acts); Docling PDF parser (numbering blocks, background vs operative text, sections); MVP scope filters
- ✅ Chunking with hierarchy prefix; cross-reference, amendment and definition edges (7.9k)
- ✅ Postgres + pgvector (Docker), BGE-M3 embeddings, bge-reranker-v2-m3; `reglens search`
- ✅ EBA Q&A: 243 final credit-risk Q&As crawled politely (robots.txt crawl-delay), linked to CRR articles; excluded from default search
- ✅ Golden set: accepted alternative citations (schema field `alternatives`)
- ✅ Golden set: 80 verified questions (30 Phase 0 + 50 Phase 1), checked in source text and reviewed
- ✅ Retrieval eval on 69 evaluable questions: reranked hybrid recall@10 **0.79** overall, **0.89** single-answer (target met), 0.31 multi-hop ([results](results/retrieval-phase1.md))
- Carry-overs: ECB guide paragraph refs are not unique across parts (refs should name the part); query rewriting for practitioner terms ("F-IRB", "LGD in-default") → Phase 2

## Phase 2 — Grounded Q&A · 30 Nov – 20 Dec 2026 · €40

- Answer generation with paragraph-level citations, "as of" date, abstention, law / expectation / interpretation labels.
- Automatic citation verifier (cited text must support the claim).
- Eval harness: smoke set (30, Sonnet) + full set (Opus, milestone only); LLM judge; hand spot-checks.
- Anthropic API provider for the bring-your-own-key demo; verify Haiku 5.5 list prices first.
- Streamlit UI v0 with bring-your-own-key.
- Comparison of each component: naive RAG → hybrid → +rerank → +hierarchy prefix.
- Golden set to ~150 questions.

**Exit:** citation accuracy ≥ 90%, abstention ≥ 85%. **LinkedIn post 2:** the benchmark chart.

**Status (2026-10-28):**
- ✅ Answer pipeline (`reglens ask`): numbered passages, JSON claims with citations and law / supervisory / interpretation labels; as-of line and legal levels set by code
- ✅ Two-layer abstention: retrieval gate (no LLM call below rerank score 0.05) + scope statement in the prompt
- ✅ Deterministic citation verifier (citations exist, numbers supported, "law" cites CRR/RTS)
- ✅ Answer eval (`reglens eval-answers`, dry run by default, cached): smoke run on 30 questions — out-of-scope abstention 5/5, claims passing the check 0.98, citation recall 0.78 single-answer / 0.18 multi-hop, 163k tokens ([results](results/answers-phase2.md))
- ✅ Glossary query expansion (practitioner terms → legal wording): retrieval recall@10 0.79 → **0.81**, single-answer 0.89 → **0.92**
- ✅ Prompt: bounded partial answers instead of abstaining; missing information in the text, not as claims (not yet re-measured)
- ✅ Anthropic API provider (official SDK, BYOK key never logged, server-side fallback, refusal handling; tested with a fake client)
- ✅ Streamlit UI v0 (`streamlit run src/reglens/ui/app.py`): disclaimer, BYOK or local subscription, sources with legal level, citation check; end-to-end test answer 7.6k tokens
- ✅ Smoke re-run (new prompt + expansion + ECB release table in scope): in-scope answered 25/25, out-of-scope declined 5/5, claims passing the check 0.99; citation recall unchanged (0.75 single / 0.18 multi-hop) ([results](results/answers-phase2.md))
- ✅ LLM judge (`reglens judge`, Haiku, cached, deterministic where possible): correctness **0.92** single-answer, **0.43** multi-hop, 16/25 fully correct; 42k tokens. Spot-check: reliable on facts, strict on framing; two golden references corrected ([results](results/answers-phase2.md))
- ⏳ Phase 3 (agentic multi-hop retrieval) is the next lever

*Buffer: 21 Dec – 3 Jan (holidays).*

## Phase 3 — Agentic retrieval & MCP · 4 – 24 Jan 2027 · €45

- Tools: `search`, `get_article`, `follow_reference`, `get_definition`, `get_qa`.
- Bounded agent loop (max steps, token cap, logged usage), prompt caching verified.
- MCP server exposing the same tools.
- Comparison: pipeline Q&A vs agentic, on multi-hop questions (cross-references, definitions, Q&A).

**Exit:** agentic beats pipeline on multi-hop questions at ≤ 50k tokens/query (Sonnet). **LinkedIn post 3:** demo video incl. MCP in Claude.

**Status (2026-10-29):**
- ✅ Tools (`search`, `get_article`, `follow_reference`, `get_definition`, `get_qa`) with citation keys; ECB keys name the part
- ✅ RegLens MCP server (stdio) and bounded agent (`reglens ask --agent`): tool-call budget + cost cap
- ✅ Multi-hop smoke (7): correctness **0.43 → 0.71**, citation recall **0.18 → 0.72**, no wrong answers; **~63k tokens/question** (above the 50k target)
- ✅ Stopping rule (check the legal basis first) and tool-call traces; mh-003 now fully correct
- ✅ Haiku router (accuracy 0.81, multi-hop recall 0.79): smoke correctness **0.78 → 0.86**, multi-hop **0.43 → 0.86**, citation recall 0.62 → 0.82; 685k vs 147k tokens on 25 questions
- ✅ Search snippets + `get_passage` for full text: routed smoke correctness **0.90** (single-pass 0.78), 482k tokens for the 12 agent questions; a 4,000-char cap alone made the agent stop early (multi-hop 0.64 on two runs)
- ✅ API agent loop for the BYOK demo: RegLens runs the tool loop on the Messages API with hard limits (10 tool calls, 13 turns, 200k tokens per question); UI modes Auto / Quick / Deep
- Decision: quality over the 50k tokens/query target (multi-hop averages ~65k)
- ✅ **Milestone eval, full golden set (80):** routed correctness **0.88** vs 0.81 single-pass (multi-hop 0.67 vs 0.46), 3 wrong of 70, citation recall 0.85, all claims pass the check; 9/10 out-of-scope declined ([results](results/golden-phase3.md))
- ✅ Four fixes (glossary + expanded reranker query, agent fallback on `missing_info`, scope rule; stricter router tested and reverted): routed **0.91**, single-pass 0.86, **no wrong answers**, 10/10 out-of-scope declined, citation recall 0.90; retrieval recall@10 0.84

## Phase 4 — Policy gap analysis · 25 Jan – 21 Feb 2027 · €40

- **Obligation register:** extract atomic requirements (ID, source paragraph, legal level, `applies_to`, topic); hand-review a sample.
- Write the **synthetic Model Validation Policy** with ~15 planted gaps (missing, partial, contradicted).
- Matching pipeline: split policy into clauses → retrieve candidate requirements → classify coverage with evidence quotes.
- Coverage matrix in the UI + export (xlsx/csv) with reviewer sign-off column.
- Gap-analysis eval: precision/recall on planted gaps.

**Exit:** planted-gap recall ≥ 0.85. **LinkedIn post 4:** flagship gap-analysis demo.

**Status (2026-11-01):**
- ✅ Obligation register: 752 atomic obligations (720 validation-relevant) from 322 passages, Sonnet extraction, 746/752 quotes verbatim ([register](../register/obligations.jsonl))
- ✅ Synthetic Model Validation Policy (53 clauses) with 15 planted gaps (5 missing, 5 partial, 5 contradicted) and answer key
- ✅ Matcher: whole policy per call, one verdict per obligation with clause + verified quote; statuses incl. *not applicable* and *belongs in another document*
- ✅ **Planted-gap recall 15/15, type accuracy 1.00** (after one prompt revision on the same gaps; tuning caveat); sample precision: 20/20 factually correct, ≈ 11/20 belong in a validation policy ([results](results/gap-phase4.md))
- ✅ UI tab: coverage matrix with filters, planted-gap view, CSV/Excel export with reviewer columns
- ⏳ Clean recall test on a second synthetic policy; precision calibration on reviewer-labelled findings
- Note: Phase 4 tokens up to 2026-11-01 were logged under phase 3 (`current_phase` not yet switched)

## Phase 5 — Polish & launch · 22 Feb – 7 Mar 2027 · €10

- **Priority (2026-11-04):** the demo is about the Q&A — visitors asking questions and checking the answers. The gap analysis stays as a secondary showcase.
- ✅ Next.js UI (`web/`) over a FastAPI backend: live research progress (each agent tool call streamed), citation badges that open their sources, gap-analysis page with filters and exports; Streamlit kept as fallback
- ✅ Golden set extended to **120 verified questions** (`phase2.jsonl`, 40 new, weighted to weak spots: 11 multi-hop, 8 comparison/applicability, 15 factual on downturn LGD, IRB parameters, CCF, CRM, MoC, validation, 6 near-miss out-of-scope); every reference checked in the source text, flagged items reviewed; retrieval recall@10 on the new in-scope items 0.76 (vs 0.84 on the earlier set)
- ✅ Eval on the 40 new questions: routed correctness **0.87** vs 0.72 single-pass (multi-hop 0.86 vs 0.59), **no wrong answers** (5 single-pass), citation recall 0.88; 5/6 near-miss out-of-scope declined. All 120: **0.89**, 82 / 22 / 0, 15/16 declined ([results](results/golden-120.md)). Fixed: agent MCP tools hidden by CLI tool search, graceful cost cap, JSON control characters
- README, architecture doc (draft: [DESIGN.md](DESIGN.md)), published eval report, usage report from the ledger ("built on X tokens").
- ~~Deploy Streamlit (BYOK)~~ — dropped 2026-11-04: the two local models (~2 GB each) need more memory than free tiers give, Hugging Face Docker Spaces now need a paid plan, and Spaces block outbound Postgres ports. Demo is a video instead.
- **Recorded demo video** (script: [docs/demo/video-script.md](demo/video-script.md)); visitors can run it locally.
- ✅ README *Start the web UI*: database (Docker), API (`uvicorn`, port 8000, models warm at startup), Next.js (`npm run dev`, port 3000); subscription or own API key
- Make the GitHub repo public (after the employer check); consider a noreply commit email.
- **LinkedIn launch post.**

---

## Backlog (after MVP)

- DNB, then other national regulators
- Version switching over time (point-in-time answers, CRR2 vs CRR3 diff; the 2027-01-01 CRR version)
- Regulatory change monitoring ("what changed this month")
- More topics: IFRS 9 ECL expectations, COREP credit risk templates, stress testing

## Key risks

| Risk | Mitigation |
|---|---|
| Golden set takes longer than expected | Start in Phase 0; grow it gradually; it is also the most valuable asset |
| Subscription usage limits hit by eval runs | Tiered evals, token ledger, 1M-token approval rule, retrieval-only evals first |
| PDF parsing quality (EBA/ECB) | Docling + manual fixes for the ~10 key documents; prefer EUR-Lex XHTML |
| Source access breaks (EUR-Lex bot challenge, site moves) | CELLAR API for EUR-Lex; URLs and checksums pinned in the lock file |
| Outdated sources (e.g. 2019 ECB validation instructions) | `verify` flags in sources.yaml; check for updates before each milestone |
| Employer / IP concerns | Public sources, synthetic policy, built from scratch, disclaimer, early heads-up |
| Scope creep | Backlog list; MVP corpus fixed until launch |
