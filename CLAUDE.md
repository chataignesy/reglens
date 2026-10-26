# RegLens — project rules

RegLens is a personal, open-source RAG assistant for **EU credit risk regulation**, built as a public
portfolio project (GitHub + LinkedIn). Plan and milestones: [docs/ROADMAP.md](docs/ROADMAP.md).

## Product scope (MVP)

- **Users:** credit risk modellers and model validators (IRB, SA, CRM, definition of default).
- **Use case A — Regulatory Q&A:** grounded answers with paragraph-level citations.
- **Use case B — Policy gap analysis:** compare a policy document against an obligation register
  extracted from regulation; output a coverage matrix (covered / partial / missing / contradicted).
- **Jurisdiction:** EU (CRR3/CRD VI, RTS/ITS, EBA) + ECB/SSM. National regulators (DNB first) after MVP.
- **Applicability:** both significant (SI) and less significant (LSI) institutions, as metadata
  `applies_to: SI | LSI | all` — answers must say which applies.
- **Language:** English only.
- **Out of scope for MVP:** non-public documents, multi-version point-in-time history (store
  effective dates now, build version switching later), Next.js UI, non-credit-risk topics.

## Hard rules

1. **Public sources only.** Never ingest internal, confidential, or employer documents. Every source is
   registered in `sources.yaml` with URL, retrieval date, legal level, and reuse/licence note.
   Basel (BIS) material is link-only unless its terms allow reuse.
2. **Clean separation from the user's employer.** No employer code, prompts, eval sets, architecture
   or policies — everything here is built from scratch. The demo gap-analysis policy is **synthetic**.
3. **Disclaimer everywhere** (README, UI, generated reports): personal project, not affiliated with any
   employer or supervisor, not legal or regulatory advice.
4. **Grounded answers:** every claim cites source + article/paragraph; answers state their "as of" date;
   abstain when the corpus does not support an answer; distinguish *law* / *supervisory expectation* /
   *interpretation*.
5. **Never commit secrets.** Demo is bring-your-own-key: user API keys live only in the browser session,
   are never logged, stored, or sent anywhere except the LLM provider.

## Token & cost budget (applies to the app AND to Claude Code sessions)

The MVP is built on a deliberately small budget. **Target ≤ €150 total API spend for the MVP, hard
ceiling €250.** Per-phase allocations are in the roadmap.

**App / pipeline rules**
- **Model tiers** (configured in one place, never hard-coded):
  `claude-haiku-5-5` for bulk/cheap tasks · `claude-sonnet-5-5` for development and dev evals ·
  `claude-opus-5-5` only for milestone evals and one-off high-value extraction, with a stated reason.
- **Free first:** local open-source embeddings (e.g. BGE-M3) and a local reranker by default; switch to
  a paid embedding API only if retrieval evals show a clear gain.
- **Deterministic chunk context** (hierarchy path, e.g. `CRR3 › Part Three › Title II › Ch. 3 › Art. 180(1)(a)`)
  instead of LLM-generated context. LLM summaries only if evals prove they help.
- **Prompt caching:** stable prefixes (system prompt, tool definitions) first; no timestamps or random
  IDs before the cache breakpoint. Verify with `cache_read_input_tokens`.
- **Batch API** (50% off) for offline jobs: obligation extraction, LLM-judge grading.
- **Bounded agents:** cap tool-call steps and tokens per query; log usage of every call.
- **Cost ledger:** every paid API call appends model, input/output/cache tokens and estimated cost to
  `data/ledger.jsonl`; a CLI command summarises spend per phase.
- **Eval tiers:** retrieval-only metrics (no LLM cost) on every change → 30-question smoke set on Sonnet
  for daily work → full golden set (Opus) only at phase milestones.

**Claude Code session rules**
- Before running anything that calls a paid API, **state the estimated cost**; if it exceeds **€2**,
  ask first. Prefer a dry run or a 5-item sample before a full run.
- Never load raw regulation files or the full corpus into context — inspect with scripts (counts,
  `head`, targeted grep). Read only the lines needed.
- No subagents or broad codebase sweeps unless the user asks. Keep this file short; put detail in `docs/`.

## Architecture (target)

- **Python 3.12+**, `uv`, FastAPI backend, **Streamlit** UI for the MVP (Next.js later).
- **Postgres + pgvector + full-text search** in one database: chunks, embeddings, cross-reference
  edges, obligation register. No separate vector or graph DB.
- **Ingestion:** EUR-Lex HTML/XML (preferred over PDF), Docling for EBA/ECB PDFs. Chunk at
  article/paragraph level with metadata: source, legal level, article ID, effective dates,
  amending act, status, `applies_to`, topic.
- **Retrieval:** hybrid (BM25 + dense) → reranker → metadata filters; agentic tools
  (`search`, `get_article`, `follow_reference`, `get_definition`, `get_qa`); also exposed as an MCP server.
- **LLM access** through a thin provider interface (Claude by default, swappable for benchmarking),
  using the official Anthropic SDK.

Target layout: `src/reglens/{ingest,index,retrieve,agent,gap,eval,llm,ui}`, `data/` (raw data
gitignored), `evals/golden/*.jsonl`, `docs/`.

## Conventions

- Type hints, small modules, `ruff` + `pytest`. Tests must not call paid APIs (mock or record).
- Config via `.env` / `config.yaml`; `.env` is gitignored.
- Licence: **MIT**.

## Decisions log

| Date | Decision |
|---|---|
| 2026-10-26 | Claude by default + thin provider layer; tiered models for budget |
| 2026-10-26 | Streamlit for MVP, Next.js later |
| 2026-10-26 | Open source, MIT |
| 2026-10-26 | Public demo is bring-your-own-key; recorded video for LinkedIn |
| 2026-10-26 | Public sources only; EU + ECB first, national regulators later |
| 2026-10-26 | MVP API budget: target €150, ceiling €250 |
