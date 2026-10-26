# RegLens — plan & roadmap

Project rules and budget policy: [../CLAUDE.md](../CLAUDE.md).

## Goal

Ship a public, open-source MVP that a credit risk modeller or validator can use to
(A) get cited answers on EU/ECB credit risk regulation and (B) run a gap analysis of a policy
against regulation — and publish **measured** evidence (benchmarks) of why the design works.

**Timeline assumption:** part-time (~8–10 h/week), start 2026-10-26, public launch early March 2027.
Dates are targets; phase exit criteria matter more than dates.

## Success metrics (MVP targets, calibrate after Phase 1)

| Area | Metric | Target |
|---|---|---|
| Retrieval | Recall@10 of the correct article(s) on golden set | ≥ 0.90 |
| Answers | Citation accuracy (cited paragraph supports the claim) | ≥ 95% |
| Answers | Faithfulness (LLM judge, spot-checked by hand) | ≥ 0.90 |
| Answers | Correct abstention on out-of-corpus questions | ≥ 90% |
| Gap analysis | Recall of planted gaps in the synthetic policy | ≥ 0.85 |
| Cost | Avg. cost per Q&A query (Sonnet tier) | ≤ $0.10 |
| Budget | Total MVP API spend | ≤ €150 (ceiling €250) |

## MVP corpus

| Source | Scope |
|---|---|
| CRR3 (consolidated Reg. 575/2013 as amended by 2024/1623) | Art. 4 definitions; Part Three Title II Ch. 2 (SA), Ch. 3 (IRB, Art. 142–191), Ch. 4 (CRM); Art. 92 output floor + transitional provisions |
| RTS | IRB assessment methodology (Del. Reg. 2022/439); materiality threshold of default (2018/171); economic downturn (2021/930) |
| EBA Guidelines | Definition of default (GL/2016/07); PD/LGD estimation (GL/2017/16); downturn LGD (GL/2019/03); CRM for A-IRB (GL/2020/05); loan origination & monitoring (GL/2020/06) |
| EBA Single Rulebook Q&A | Credit risk topics |
| ECB | Guide to internal models (latest revision); instructions for reporting validation results |

---

## Phase 0 — Foundations · 26 Oct – 8 Nov 2026 · budget €5

| Task | Owner |
|---|---|
| Git repo, `uv` project, ruff/pytest, `.gitignore`, `.env.example`, MIT licence, README with disclaimer | Claude |
| Config with model tiers; LLM provider interface; **cost ledger** (`data/ledger.jsonl`) + `reglens cost` CLI | Claude |
| `sources.yaml` source registry (URL, date, legal level, reuse note) for the MVP corpus | Claude + you |
| Download the corpus; **measure real token counts** per document | Claude |
| Golden-set schema (`question, expected_answer, expected_citations, applies_to, type`) + **first 30 questions** (incl. 5 out-of-scope) | **You** (domain expert) |
| Outline of the synthetic Model Validation Policy (sections only) | You + Claude |
| Check employment contract / inform employer about the side project | **You** |

**Exit:** corpus downloaded and counted; 30 golden questions; ledger records a test call.

## Phase 1 — Ingestion & retrieval · 9 – 29 Nov 2026 · budget €10

- Parser for EUR-Lex HTML/XML that keeps the legal structure (Part → Title → Chapter → Section → Article → paragraph → point); Docling for EBA/ECB PDFs.
- Chunking at article/paragraph level with full metadata and **deterministic hierarchy prefix**.
- Cross-reference extraction ("referred to in Article X") and Art. 4 definition links → edge table.
- Postgres + pgvector + full-text index; local embeddings (BGE-M3) and local reranker.
- Hybrid retrieval + reranker + metadata filters.
- **Retrieval-only eval** (recall@k, MRR) — no LLM cost. Compare: BM25 vs dense vs hybrid vs hybrid+rerank.
- Grow golden set to ~80 questions.

**Exit:** recall@10 ≥ 0.85 on golden set. **LinkedIn post 1:** "Why regulation breaks naive RAG" (+ first retrieval chart).

## Phase 2 — Grounded Q&A · 30 Nov – 20 Dec 2026 · budget €40

- Answer generation with paragraph-level citations, "as of" date, abstention, law / expectation / interpretation labels.
- Automatic citation verifier (cited text must support the claim).
- Eval harness: smoke set (30, Sonnet) + full set (Opus, milestone only); LLM judge via Batch API; hand spot-checks.
- Streamlit UI v0 with bring-your-own-key.
- Comparison of each component: naive RAG → hybrid → +rerank → +hierarchy prefix.
- Golden set to ~150 questions.

**Exit:** citation accuracy ≥ 90%, abstention ≥ 85%. **LinkedIn post 2:** the benchmark chart.

*Buffer: 21 Dec – 3 Jan (holidays).*

## Phase 3 — Agentic retrieval & MCP · 4 – 24 Jan 2027 · budget €45

- Tools: `search`, `get_article`, `follow_reference`, `get_definition`, `get_qa`.
- Bounded agent loop (max steps, task budget, logged usage), prompt caching verified.
- MCP server exposing the same tools.
- Comparison: pipeline Q&A vs agentic, on multi-hop questions (cross-references, definitions, Q&A).

**Exit:** agentic beats pipeline on multi-hop questions at ≤ $0.10/query (Sonnet). **LinkedIn post 3:** demo video incl. MCP in Claude.

## Phase 4 — Policy gap analysis · 25 Jan – 21 Feb 2027 · budget €40

- **Obligation register:** extract atomic requirements (ID, source paragraph, legal level, `applies_to`, topic) via Batch API; hand-review a sample.
- Write the **synthetic Model Validation Policy** with ~15 planted gaps (missing, partial, contradicted).
- Matching pipeline: split policy into clauses → retrieve candidate requirements → classify coverage with evidence quotes.
- Coverage matrix in the UI + export (xlsx/csv) with reviewer sign-off column.
- Gap-analysis eval: precision/recall on planted gaps.

**Exit:** planted-gap recall ≥ 0.85. **LinkedIn post 4:** flagship gap-analysis demo.

## Phase 5 — Polish & launch · 22 Feb – 7 Mar 2027 · budget €10

- README, architecture doc, published eval report, cost report from the ledger ("built for €X").
- Deploy Streamlit (BYOK) — e.g. Streamlit Community Cloud + hosted Postgres free tier.
- Recorded demo video (most visitors won't enter a key).
- **LinkedIn launch post** + repo public.

---

## Backlog (after MVP)

- Next.js UI
- DNB, then other national regulators
- Version switching over time (point-in-time answers, CRR2 vs CRR3 diff)
- Regulatory change monitoring ("what changed this month")
- More topics: IFRS 9 ECL expectations, COREP credit risk templates, stress testing

## Key risks

| Risk | Mitigation |
|---|---|
| Golden set takes longer than expected | Start in Phase 0; grow it gradually; it is also the most valuable asset |
| Budget overrun from eval runs | Tiered evals, ledger, €2 approval rule, Batch API |
| PDF parsing quality (EBA/ECB) | Docling + manual fixes for the ~10 key documents; prefer EUR-Lex HTML |
| Employer / IP concerns | Public sources, synthetic policy, built from scratch, disclaimer, early heads-up |
| Scope creep | Backlog list; MVP corpus fixed until launch |
