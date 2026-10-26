# RegLens

Grounded RAG assistant for **EU credit risk regulation** (CRR3, EBA, ECB), built for credit risk
modellers and validators:

- **Regulatory Q&A** with paragraph-level citations and "as of" dates
- **Policy gap analysis** against an obligation register extracted from regulation

> **Disclaimer.** Personal open-source project. Not affiliated with any employer, supervisor or
> regulator. Not legal or regulatory advice. Always check the official texts.

Status: Phase 0 (foundations). See [docs/ROADMAP.md](docs/ROADMAP.md).

## Quick start

```bash
uv sync
uv run pytest
uv run reglens usage
uv run reglens estimate --tier dev --input 50000 --output 3000 --calls 150
```

Every LLM call is logged to `data/ledger.jsonl`; `reglens usage` shows tokens (and API-equivalent
EUR) against the budget.

## Licence

MIT. Regulatory texts remain subject to their publishers' reuse terms (see `sources.yaml`).
