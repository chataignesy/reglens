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
  effective dates now, build version switching later), non-credit-risk topics.

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

The MVP is built on a deliberately small budget. Local development runs on the user's **Claude
subscription** (`billing: subscription` in `config.yaml`), so **tokens are the primary measure**;
EUR figures are API-equivalent yardsticks (target ≤ €150, ceiling €250, per-phase allocations in the
roadmap). Real per-token billing only applies to the bring-your-own-key demo. Subscription usage
limits are the practical constraint — large runs can exhaust them.

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
- **Usage ledger:** every LLM call appends model, input/output/cache tokens and API-equivalent EUR
  to `data/ledger.jsonl`; `reglens usage` summarises per phase, model or purpose.
- **Eval tiers:** retrieval-only metrics (no LLM cost) on every change → 30-question smoke set on Sonnet
  for daily work → full golden set (Opus) only at phase milestones.

**Claude Code session rules**
- Before running anything that calls an LLM, **state the estimated tokens** (`reglens estimate`);
  if a run exceeds **1M tokens** (or €2 under API billing), ask first. Prefer a dry run or a
  5-item sample before a full run.
- Never load raw regulation files or the full corpus into context — inspect with scripts (counts,
  `head`, targeted grep). Read only the lines needed.
- No subagents or broad codebase sweeps unless the user asks. Keep this file short; put detail in `docs/`.

## Architecture (target)

- **Python 3.12+**, `uv`, FastAPI backend (`reglens.api`), **Next.js** UI in `web/` (Streamlit as fallback).
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
| 2026-10-26 | Dev runs on Claude subscription: ledger tracks tokens; EUR is API-equivalent only |
| 2026-10-31 | Gap analysis: validation-focused obligation register (scope in `src/reglens/gap/scope.yaml`), extracted with Sonnet (Opus needs a newer local CLI), verbatim quotes checked in code |
| 2026-10-31 | Synthetic Model Validation Policy: short (~6–8 pages), ~15 planted gaps; matching per obligation |
| 2026-11-04 | No public deployment: demo is a recorded video; Q&A is the main demo, gap analysis secondary |
| 2026-11-04 | Next.js UI (`web/`, Tailwind + shadcn/ui) over a FastAPI backend (`reglens.api`) with streamed progress; Streamlit kept as fallback |
| 2026-11-11 | Corpus indexed as immutable generations (staged, validated, atomically published, rollback); readers pin one generation |
| 2026-11-11 | Evals grade against frozen reference snapshots (`evals/frozen/`); golden revisions are versioned, never edits to completed runs |
| 2026-11-11 | Optional shared local inference service (one GPU owner) for embeddings/reranker; direct local mode still supported |
| 2026-11-13 | Codex CLI (ChatGPT subscription) as opt-in benchmark backend via `config.codex.yaml`; Claude stays default, no OpenAI API key |
| 2026-11-15 | Routing strategy `single_first` is opt-in; LLM routing stays default (quality equivalence not established) |
| 2026-11-15 | Saved eval answers/grades kept in `docs/results` as audit evidence; merge commits (not squash) so cited SHAs stay valid |
