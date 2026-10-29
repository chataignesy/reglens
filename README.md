# RegLens

Grounded RAG assistant for **EU credit risk regulation** (CRR3, EBA, ECB), built for credit risk
modellers and validators:

- **Regulatory Q&A** with paragraph-level citations, legal level of each source and "as of" dates
- **Policy gap analysis** against an obligation register extracted from regulation (planned)

> **Disclaimer.** Personal open-source project. Not affiliated with any employer, supervisor or
> regulator. Not legal or regulatory advice. Always check the official texts.

Status: Phase 2 (grounded Q&A). See [docs/ROADMAP.md](docs/ROADMAP.md) and
[docs/results](docs/results/).

## Quick start

```bash
uv sync --extra ml --extra db --extra ui   # GPU stack (Docling, BGE-M3), Postgres client, Streamlit
docker compose up -d                       # Postgres + pgvector on 127.0.0.1:5433
uv run reglens download                    # sources from EUR-Lex (CELLAR), EBA, ECB
uv run reglens parse && uv run reglens index
uv run reglens ask "What is the PD input floor for IRB corporate exposures under CRR3?"
uv run streamlit run src/reglens/ui/app.py # web UI: bring your own Anthropic API key
```

Evaluation: `reglens eval-retrieval` (no LLM calls) and `reglens eval-answers` (dry run unless
`--yes`; answers cached). Every LLM call is logged to `data/ledger.jsonl`; `reglens usage` shows
tokens (and API-equivalent EUR) against the budget.

**API keys:** in the web UI your key stays in the browser session and goes only to the Anthropic
API; it is never logged or stored.

## Licence

MIT. Regulatory texts remain subject to their publishers' reuse terms (see `sources.yaml`).
