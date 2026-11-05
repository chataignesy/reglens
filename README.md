# RegLens

**Ask EU credit risk regulation a question and get an answer you can check:** every claim
cites the article or paragraph it comes from, says whether that source is law, a supervisory
expectation or an interpretation, and states the "as of" date of the texts. When the corpus
does not support an answer, RegLens says so instead of guessing.

Built for credit risk modellers and validators working with the IRB approach, the standardised
approach, credit risk mitigation and the definition of default.

There is no hosted demo: watch the demo video (link to follow) or run it locally (below).

> **Disclaimer.** Personal open-source project. Not affiliated with any employer, supervisor or
> regulator. Not legal or regulatory advice. Always check the official texts.

## What an answer looks like

> **What PD input floors apply to retail exposures under CRR3?**
>
> For retail exposures, the PD used as an input to the risk-weighted exposure amount and
> expected loss formulae is the higher of the one-year PD of the grade or pool and the
> applicable PD input floor [1]:
>
> - **0,1 %** for QRRE revolvers [1]
> - **0,05 %** for retail exposures that are not QRRE revolvers [1]
>
> Where an exposure is covered by an eligible guarantee from a central government, central bank
> or the ECB, the floor does not apply to the covered part [2].
>
> *As of 31 Oct 2026; CRR consolidated version of 26 Jun 2026*
>
> [1] CRR Art. 163(1) — law · [2] CRR Art. 159a — law · Citation check: 4/4 claims supported

Try questions like:

- *Can a bank use own LGD estimates for a large corporate under A-IRB?*
- *How long is the probation period after a distressed restructuring?*
- *What happens to downturn LGD if no downturn can be observed in the bank's data?*
- *Which output floor factor applies in 2026?*
- *Does the ECB guide to internal models apply to less significant institutions?*

## What it covers

| Source | Legal level |
|---|---|
| CRR (Regulation (EU) No 575/2013), consolidated version including CRR3: definitions, own funds requirement and output floor, standardised approach, IRB approach, credit risk mitigation | law |
| RTS on IRB assessment methodology, default materiality threshold, economic downturn | law (RTS) |
| EBA Guidelines on definition of default, PD/LGD estimation, downturn LGD, CRM for A-IRB, loan origination and monitoring | EBA guideline |
| EBA Single Rulebook Q&A on CRR credit risk (243 final Q&As) | EBA Q&A |
| ECB guide to internal models (overarching principles, credit risk); ECB validation reporting instructions | ECB supervisory expectation |

English only, public sources only. Not covered: market risk, counterparty credit risk,
operational risk, securitisation, liquidity, leverage, IFRS 9, national rules.

## How it works

1. **Ingestion from official sources:** the law via the EU Publications Office API (consolidated
   version in force), guidelines and the ECB guide via Docling. Every chunk is one legal unit
   (article paragraph, point, guideline paragraph, Q&A) labelled with its place in the
   hierarchy, e.g. `CRR › Part Three › Title II › Chapter 3 › Art. 178(1)`.
2. **Retrieval:** keyword (BM25) + embeddings (BGE-M3) fused, reranked by a cross-encoder, with
   a practitioner glossary ("A-IRB", "DoD", "MoC" → the regulation's own wording). All local.
3. **Routing:** a small model decides whether the question needs one lookup or several
   provisions. Simple questions get a single grounded answer; multi-step questions go to an
   **agent** that searches, follows cross-references and reads definitions and EBA Q&As
   (bounded: at most 10 tool calls). A quick answer that reports missing information is retried
   with the agent.
4. **Checking:** code verifies that every claim cites a passage it was given and that its numbers
   appear in that passage, before you see the answer.

The corpus tools are also available as an **MCP server**, so Claude Desktop or any MCP client
can query the regulation directly. Design choices and evidence: [docs/DESIGN.md](docs/DESIGN.md).

## How well it works

Measured on 120 golden questions, drafted with an LLM and checked and corrected against the
source texts by a credit risk practitioner, graded by an LLM judge against the expert answers
([first 80](docs/results/golden-phase3.md), [40 harder ones](docs/results/golden-120.md)):

| 104 in-scope questions | |
|---|---|
| Correctness (fully / partly / wrong) | **0.89** (82 / 22 / **0**) |
| Citation recall (expected sources cited) | 0.89 |
| Claims passing the citation check | 0.99 |
| Out-of-scope questions declined | 15 / 16 |

Multi-step questions are where the research agent earns its cost. On the 11 newest multi-hop
questions, a single retrieval pass scores 0.59 and the routed agent 0.86. See
[the agent results](docs/results/agent-phase3.md).

## Also included: policy gap analysis

A second use case, shown on a **synthetic** Model Validation Policy of a fictitious bank: an
obligation register of 752 atomic obligations extracted from the regulation (each with a
verified quote), matched against the policy clause by clause into a coverage matrix (covered /
partial / missing / contradicted) with evidence. It finds all 15 deficiencies planted in the
policy; see [the results and caveats](docs/results/gap-phase4.md).

## Run it locally

```bash
uv sync --extra ml --extra db --extra api --extra mcp  # Docling, BGE-M3, Postgres client, API, MCP
docker compose up -d                                   # Postgres + pgvector on 127.0.0.1:5433
uv run reglens download                                # sources: EU Publications Office, EBA, ECB
uv run reglens parse && uv run reglens index
uv run reglens ask --route "Can a bank use own LGD estimates for a large corporate under A-IRB?"

uv run uvicorn reglens.api.app:app --port 8000         # API for the web UI
cd web && npm install && npm run dev                   # web UI on http://localhost:3000
```

The web UI (Next.js) streams the research steps live while an answer is produced; see
[web/README.md](web/README.md). The earlier Streamlit UI still works as a fallback
(`uv sync --extra ui`, then `uv run streamlit run src/reglens/ui/app.py`).

A GPU is recommended for indexing (embeddings and reranker run locally).

**API key:** the web UI takes your own Anthropic API key. It stays in your browser session, goes
only to the Anthropic API and is never logged or stored. A quick answer costs about 6k tokens;
an agent answer 40–90k.

**Evaluation:** `reglens eval-retrieval` (no LLM calls), `reglens eval-answers` and
`reglens judge` (dry run unless `--yes`; cached). Every LLM call is logged; `reglens usage`
reports tokens per phase, model and purpose. The whole project so far, development and
evaluation, used about 7M tokens.

## Licence

MIT. The regulatory texts remain subject to their publishers' reuse terms (see `sources.yaml`).
