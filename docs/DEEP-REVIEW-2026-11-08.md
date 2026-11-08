# RegLens: deeper design and implementation review

8 November 2026. Supplements [the first review](REVIEW-2026-11-08.md).

This pass inspected ingestion/parsing, structural identity, graph construction, index refresh, retrieval/reranking, agent tools, MCP lifetime, provider usage accounting, CLI orchestration, and evaluation selection. It used the actual 4,631 processed chunks, all 13 source-lock records, regenerated cross-reference edges in memory, and current local answer caches. Application code was not changed.

## Assessment

The project has a coherent MVP architecture, but its strongest guarantees currently depend on conventions rather than enforced contracts. The key weakness is **loss of identity and completeness as information moves between stages**:

1. Parsing loses a paragraph number after some structural splits.
2. Citation keys omit a section identifier needed to distinguish repeated paragraph numbers.
3. Tools truncate legal provisions without consistently saying what is absent.
4. Answer evaluation collapses distinct source locations and required ranges.
5. The judging CLI selects a cache namespace instead of an actual routed-run manifest.

These problems can reinforce one another: an incomplete provision can be assigned a plausible citation and receive full citation-recall credit. More prompt tuning cannot reliably fix that chain. The first engineering priority should be to preserve source identity, completeness, and run lineage through every stage.

## New confirmed findings

Priorities follow the first report: P1 affects the central trust promise and should be addressed before presenting that guarantee; P2 is a substantive correctness or reliability defect. Reproductions are in [deep_checks.py](review/deep_checks.py), with captured [JSON output](review/deep-checks-result.json). Mocked boundaries and local-artifact observations are identified below.

### D1 — P1: Re-downloaded PDFs can be parsed as old text with new metadata

Location: `src/reglens/ingest/pdf.py:31–35`; `src/reglens/cli.py:152–163`.

The Docling cache path is only `<source_id>.md`. Its reuse checks neither PDF hash nor version. The parsing CLI does not expose/pass `force` to conversion. After `download --force` replaces a PDF, `parse` can reuse the old Markdown and label its chunks with the newly retrieved date. This is more serious than a slow update: the text and apparent source freshness can disagree.

Reproduction: a temporary source PDF containing new bytes, plus an existing Markdown cache, returns “OLD converted regulation.” No Docling execution or model request was needed.

Fix: content-address conversion artifacts by input-file digest and converter/config version. Store that digest in parsed units and chunks; refuse to index a conversion whose provenance does not match the source lock. Test download replacement → conversion invalidation → new chunk content as an integrated path.

### D2 — P1: Paragraph continuations lose their parent identity after point splitting

Location: `src/reglens/ingest/eurlex.py:209–245`.

`emit_split` sets `current = None`. A following unnumbered continuation still has `para_num` available, but the ordinary Unit constructor uses `num`, which is `None`, instead. The continuation becomes an article-level chunk, no longer part of its numbered paragraph. Tools filtering by paragraph or selecting the definition point can omit a relevant qualification.

Reproduction: a minimal XHTML paragraph 1 containing point (5a), followed by an unnumbered qualification, yields a final unit with `paragraph=None`. The current corpus contains the matching pattern at `crr3-consolidated:article:142::`: “For the purposes of the first subparagraph, point (5a) … sales threshold … audited financial statements.” The large-corporate definition is separately indexed under paragraph 1, point (5a). `get_definition` excludes the qualification because it requires `point IS NOT NULL`; `get_article(..., paragraph='1')` also excludes that article-level chunk.

Fix: keep structural ownership independently of the current emitted Unit. Model lead-ins, list points, and subsequent qualifications explicitly; a definition lookup should return the definition and its governing qualifications. Add parser fixtures for tails after lists and nested list scopes. Do not simply attach every unnumbered paragraph to the previous point.

### D3 — P1: “Full article” tools silently omit substantial text

Location: `src/reglens/agent/tools.py:78–80`, `:155–160`, `:188–201`.

`get_article` selects at most 40 rows; `_out` then slices the total output at 14,000 characters without an overall truncation marker or continuation token. The per-passage truncation indicator does not cover this aggregate cut. Consequently, a tool described as full text can return an incomplete legal provision without disclosing it.

Using actual local chunks and a mocked SQL boundary that preserves the implementation's sort and LIMIT:

- CRR Article 124 has 16 chunks and 21,278 text characters. Output stops at exactly 14,000 characters, ending mid-word at “paragrap”, with no truncation indication.
- CRR Article 4 has 185 chunks, but the query can select only 40 before the aggregate output cap applies.

The cap itself is sensible; silent incompleteness is the defect. Fix with explicit `complete`, returned/total counts, stable ordering, and pagination/continuation. Agent finalisation should distinguish reading a snippet from reading the complete necessary provision. Preserve the budget while allowing deliberate follow-up reads.

### D4 — P1: Citation keys collide across distinct sections of an included source

Location: `src/reglens/agent/tools.py:63–99`; `src/reglens/ingest/pdf.py:103–117`; `sources.yaml` ECB validation-reporting entry.

The parser records numbering blocks, but citation keys for the ECB validation instructions do not include them or the section path. The special part-qualified key logic only runs when the source declares `parts`. The instructions source does not.

Actual corpus result: `ECB validation reporting instructions para. 1` denotes **14 chunks from 14 numbering blocks**. Examples cover validation deficiency ratings, portfolio size, and customers with outdated ratings. They are distinct locations, not windows of the same paragraph. `resolve_key` retrieves all matching source/ref rows; final answer resolution merges them as if one passage. A citation can therefore expand to unrelated material and numeric values.

Fix: use stable source-version + structural-path + local-paragraph identifiers internally. Human-readable labels should be presentation, not the database identity. Validate that each citation identity maps to exactly one logical unit, allowing only explicitly identified windows/continuations. Include sections for all PDF sources with local numbering, not only the internal-models guide.

### D5 — P2: Explicit references inside the same article disappear from the graph

Location: `src/reglens/ingest/xrefs.py:72–75`.

The self-reference guard compares only source and article. It drops a reference from Article 178(1) to Article 178(3), although the paragraph differs and may supply a necessary condition.

Reproduction: a chunk in Article 178, paragraph 1, with body “The conditions in Article 178(3) shall apply.” produces no reference edge.

Fix: compare the complete source/article/paragraph/point identity, excluding only a genuine reference to the same unit. Retain and resolve sibling-paragraph edges. In addition, point identifiers such as Article 181(1)(b) need to survive extraction, and paragraph-only references need explicit support; the current `_ART` pattern and article-only scan do not provide those capabilities.

### D6 — P1: Citation recall gives full credit to incomplete ranges and wrong document parts

Location: `src/reglens/eval/answers.py:33–69`; `src/reglens/eval/retrieval.py:23–42`; `src/reglens/answer/pipeline.py:65–71`.

Two independent reproductions:

- Expected `paras. 71-73`, actual citation only `para. 71` → answer citation recall **1.0**. Expanded range members are put into one alternatives group, so any one satisfies the entire range. Retrieval evaluation treats the expanded members separately, making the metric inconsistent across stages.
- Expected ECB guide `Foreword, para. 1`, actual citation from `Credit risk`, paragraph 1 → answer citation recall **1.0**. Normalisation removes the part; serialised context also omits title/part metadata needed to disambiguate it.

Fix: represent citations as structured identifiers; distinguish required members (AND) from accepted alternatives (OR). Preserve part/section and source version in evaluation records. Recompute affected metrics after auditing the golden references and cached answers. These probes show that the metric is unsound for those cases; they do not quantify the change to the published aggregate score.

### D7 — P2: The documented judging commands do not reproduce routed correctness

Location: `src/reglens/cli.py:467–475`; `src/reglens/eval/judge.py:47–57`, `:74–76`; `src/reglens/eval/answers.py:110–126`; `docs/results/golden-120.md` reproduction commands.

`eval-answers --route` chooses a combination of single-pass, agent, and fallback records, but no composite answer namespace is created. `judge --agent` selects only the agent namespace, not the per-item answers selected by that routed run. Ordinary `judge` selects only single-pass records. Neither judges the full routed output.

Offline interception of the CLI selection, without provider calls, found the current agent namespace has **25 cached records**, while there are **120 verified golden items**. **66 items that remain single-pass in the routed selection are absent from that agent namespace.** This is not evidence that the published scores were fabricated or necessarily calculated incorrectly; it demonstrates that the documented commands do not independently reproduce the routed headline.

Fix: persist a run manifest with the exact answer artifact/hash and route/fallback outcome for every item. Grade a run ID, including errors and missing records, then aggregate that same manifest. Include routing tokens and both attempts in fallback costs. A headline should link to the exact immutable run it summarises.

### D8 — P2: The general-purpose MCP server exhausts its budget for the whole session

Location: `src/reglens/agent/mcp_server.py:28–37`; `src/reglens/agent/tools.py:143–152`.

The process-global Toolbox permits 10 successful tool calls total. This matches a fresh MCP process for one CLI agent run, but a desktop MCP client normally keeps the process alive across questions. After 10 calls, all later questions receive “Tool budget exhausted” until the process restarts.

Reproduction: consume 10 calls on one Toolbox and make the first call of the next logical question; it is rejected. No server/question reset exists in the current wrapper.

Fix: separate the externally hosted stateless corpus tools from an internally budgeted question session. Enforce question budgets in the agent runtime, or introduce an explicit scoped session contract. Do not silently reset on arbitrary search calls, which would defeat budget enforcement.

### D9 — P2: Failed CLI calls with reported usage are absent from the usage ledger

Location: `src/reglens/llm/provider.py:134–137`; `src/reglens/agent/run.py` cost-cap exception path.

The provider checks `is_error`/subtype before logging usage. A model call that spends tokens and stops at its budget cap therefore raises without recording its available usage. Agent fallback can then show the cost of the replacement answer while omitting the failed attempt.

Reproduction: a fake CLI result reports `error_max_budget_usd` and 1,100 usage tokens; the real provider error path produces **zero ledger records**. This is conditional on usage being present in the CLI response; it is not a measurement of actual unlogged expenditure in the user's ledger.

Fix: record available usage on both successful and failed calls, with outcome/error metadata. Carry spent tokens through failed attempts and fallbacks. Never invent a zero-cost total when usage is unavailable; represent it as unknown.

## Design changes that address the causes

### Make the unit of evidence a first-class object

Currently a Chunk has detailed structural metadata, Hit drops several fields, tool output becomes a plain string, trace entries recover keys with regexes, and finalisation re-queries by human-readable labels. That sequence discards the information needed to prove what was read.

Use a shared Evidence object with source/version, logical unit ID, part/section path, chunk/window IDs, content hash, supplied text, and completeness. Tool responses can render it for the model while retaining the structured object for validation. Generate display citations from those objects. This addresses D2–D4 and the first review's unreceived-citation problem together.

### Separate corpus snapshots from updates

`_cmd_index` commits chunk upserts, source deletions, edge replacement, and embedding batches in separate steps. A running API can observe new text with missing vectors or an old graph, and an interrupted embedding run leaves an incompletely refreshed searchable corpus. Removed sources are not purged if their chunk file is no longer present, because deletion iterates only sources still in the loaded set.

These are code-path risks; a live database failure experiment was not performed. Use a staged corpus/index generation and promote it only after validating source counts, hashes, graph coverage, and embedding completeness. Retain the previous generation for rollback. This need not require another database service: generation IDs and a promotion pointer fit the existing Postgres design.

Store embedding model/revision and preprocessing identity alongside vectors. Current text-hash-only reuse cannot detect a changed embedding model/revision. Pin model revisions for reproducible retrieval. Process-global term frequencies and registry caches should be tied to a corpus generation rather than surviving a refresh indefinitely.

### Treat time and applicability as constraints, not just labels

Chunk records hold a source version but no effective interval; hits and model context do not preserve the full applicability metadata. The “as of” date is the current answer date, while the corpus is a previously built snapshot. This does not implement legal point-in-time reasoning, and source download dates are not effective dates.

For the MVP, state “answer generated on” separately from “corpus snapshot/source versions” and make freshness checks explicit. Preserve applicability in evidence and prompts for all modes. Later, implement valid-from/valid-to constraints and distinguish publication, consolidation, retrieval, and application dates. This is a domain-model correction; no particular regulatory rule's effective date was independently adjudicated here.

### Make evaluations execute the product's orchestration

The runtime and evaluation duplicate routing/fallback logic. The evaluation uses cached route choices, selects cached answer variants, and then grades through a separate selector. This makes it easy to compare or price a different execution than the one the UI uses.

Introduce one orchestration service returning a validated Answer plus an immutable execution record. CLI, HTTP, Streamlit, and evaluations should invoke that same service; transport differences belong in provider/tool adapters. Test both CLI/MCP and API runtimes against the same scripted tool-response scenarios and invariants. A fake SDK request-shape test cannot establish real provider compatibility, but shared contract tests can establish parity of budgets, evidence, and fallback behavior.

### Make operational limits explicit

The HTTP endpoint starts one new thread per request with no admission control; parallel expensive retrieval and agent requests can compete for GPU memory and provider quota. A local MVP does not need a distributed queue, but it does need a small concurrency limit, lifecycle cancellation, bounded timeouts, and an honest readiness state. Current health always returns OK and model warmup exceptions happen in a detached background thread.

Provide distinct liveness and readiness, one controlled model initialisation path, and a bounded executor. Keep the local-only subscription endpoint assumption explicit. Do not add deployment infrastructure merely to solve these local lifecycle problems.

### Describe retrieval accurately and test what matters

The function named `bm25` uses PostgreSQL `ts_rank(..., 1)` with rare-term selection; it is not an implementation of the BM25 scoring formula. The hybrid lexical/dense approach remains reasonable, but name the baseline accurately so the comparison is reproducible.

Cross-encoder inputs are capped at 1,024 tokens while chunks target approximately 1,200 tokens plus hierarchy and query. Suffix information can therefore be excluded from reranking. This is a design risk requiring model-tokenizer-based measurement, not a confirmed recall regression. Record truncation rates, test long provisions with decisive tail exceptions, and compare legal-unit-aware candidate expansion before adding another model layer.

## Additional integrity observations

- All **13 source-lock records** matched their existing local raw-file SHA-256 hashes. This confirms local file/lock agreement, not independent publisher authenticity or freshness.
- Regenerating graph edges from the local chunks produced **10,274 edges**, consistent with documentation. **1,116 edges** point to an article absent from this scoped corpus: 1,000 refers_to, 64 amends, 52 answers_on. Many may be legitimate out-of-scope targets; this is not a count of graph bugs. Tools should distinguish “known external/out-of-scope target” from a broken internal reference.
- The corpus contains **535 windowed chunks**, and no current text chunk exceeds 4,000 characters. That supports the per-passage size assumption on this snapshot; it does not prevent D3's aggregate-output truncation.
- The stored golden set contains **120 verified items plus 3 drafts**. Counts in this report's routed comparison exclude drafts.
- Existing tests exercise many positive and mocked paths, but the reproduced failures cross module boundaries: refreshed source → cached conversion, paragraph split → definition lookup, citation identity → metric, and routed run → judging. Expand tests around those boundaries rather than adding more shallow field checks.

## Verification and scope limits

Run the evidence script from the repository root:

```powershell
.venv\Scripts\python.exe docs/review/deep_checks.py
```

It performs 12 groups of observations using temporary fixtures, mocks at provider/SQL boundaries, and local corpus/cache artifacts. It neither calls an LLM nor writes to the database. These are reproducibility probes, not passing acceptance tests: the captured output deliberately records current faulty behaviour. The review script passes Ruff. The prior 84-test result remains valid for the unchanged application source; it does not contradict these additional failures.

The Postgres endpoint timed out, so no live SQL query-plan, HNSW/filter recall, transaction-failure, concurrency/load, or GPU retrieval benchmark was claimed. No provider call, regulatory website freshness check, or legal interpretation validation was performed. The previous browser review remains limited to the rendered desktop form and saved gap demo.

Recommended sequence: fix PDF provenance and legal-unit identity first (D1–D4); correct evaluation identity/selection before quoting refreshed metrics (D6–D7); restore graph and MCP contracts (D5, D8); then fix usage accounting and complete the lifecycle work identified in the first review. Add regression acceptance tests for the reproduced failures as each fix lands.
