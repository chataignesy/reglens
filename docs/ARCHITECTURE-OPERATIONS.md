# Architecture foundations: operation and remaining limits

Implemented on `codex/architecture-foundations`, 11 November 2026. The application remains
local and uses one Postgres database. Shared inference is an optional local process.

Current Q&A follow-up and session entry point: [HANDOFF.md](HANDOFF.md). The foundation description
below is supplemented by the dated runtime updates; completed infrastructure is not a guarantee
of complete legal answers.

Remaining handoff update (15 November 2026): enclosing amendment introductions are included in
bounded context/get_passage reads and required as citations for numbers not present in a child.
Strict mechanical checks remain unchanged. `answer.routing: single_first` is available in a copy
of configuration as an opt-in, with the same gates and bounded fallback; runtime, CLI and evaluation
paths honor it without reusing LLM route-cache decisions. The LLM default was retained after
[paired development verification](results/handoff-routing14-2026-11-15.md) showed lower candidate
cost but one lower grade. Route-type agreement is only a diagnostic proxy, not answer quality.

Scope/list coverage update (14 November 2026): bounded evidence planning now adds scope/addressee
units and requested-list children/peers under the existing context budget. The shared guard checks
whole-window delivery and conservative enumeration omissions, including API/Codex pre-final and
all agent post-resolution paths. See [local verification](review/COMPLETENESS-VERIFICATION-2026-11-14.md)
for probe bounds and specificity costs. The
[focused live evaluation](results/codex-completeness8-2026-11-14.md) completed at 582,354 tokens:
seven full / one partial, with a silent cure-condition omission and additional research overhead.
The [subsequent precision check](review/COVERAGE-PRECISION-VERIFICATION-2026-11-14.md) resolves
those two observed issues in a two-case run. Time-linked conditions use whole logical lists;
broad neighbours alone do not force research; format repair and context-only completion share
the existing two-call single-pass maximum. Detected unresolved facts still remain visible.

## Corpus publication and interrupted builds

`uv run reglens index` builds chunks, edges and embeddings in a new private schema. It validates
nonempty content, citation keys, complete vectors and edge-source integrity before switching the
active-generation pointer in one transaction. Every answering connection stays on the generation
it opened. Agent subprocesses receive that exact generation. Publication waits for active
application writers and rejects a build whose base was superseded.

- `uv run reglens corpus`: list generations and their validation/model/source manifests.
- `uv run reglens index --no-embed`: stage a build without changing active readers.
- `uv run reglens index --resume GENERATION`: embed the unfinished build's stored text with its
  pinned model identity and publish it; changed workspace files are not mixed into the build.
- `uv run reglens corpus --publish GENERATION`: explicitly publish a reviewed build, including a
  stale build after reviewing the newer head. Validation still applies.
- `uv run reglens corpus --rollback GENERATION`: switch to a previously published snapshot.

Existing public tables remain the legacy snapshot. They become read-only through application
write helpers when the catalog adopts them. The first managed build re-embeds legacy vectors:
old model identity was not recorded, so compatibility is not assumed. Subsequent builds reuse
unchanged vectors only when the complete model identity matches. Keep old schemas while answers
or runs reference them. This implementation does not garbage-collect generations or restrict a
DB owner's ability to alter tables manually; retain backups and use the application writers.
The current user's corpus was not republished during implementation; integration publication,
rollback and concurrent-writer checks used disposable databases.

## Reviewed dates and conditions

Source defaults can be supplied in `sources.yaml`; provision overrides use
`uv run reglens parse --metadata reviewed-provisions.yaml`. The YAML file is a list of records:

```yaml
# Illustrative metadata format only; these are not assertions about a real legal provision.
- source: registered-source-id
  ref: 'Art. 1(1)'
  version: registered-version
  metadata:
    effective_from: '2025-01-01'
    application_from: '2026-01-01'
    application_until: '2027-01-01'
    temporal_verified: true
    applicability:
      approach: [SA]
      jurisdiction: [EU]
```

Date upper bounds are exclusive. `published_on` records publication, not application.
`temporal_verified` must be a boolean and is an explicit review assertion about the governing
interval; it is never inferred from a CELEX consolidation date. Unverified entries remain
unknown. Conditions support approach, exposure class, jurisdiction and national option;
values must match the reviewed vocabulary exactly. Existing SI/LSI filtering remains available.
No national rules or historical texts were invented or ingested by this change.

`reglens ask --as-of 2026-01-01 --approach SA "QUESTION"` carries constraints through single,
routed and agent paths. `--known-validity` excludes unknown intervals. The HTTP request also
supports `require_known_applicability`. The web form accepts an application date and SA/IRB
approach, and explicitly flags unknown coverage. The default allows unknown passages with a
warning; it does not establish historical applicability. The data model supports annotated
intervals, but building a complete multi-version legal history still needs reviewed historical
texts and ingestion/version-selection work.

## Evidence and practitioner review

Mechanical citation checks establish delivery, numeric overlap and legal-level consistency.
They do not establish entailment. `reglens ask --semantic-review --json "QUESTION"` explicitly
requests one additional bulk-tier model assessment. The CLI prints its token estimate before
that call. It assesses every claim against cited evidence and checks prose/claim alignment;
malformed reviews become unavailable assessments. The separate result remains labelled a model
opinion. Semantic review is off by default; no new LLM evaluation was run during implementation.

New answer records retain the context metadata, delivered cited text and hashes, corpus
generation, frozen source registry, research checks and any semantic assessment. Old artifacts
remain readable; missing historical evidence cannot be reconstructed by guessing.

Record a real review with:

```bash
uv run reglens adjudicate PATH_TO_ANSWER_JSON --reviewer "Reviewer name" --decision rejected --reason "Explain the omitted exception and its official reference"
```

Decisions are `accepted`, `rejected`, or `needs_evidence`. Records are content-addressed,
exclusively created, timestamped and bound to the reviewed file's SHA-256. Originals remain
untouched. Judge reports display recorded practitioner reviews separately from automated scores;
conflicting reviews stay visible. Local reviewer attribution is not an identity-verification
service. A practitioner must still supply and take responsibility for their assessment.

## Research and runtime contracts

Both answering prompts require checks for rule, definitions, exceptions, applicability and
temporal evidence. Checks are explicitly model-reported, and evidence-found statuses require
actually delivered, sufficiently read citation keys. Missing, malformed and partial evidence
stays unresolved. Research is scoped to the actual question and its stated assumptions.
`missing_info` records an unanswered requirement; `missing_requirements` names it, and
`research_needed` distinguishes a gap that another corpus lookup could resolve from missing
user inputs or unavailable corpus evidence. Only required, retrievable gaps trigger automatic
research or the API loop's existing completion round. Optional background and unannotated date
metadata alone do not trigger more tools. Explicit current-law/date questions still require
relevant date evidence and visible qualifications; strict date filters remain unchanged.
Partially read cited passages still require a full read. Legacy records without the new decision
retain their previous fallback behavior. Call/turn/token reserves remain in force. The subscription CLI shares the checklist,
read-only tool contract and tool budget; its orchestration and cost cap remain controlled by
Claude Code. Equal tools do not imply identical model trajectories or token accounting across
transports. No complete legal-coverage guarantee is claimed.

SDK and MCP share argument validation and execution. SDK schemas live beside that contract;
MCP retains typed tool wrappers and its native protocol validation. Dispatched validation failures
consume budget, cancellation propagates, and error calls clear stale evidence delivery. Parallel
MCP requests serialize the shared toolbox so budgets and evidence traces cannot interleave. Parity scripts
cover truncated snippets, full reads, exhausted budgets and invalid arguments.

## Runtime review follow-up

The [13 November runtime review](review/REVIEW-FROZEN118-2026-11-13.md) adds bounded
same-article proviso reads, independent gap signals and targeted gap handoff on fallback.
These signals do not prove legal completeness. One format-only repair may run within remaining
question limits; it cannot add facts or tools. Answers that still cite partly read evidence
are withheld as unverified. Whole-unit definition qualifiers and ordinary bracketed placeholders
are preserved correctly. The CLI's tool/cost bounds remain distinct from the SDK loop's token
and turn enforcement.

Reported CLI usage now sums every model, including helpers. Output-format failures retain
their consumed tokens; unknown calls remain explicitly unknown. Judge reports distinguish
current-invocation tokens from immutable cumulative receipts. They include citation mappings
in both prompts and cache identity, and flag inconsistent raw scores for review. Defaults
are estimates, not spending caps; newly discovered gaps and repairs can add calls. Known
fallbacks from cached incomplete answers are included in the dry-run estimate.

## Codex and completeness follow-up — 14 November 2026

Claude subscription remains the default, Anthropic API is the implemented BYOK API, and Codex
subscription is opt-in through `config.codex.yaml`. Codex uses the shared in-process bounded loop;
its CLI supplies text and validated JSON tool requests. Native tool activity is rejected. Shared
tool semantics do not make provider trajectories, token accounting or grades directly comparable.

`answer/context_plan.py` adds bounded requested ranges, parent qualifiers and relevant sibling
provisions before drafting. It confirms availability of model-declared required quoted definitions;
`answer/research.py` feeds these findings into existing completion/fallback paths. Additional context
shares a four-row / 12,000-character allowance with proviso expansion. Existing source, date and
applicability restrictions remain binding; optional background does not become mandatory research.

The full frozen118 Codex run completed with 76 full / 26 partial / one wrong or unanswered in-scope
answer, and 15/15 out-of-scope refusals. Although mechanical checks averaged 99.0%, 22/26 graded
partial answers reported no missing information. `app-004` declares a required scope gap but does
not escalate to the indexed addressee text. These are open coverage/stopping limitations, not
unfinished corpus-publication infrastructure. See [findings](review/CODEX-FULL118-FINDINGS-2026-11-14.md).

The benchmark harness is `docs/review/run_codex_frozen118.py`, dry-run by default. Its isolated answer
cache prevents pilot reuse; explicit resume checks source/config/corpus/snapshot identity and
preserves completed work. The completed run consumed 5,776,251 known tokens plus one rejected
request with unknown usage. After its quota reset, the user explicitly resumed it. Preserve that
unknown receipt; elapsed overnight waiting is not active processing time. The old 8-million-token
approval applied to this completed run, not new evaluations. Estimate new calls and follow
`CLAUDE.md` before launching them. Do not resume the completed benchmark to test modified code.

## One local GPU owner

Start `uv run uvicorn reglens.inference:app --host 127.0.0.1 --port 8001 --workers 1`, then set
`REGLENS_INFERENCE_URL=http://127.0.0.1:8001` in every API/index/evaluation caller. RegLens passes
it to agent subprocesses. Clients send bounded embedding/reranking batches and load no models.
The default owner guard rejects a second service worker before model loading. Inference admits
four requests, executes one at a time, bounds queue wait to 30 seconds and returns busy/errors
explicitly. The client has a 90-second request timeout and accepts loopback HTTP origins only.
Service failures never silently start a duplicate GPU model in a caller. `/ready` reports pinned
identity; API `/api/ready` checks the live inference service and database. No network deployment
or user authentication for this loopback service is included.

A service rejects a different pinned model identity instead of mixing embedding spaces. To read
a generation built with another identity, run its corresponding pinned inference deployment or
use a direct local process with those models available. Direct local mode remains supported for
simple runs; it does not coordinate GPU ownership between processes. Shared inference is the
recommended mode for API plus agents. Generation retention uses disk, and serialized inference
limits throughput by design. An in-flight GPU operation finishes even if its HTTP caller leaves.

## Frozen evaluation and future holdouts

`uv run reglens eval-freeze` creates a content-addressed snapshot of verified development items
and their source registry under `evals/frozen/`. The original development snapshot contains 120
items. The source-reviewed 11 November revision contains 118; see
[GOLDEN-REVISION-2026-11-11.md](GOLDEN-REVISION-2026-11-11.md). `eval-answers --snapshot PATH` and `eval-route --snapshot PATH` use that snapshot (dry run
unless `--yes`). Every new answer run embeds frozen references and their hash; `judge --run ID`
uses them even if the working golden files later change. Run manifests are exclusively created.
Legacy runs explicitly fall back to current references because their original references were
not preserved. Historical headline scores were not changed.

Use `eval-freeze --input NEW_PUBLIC_QUESTIONS.jsonl --role holdout` for future verified questions.
It rejects overlap with normalized development questions or questions in local evaluation
history, and fails if history cannot be audited. It detects exact normalized overlap, not semantic
paraphrases, missing external history, or deliberate human leakage. Keep future holdout authors
and references independent; do not tune on their results. No existing development question was
relabelled as unseen, and no practitioner-authored holdout was fabricated.

Stable obligation IDs hash normalized substantive content, retaining previous IDs as aliases.
Reordering, new unrelated obligations and quote-window corrections preserve identity; a substantive
wording change creates a new identity that needs explicit human mapping if equivalence is intended.
Long-policy matching bounds selected evidence and records `policy_complete=false`. Candidate-only
absence/applicability results become unassessed; even positive findings remain visibly partial
policy assessments. This is bounded retrieval, not proof that the rest of the policy has no effect.

## Verification on 11 November 2026

- 170 tests passed, including five disposable-Postgres integration scenarios; no skipped database
  checks in the configured run. Ruff, frontend TypeScript and ESLint checks passed.
- Real shared GPU service: initial embedding request 3.76 seconds; two fresh concurrent client
  processes completed embedding plus reranking in 0.65 and 0.68 seconds. Neither imported PyTorch.
  Duplicate service ownership was rejected. The real API reported models and database ready.
- Six-question smoke: reranked recall@10 0.917 in 3.59 seconds. Full development retrieval: 103
  evaluable in-scope items, recall@5 0.745, recall@10 0.805, hit@10 0.913, total 64.40 seconds.
  Against original retrieval code at `5cb314b`, using the same corpus/models, all 103 top-ten
  lists and metrics were identical (baseline 60.04 seconds; timings are not a load benchmark).
  `cmp-002` was not evaluable against the current indexed expected reference. Out-of-scope and
  unverified questions are excluded by the existing retrieval evaluator. These are retrieval
  checks, not measurements of answer correctness or production load capacity.
- Strict requested-date filtering returned zero passages in the existing unannotated corpus,
  confirming that unknown legal intervals cannot pass strict validity checks.
- Runtime JSON evidence stays in local `data/evals/architecture-*.json` and
  `data/evals/inference-smoke.json`. No paid/subscription LLM calls were made.

Committed measurement summary: [review/architecture/checks.json](review/architecture/checks.json).
