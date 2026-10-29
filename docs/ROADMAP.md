# RegLens — plan & roadmap

Project rules and budget policy: [../CLAUDE.md](../CLAUDE.md). Last updated: 2026-10-27.

## Goal

Ship a public, open-source MVP that a credit risk modeller or validator can use to
(A) get cited answers on EU/ECB credit risk regulation and (B) run a gap analysis of a policy
against regulation — and publish **measured** evidence (benchmarks) of why the design works.

**Timeline assumption:** part-time (~8–10 h/week), start 2026-10-26, public launch early March 2027.
Dates are targets; phase exit criteria matter more than dates.

**Budget:** development runs on a Claude subscription, so usage is tracked in **tokens**
(`reglens usage`). Phase budgets are in **API-equivalent EUR** as a yardstick (target €150, ceiling
€250 for the MVP); any single run above 1M tokens needs approval first.

## Status at a glance

| Phase | Dates | Status |
|---|---|---|
| 0 — Foundations | 26 Oct – 8 Nov 2026 | ✅ Done |
| 1 — Ingestion & retrieval | 9 – 29 Nov 2026 | ✅ Done early (27 Oct) — single-answer recall@10 0.89 on 80 questions; see [results](results/retrieval-phase1.md) |
| 2 — Grounded Q&A | 30 Nov – 20 Dec 2026 | **In progress** (started early) — pipeline, verifier and smoke eval done; see [results](results/answers-phase2.md) |
| 3 — Agentic retrieval & MCP | 4 – 24 Jan 2027 | Not started |
| 4 — Policy gap analysis | 25 Jan – 21 Feb 2027 | Not started |
| 5 — Polish & launch | 22 Feb – 7 Mar 2027 | Not started |

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
- ✅ LLM judge (`reglens judge`, Haiku, cached, deterministic where possible): correctness **0.83** single-answer, **0.43** multi-hop, 14/25 fully correct; 39k tokens. Spot-check: reliable on facts, strict on framing ([results](results/answers-phase2.md))
- ⏳ Golden reference fix for `moc-001` (and possibly `app-001`); then Phase 3 (agentic multi-hop retrieval)

*Buffer: 21 Dec – 3 Jan (holidays).*

## Phase 3 — Agentic retrieval & MCP · 4 – 24 Jan 2027 · €45

- Tools: `search`, `get_article`, `follow_reference`, `get_definition`, `get_qa`.
- Bounded agent loop (max steps, token cap, logged usage), prompt caching verified.
- MCP server exposing the same tools.
- Comparison: pipeline Q&A vs agentic, on multi-hop questions (cross-references, definitions, Q&A).

**Exit:** agentic beats pipeline on multi-hop questions at ≤ 50k tokens/query (Sonnet). **LinkedIn post 3:** demo video incl. MCP in Claude.

## Phase 4 — Policy gap analysis · 25 Jan – 21 Feb 2027 · €40

- **Obligation register:** extract atomic requirements (ID, source paragraph, legal level, `applies_to`, topic); hand-review a sample.
- Write the **synthetic Model Validation Policy** with ~15 planted gaps (missing, partial, contradicted).
- Matching pipeline: split policy into clauses → retrieve candidate requirements → classify coverage with evidence quotes.
- Coverage matrix in the UI + export (xlsx/csv) with reviewer sign-off column.
- Gap-analysis eval: precision/recall on planted gaps.

**Exit:** planted-gap recall ≥ 0.85. **LinkedIn post 4:** flagship gap-analysis demo.

## Phase 5 — Polish & launch · 22 Feb – 7 Mar 2027 · €10

- README, architecture doc, published eval report, usage report from the ledger ("built on X tokens").
- Deploy Streamlit (BYOK) — e.g. Streamlit Community Cloud + hosted Postgres free tier.
- Recorded demo video (most visitors won't enter a key).
- Make the GitHub repo public (after the employer check); consider a noreply commit email.
- **LinkedIn launch post.**

---

## Backlog (after MVP)

- Next.js UI
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
