# RegLens — design choices

RegLens answers questions about EU credit risk regulation (CRR3, RTS, EBA guidelines and Q&A,
ECB guide to internal models) with paragraph-level citations. This document records each design
choice, what it replaced, the tools used and — where we measured it — the evidence.

> Personal project. Not affiliated with any employer or supervisor. Not legal or regulatory advice.

## At a glance: a basic RAG vs RegLens

A "basic RAG" here means the common tutorial pipeline: split PDFs into fixed-size chunks, embed
them, take the top-k by cosine similarity, and ask an LLM to answer from them.

| Layer | Basic RAG | RegLens | Evidence |
|---|---|---|---|
| Sources | PDFs scraped from websites | Official EU publications API (CELLAR + SPARQL) for law, consolidated version in force on the as-of date; Docling for EBA/ECB PDFs; every source registered with URL, date, legal level, licence | 13 sources, 4,631 chunks |
| Chunking | Fixed 500-token windows | Structure-aware: Part › Title › Chapter › Article › paragraph › point, with a deterministic hierarchy prefix on every chunk | — |
| Metadata | None | Legal level (law / supervisory / Q&A), version, `applies_to` (SI / LSI), amending act | Answers label each claim |
| Links between texts | None | Cross-reference graph: 10,274 edges (`refers_to`, `amends`, `uses_definition`, `answers_on`) | Used by the agent |
| Retrieval | Dense top-k | Hybrid BM25 + dense (RRF) → cross-encoder reranker → practitioner glossary expansion | recall@10 0.59 (BM25) / 0.74 (dense) → **0.84** |
| Grounding | "Answer from the context" | JSON claims, each citing passages; a deterministic checker verifies citations and numbers; abstention gate; "as of" line built by code | **0.99** of claims pass the check; 5/5 out-of-scope questions declined |
| Multi-step questions | Same single pass | Router → bounded agent with 6 corpus tools over the graph, agent fallback when a quick answer has gaps; runs on the Messages API or as an MCP server | Correctness 0.86 → **0.91**, no wrong answers (70 questions) |
| Evaluation | Eyeballing answers | 80-question expert golden set, retrieval metrics, deterministic citation metrics, LLM judge, router eval, repeat runs for variance | — |
| Cost | Unknown | Token ledger on every call, model tiers, prompt caching, estimates before every run | 3.1M tokens, ≈ €3.6 API-equivalent so far |

## 1. Sources and ingestion

**1.1 Official APIs, not scraping.** Law (CRR, RTS) comes from the EU Publications Office
**CELLAR** REST API, with **SPARQL** queries to find the consolidated version in force on the
as-of date (CRR `02013R0575-20260626`). The EUR-Lex website is behind a bot challenge; we use the
official machine interface instead of working around it.
*Tools:* `urllib` + `truststore` (OS certificate store; TLS verification never disabled),
SPARQL endpoint, `sources.lock.json` with SHA-256 per file.

**1.2 Structured HTML over PDF for law.** Consolidated XHTML keeps article, paragraph and point
structure explicitly, so we parse that instead of extracting text from PDFs.
*Tools:* BeautifulSoup + lxml, with handling for consolidated-text quirks (unnumbered paragraphs,
grid lists, nested points such as "(86)(a)").

**1.3 Layout-aware PDF conversion for guidance.** EBA guidelines and the ECB guide are PDFs only;
**Docling** converts them to Markdown with headings and tables intact, and the parser maps
numbered paragraphs and sections. Background and rationale sections are kept but excluded from
default search, so operative text wins.

**1.4 EBA Q&A via a polite crawler.** 243 final credit-risk Q&As, crawled within robots.txt
(10 s delay, disallowed paths respected). Q&As are linked to the CRR article they interpret and
reached through it, rather than flooding default search.
*Evidence:* adding them this way raised retrieval recall@10 from 0.65 to **0.69** on the early
set; mixing them into default search did not.

**1.5 A source registry as the single source of truth.** `sources.yaml` holds every document's
URL, issuer, legal level, scope filters, `applies_to`, reuse/licence note and whether it is in
default search. Public sources only; Basel material is link-only.

## 2. Chunking and indexing

**2.1 Structure-aware chunks with a deterministic context prefix.** Each chunk is one legal unit
(article paragraph, point, guideline paragraph, Q&A) and starts with its path, e.g.
`CRR › Part Three › Title II › Chapter 3 › Art. 178 Default of an obligor › Art. 178(1)`.
This gives "contextual retrieval" without an LLM call per chunk: free, reproducible and
auditable. Long units are windowed (≤ 1,200 tokens) and stitched back together for citation.

**2.2 One database for everything.** **Postgres 17 + pgvector** (HNSW index) holds text,
1,024-dim embeddings, full-text `tsvector`, metadata and the cross-reference graph. No separate
vector database or graph database: fewer moving parts, SQL joins between vectors and edges.
*Tools:* Docker (`pgvector/pgvector:pg17`), psycopg 3.

**2.3 Cross-reference graph from the text itself.** References such as "Article 181(1)(b)",
defined terms from CRR Art. 4(1), amendments and Q&A→article links are extracted
deterministically into an `edges` table (10,274 edges). The agent's `follow_reference` tool
walks it.

**2.4 Local open-source embeddings.** **BGE-M3** (multilingual, 1,024-dim) runs on a local GPU,
so indexing costs no API tokens and re-indexing is free.

## 3. Retrieval

**3.1 Hybrid search with rank fusion.** BM25 (Postgres full-text) and dense search are fused with
Reciprocal Rank Fusion (k = 60). Legal text needs both: exact terms ("Article 178", "ELBE") and
paraphrase ("when is a borrower in default").

**3.2 A BM25 fix that matters for legal text.** OR-ing every question word let common words
dominate. The BM25 query keeps only rare terms (document frequency ≤ 10 %).
*Evidence:* overall recall@10 0.57 → 0.65 together with the scope fix below.

**3.3 Cross-encoder reranking.** The top 30 candidates are reranked with **bge-reranker-v2-m3**
(local, GPU). *Evidence (69 questions):*

| Mode | recall@10 | MRR@10 | Single-answer recall |
|---|---|---|---|
| BM25 | 0.59 | 0.40 | 0.66 |
| Dense (BGE-M3) | 0.74 | 0.65 | 0.81 |
| Hybrid (RRF) | 0.76 | 0.58 | 0.84 |
| **Hybrid + rerank** | **0.79** | **0.69** | **0.89** |

**3.4 Practitioner glossary expansion.** Practitioners write "A-IRB", "LGD in-default", "DoD",
"MoC", "CCF"; the regulation writes "own estimates of LGD", "definition of default", "margin of
conservatism". A curated glossary of ~20 terms expands the query with the legal wording.
The reranker also scores against the expanded query.
*Evidence:* recall@10 0.79 → 0.81 (expansion in search), → **0.84** (also in the reranker);
hit@10 0.93, MRR 0.73. Known trade-off: one multi-hop question lost a passage, which the agent
now recovers.

**3.5 Scope and metadata filters.** Default scope excludes the amending act and rationale text;
filters by source, legal level and `applies_to` (SI / LSI) are available to the UI and agent.

## 4. Answering and grounding

**4.1 Structured answers, not free text.** The model returns JSON: an answer plus atomic claims,
each with citations and a kind — **law** (CRR / RTS), **supervisory** (EBA, ECB) or
**interpretation** (the model's inference, flagged as such). Credit risk users need to know
which is which.

**4.2 A deterministic citation checker.** Code, not an LLM, checks every claim: it must cite a
passage that was actually provided, numbers in the claim must appear in that passage
(normalised: "0,05 %" = "0.05%", period words like "ninety days"), and law claims must cite law.
*Evidence:* **0.99** of claims pass on the smoke set; failures are shown to the user.

**4.3 Abstention in two layers.** A free retrieval gate (no LLM call if the best rerank score is
below 0.05) plus a scope rule in the prompt, which also covers off-topic provisions that are in
the corpus (Art. 92 lists the leverage ratio). Partial answers say what is missing instead of
guessing. *Evidence:* 5/5 out-of-scope questions declined; 25/25 in-scope answered.

**4.4 "As of" dates built by code.** The answer header states the as-of date and the
consolidated version of each cited source, generated from metadata, never by the model.

**4.5 Model tiers and a thin provider layer.** Model IDs live in `config.yaml` only: Haiku 5.5
for bulk work (judge, router), Sonnet 5.5 for answering and the agent, Opus 5.5 reserved for
milestone evals. One provider interface runs either the Claude subscription (`claude -p`) for
development or the **Anthropic SDK** with the visitor's own key for the public demo.

## 5. Agentic retrieval

**5.1 Route first: most questions don't need an agent.** A Haiku router (~1k tokens) decides
between single-pass (~6k tokens) and the agent (~40k tokens).
*Evidence:* router accuracy 0.81 on 70 questions; it sends 11 of 14 multi-hop and comparison
questions to the agent. Over-routing costs tokens, not quality.

**5.2 A bounded agent with domain tools.** Six read-only tools over the corpus: `search`,
`get_article`, `get_passage`, `follow_reference` (walks the graph), `get_definition` (CRR
Art. 4 / 142) and `get_qa` (EBA Q&As on an article). Citation keys resolve back to chunks, so
the same checker applies to agent answers.

**5.2a Two runtimes, one agent.** The same prompt, tools and citation keys run in two places:
- *Development:* Claude Code (`claude -p`) drives the loop over the RegLens MCP server, on the
  Claude subscription; the tool server enforces 10 tool calls and the CLI caps cost.
- *Public demo (bring your own key):* RegLens runs the loop itself on the **Anthropic Messages
  API** (documented manual tool-use loop, tools executed in-process). Limits are enforced in
  RegLens code: 10 tool calls, 13 model turns as a hard stop, 200k tokens per question; at a
  limit the agent is told to answer with what it has. Each turn adds a cache breakpoint so the
  growing conversation is read from cache, and every call is logged to the ledger.

**5.3 Tools exposed as an MCP server.** The same tools run as a **Model Context Protocol**
server (stdio), so any MCP client — Claude Desktop, Claude Code, other agents — can query the
corpus. *Tools:* `mcp` Python SDK.

**5.4 A stopping rule: check the legal basis.** Before answering, the agent must read the CRR or
RTS provisions its passages cite, and search for the law when it only has guidelines.
*Evidence:* on the downturn-LGD question the agent went from 1 search (guidelines only) to
6 calls reading CRR Art. 181 and the RTS; citation recall 0.25 → 0.50.

**5.5 Snippets, then full text on demand.** Search returns 2,000-character snippets marked as
truncated; `get_passage` returns a full passage. A measured, non-obvious result: giving the
agent *full* passages in search made it **worse** on multi-step questions — the results looked
complete, so it stopped early (multi-hop 12/14 → 9/14 on two runs).

| 12 routed agent questions | 2k snippets | 4k full passages | **Snippets + `get_passage`** |
|---|---|---|---|
| Judge score (of 24) | 18 | 19 | **20** |
| Tokens | 609k | 588k | **482k** |

**5.6 Every tool call is traced.** Each answer stores its tool trace (tool, arguments, passages
returned), which is how the failures above were diagnosed instead of guessed.

*Full golden set (70 in-scope questions):* correctness **0.86 → 0.91** single-pass vs routed,
factual 0.98, **no wrong answers**; 10/10 out-of-scope declined. A single-pass answer that
reports missing information (`missing_info`) falls back to the agent (8 of 49 single-pass
routes; fixed 3 answers).

*Smoke set:* single-pass vs routed on the 25 in-scope smoke questions — correctness **0.78 →
0.90**, multi-hop **0.43 → 0.71** (0.64–0.86 across the agent designs tried), citation
recall **0.62 → 0.80**.

## 5b. Policy gap analysis

**Obligation register from the regulation itself.** 322 passages chosen in
`gap/scope.yaml` (the coverage map of a validation policy) are turned into **752 atomic
obligations** (one actor, one action, one condition), each with its citation key, legal level,
topic and a **verbatim quote checked in code** (746/752 found; the 6 misses are PDF artefacts).
Committed as `register/obligations.jsonl`, so it can be reviewed like any other artefact.

**Matching with evidence.** For each obligation, the matcher returns covered / partial /
missing / contradicted / not applicable / belongs in another document, with the policy
clauses it relies on and a verbatim quote from them (checked in code). A short policy is sent
whole in a cached system prompt, so retrieval cannot hide the relevant clause.

**Evaluated against planted gaps.** A synthetic policy with 15 planted deficiencies and a
separate answer key: **15/15 found, flag type correct for all** — after one prompt revision on
the same gaps (a caveat stated in the results). Sampled non-planted findings were 20/20
factually correct, but only ≈ 11/20 belonged in a validation policy: precision is the open
problem, and the matrix is built for reviewer sign-off.

## 6. Evaluation

**6.1 An expert golden set.** 80 questions written and verified against the source texts by a
credit risk practitioner (CFA, FRM): factual, multi-hop, comparison, applicability (SI / LSI)
and out-of-scope, each with expected citations and accepted alternatives where two provisions
say the same thing.

**6.2 Evaluation in tiers, cheapest first.**
1. Retrieval metrics (recall@k, hit@k, MRR) — no LLM, run on every change.
2. Deterministic answer metrics: citation recall, claims passing the checker, abstention.
3. An LLM judge (Haiku, low effort, ~2k tokens per answer) scoring correctness 0 / 1 / 2 against
   the expert answer, cached by answer, judge and reference version.
4. Router accuracy against question types.

**6.3 Variance is measured, not assumed.** `--repeat N` re-runs the agent into a separate cache.
Two identical runs differed by a point on individual questions, so conclusions are drawn on
patterns that repeat (e.g. the full-passage regression), not single scores.

**6.4 Everything is cached and versioned.** Answers are cached per prompt / tool-code hash, so
re-running an unchanged eval costs nothing and any change to prompts or tools invalidates
exactly what it affects.

## 7. Cost discipline

- **Tokens are the primary measure;** EUR is an API-equivalent yardstick. Budget: target €150,
  ceiling €250 for the whole MVP.
- **A usage ledger** records model, input / output / cache tokens and API-equivalent cost of
  every LLM call; `reglens usage` reports by phase, model or purpose.
- **Estimate before running:** every LLM command prints a token estimate and needs `--yes`;
  runs above 1M tokens need explicit approval.
- **Free first:** local embeddings and reranker; deterministic chunk context instead of LLM
  summaries; deterministic checks before LLM judging.
- **Prompt caching:** stable system prompts and tool definitions first; most agent tokens are
  cache reads.
- *So far:* 3.1M tokens, ≈ **€3.6** API-equivalent, through Phase 3.

## 8. Scope, safety and trust

- Public sources only; no employer or confidential material; the gap-analysis demo policy is
  synthetic.
- Bring-your-own-key demo: keys stay in the browser session and are never logged or stored.
- Disclaimer in the README, UI and every generated report.
- MIT licence.

## 9. Engineering

Python 3.12+ (developed on 3.14), **uv**, src layout, **ruff**, **pytest** (65 tests; no test
calls a paid API — the CLI and the SDK client are faked), Docker for the database.

**Web UI:** **Next.js** (App Router, TypeScript) with Tailwind and shadcn/ui, over a small
**FastAPI** backend. Answers stream as **Server-Sent Events**: retrieval, the routing decision
and every agent tool call appear live, then the answer with citation badges that open their
sources. The bring-your-own key is held in page memory only and forwarded per request. The
earlier Streamlit UI remains as a fallback.

## Roadmap items not built yet

- **Gap analysis:** a second synthetic policy for an untuned recall test; precision calibration.
- **Batch API** for offline jobs (obligation extraction, bulk judging).
- National regulators (DNB first), point-in-time version switching, a Next.js UI.

Details and full results: [ROADMAP](ROADMAP.md) · [retrieval](results/retrieval-phase1.md) ·
[answers](results/answers-phase2.md) · [agent](results/agent-phase3.md).
