# RegLens runtime, performance, and answer-verification review

8 November 2026. This review runs the actual application components, rather than inferring their behaviour only from source code. Application code was not edited by this review.

## Environment and snapshot

- Windows, Python 3.14.0; PostgreSQL 17.11 in the existing healthy Docker container.
- RTX 2070 SUPER, 8 GiB VRAM; real cached BGE-M3 and reranker weights on CUDA.
- 4,631 database chunks; all 4,631 have embeddings. No database reindex was performed.
- Retrieval measurements started at commit `f5edcaf59e89af724df622fc8503e9d2a714ab3c`.
- Other work changed and committed source files during the review; HEAD later became `d68249cc9121b46376e38a73ccdaf5af3cc0662c`, with a further routing change in the working tree. Those edits were preserved. Results describe the modules loaded for each process, not a certification of every subsequently edited file.
- Fresh generation used the configured subscription provider and models. Cached answers were not reused for the five-question sample. Estimated budget was 110k generation tokens plus 8k judge tokens; actual totals were **49,159 generation + 8,039 judging = 57,198 tokens**.

The [manifest](review/runtime/manifest.json), [runner](review/runtime_checks.py), and raw JSON artifacts record the measurements and judgments. No keys were added or copied into review artifacts. The local-model processes used cached weights with Hugging Face offline mode enabled.

## 1. Real retrieval quality and latency

Executed all four retrieval modes against the live database and all verified golden questions. The evaluator included **103 in-scope questions**, skipped **cmp-002** as not evaluable under its current reference normalisation, and excluded out-of-scope questions. Results use the existing evaluator; the citation-identity and denominator limitations described in the deeper review still apply.

| Mode | Recall@10 | MRR@10 | Full 103-question pass | Warm median / maximum |
|---|---:|---:|---:|---:|
| Lexical (`bm25` function) | 0.594 | 0.403 | 0.729 s | 5.6 / 8.5 ms |
| Dense | 0.758 | 0.637 | 4.941 s | 39.0 / 46.7 ms |
| Hybrid | 0.772 | 0.580 | 5.056 s | 44.1 / 48.2 ms |
| Hybrid + reranker | **0.808** | **0.725** | 35.141 s | **350.6 / 448.0 ms** |

Warm timings contain nine observations per mode: three questions (`dod-001`, `pd-002`, `mh-003`) repeated three times, k=10, 30 reranking candidates. This is a small local benchmark, not a p95/p99 service SLA. Model loading was excluded from warm timings. The lexical implementation uses PostgreSQL ts_rank, not the BM25 formula.

Interpretation: hybrid alone adds little latency, while reranking consumes most of retrieval time and improves recall. The sub-second retrieval path is suitable for an interactive local demo on this GPU. It is not the main source of the multi-second/minute answer delays.

The expanded harder set is a relevant comparison: phase2's 34 in-scope questions scored **0.765** reranked recall@10. Do not compare the combined 0.808 directly with the earlier 0.84 headline without matching the question set and corpus snapshot.

Evidence: [retrieval.json](review/runtime/retrieval.json).

## 2. Cold start, memory, and concurrency

Measured model construction: embedding model **14.76 s**, reranker **3.49 s**. The real HTTP pipeline with an instant fake generator took **22.50 s** for its first retrieval-bearing request in a process with warmup deliberately disabled. Subsequent requests took roughly **0.33–0.34 s** before accounting for real model generation. These cold numbers are process-level observations using cached files, not a fresh model download benchmark.

PyTorch reported **3,735 MiB peak allocated** and **4,152 MiB reserved** during retrieval. These exclude some CUDA/driver/desktop memory; an nvidia-smi observation showed approximately 5.6 GiB total GPU memory in use during the benchmark. CPU-only performance was not measured.

Six real reranked searches, separate database connections per worker, shared GPU models:

| Concurrent workers | Batch completion | Median request latency | Throughput |
|---|---:|---:|---:|
| 1 | 2.412 s | 0.367 s | 2.49 queries/s |
| 2 | 2.161 s | 0.706 s | 2.78 queries/s |
| 4 | 2.061 s | 1.238 s | 2.91 queries/s |

No errors occurred in this small concurrency sample. Four workers improved throughput by only about 17% while substantially increasing individual latency. This supports a small concurrency cap and shared model instances, rather than one unrestricted worker per request or several GPU model-loading server processes. It does not establish sustained-load stability or an OOM boundary.

## 3. Database query-plan and vector-filter checks

Compared normal vector-query results with an exact scan for three real question embeddings under default, LSI, and ECB-only filters: all nine comparisons returned 30 rows with complete overlap. Inspection showed the normal planner used scan/sort plans rather than the HNSW path for these small-corpus queries. Thus this result must not be described as proof of perfect ANN recall.

A separate controlled experiment forced the HNSW plan using transaction-local planner settings and an existing Article 178 embedding. Default and LSI searches returned 30/30 exact neighbours; the ECB-only filter returned **2 rows instead of 30**, with **2/30 overlap** against the exact result. There were enough eligible rows for the exact query to return 30.

This demonstrates a filtered-HNSW candidate-shortage risk if query planning changes as the corpus grows. It is not a demonstrated defect of today's normal exact-scan plan. Before relying on HNSW at larger scale, test filtered recall and consider iterative scanning, search breadth, filter-aware over-fetching, or an exact-search fallback. No persistent planner settings or database content were changed.

Evidence: [forced-hnsw.json](review/runtime/forced-hnsw.json). Normal plan summaries are in retrieval.json.

Measured reranker token truncation rather than assuming it was widespread: for a representative PD-floor query, only **2 of 2,648 default-scope chunks** exceeded the 1,024-token pair limit (maximum 1,118). On this snapshot it is a small exposure, not evidence of a broad truncation regression. Different/longer queries can change the result. Evidence: [tokenizer.json](review/runtime/tokenizer.json).

## 4. Real HTTP and export verification

Started Uvicorn on an isolated loopback test port, sent real HTTP requests, and shut that server down afterwards. The ordinary database and retrieval stack were real. Only the generator/provider boundary was replaced for the controlled error and disconnect scenarios; these timings are not paid-provider latency measurements.

| Check | Observed result |
|---|---|
| Health / metadata | HTTP 200 |
| Gap matrix | HTTP 200, 720 rows, approximately 468 KB |
| CSV export | HTTP 200, approximately 324 KB, 0.582 s including first export import overhead |
| Excel export | HTTP 200, 0.171 s; opened successfully with openpyxl, 721 worksheet rows including header |
| Missing API key | HTTP 400 |
| Too-short question / unsupported mode / >2,000-character question | HTTP 422 |
| Valid controlled reply | progress events then result; ordinary verified-format result |
| Malformed controlled reply | exactly one retry; final result marked `unverified=true`, with errors |
| Provider failure | SSE error event with the controlled message |

HTTP 200 for an established SSE connection is expected even when a later error event occurs; consumers must process the SSE event type rather than HTTP status alone.

**Disconnect defect reproduced with stronger evidence:** disconnected immediately after the first retrieval-progress event. The worker continued for about **2 seconds** and started **one additional provider call after the disconnect**, because the malformed response triggered its retry. Two provider calls occurred in total. This proves that aborting the client can leave both ongoing work and subsequent model calls running. Cancellation should stop retries and later tools/model calls, even if an already submitted request cannot be refunded.

Evidence: [http.json](review/runtime/http.json). The disconnect provider was fake, so this check incurred no real model charges.

## 5. Fresh model answers and judgment

Ran four real Quick questions and one routed question against the real corpus using the configured subscription provider. Then made four fresh reference-based bulk-tier judge calls; the out-of-scope case was graded deterministically. I also compared the answer text with the checked reference and inspected selected cited passages from the database.

Scores below use the project's rubric: 2 = covers the reference, 1 = partly correct, 0 = fails the task. These are checks against project references, not an independent legal opinion.

| Item | Mode | Wall time | Generation tokens | Manual reference-based judgment | Automated judge |
|---|---|---:|---:|---|---:|
| dod-001: definition of default | Quick | 30.87 s, including cold model loading | 6,286 | 2: covers the reference's two triggers | 2 |
| pd-002: retail PD floors | Quick | 8.08 s | 6,005 | 1: omits the defaulted-retail fact included in the reference | 2, with inconsistent explanation |
| scope-001: large-corporate definition | Quick | 6.64 s | 5,659 | 2: covers both reference criteria | 2 |
| oos-014: ICAAP concentration risk | Quick | 9.31 s | 7,406 | 0 for scope compliance: answered related material rather than abstaining | 0, deterministic |
| mh-003: downturn LGD | Routed → agent | 53.17 s | 23,803 | 1: explicitly incomplete; required reference details missing | 1 |

Observations:

- All **25 emitted claims passed the mechanical checks**, including those from the out-of-scope answer. A passing check is not evidence of completeness or correct scope handling.
- pd-002 contains the two floor values and higher-of rule, but not every fact demanded by the reference. This is an omission under that rubric, not a claim that the supplied floor values are wrong. The reference's required scope also deserves practitioner judgment.
- The fresh judge returned `score=2` for pd-002 while its rationale explicitly said that omitting the fact “should be 1 rather than 2.” Its machine-readable missing-facts list was empty. This is an actual **judge self-consistency failure**, not merely reviewer disagreement. Store and flag such inconsistencies and manually spot-check aggregate judgments; do not silently rewrite the raw verdict.
- mh-003 used only **two corpus tool calls** despite a ten-call allowance. It admitted it had not read the relevant RTS articles, that paragraph 30 was truncated, and that another necessary paragraph was not retrieved. The reference's duration and minimum-LGD details were missing. The model stopped early; it did not hit its tool-call limit. This reproduces the design concern that legal-basis/completeness instructions alone are insufficient stopping controls.
- oos-014 honestly stated that ICAAP was absent and gave related credit-risk material, but it still failed the project's strict out-of-scope abstention rule. Whether this response is useful and whether it passes the stated product contract are separate questions.

This deliberately selected five-question sample is too small and biased toward known risks to estimate overall accuracy. Do not replace the 120-question headline with a percentage derived from it. Its value is demonstrating concrete behaviour and checking whether verification signals distinguish the failures.

Evidence: [live.json](review/runtime/live.json), [judge.json](review/runtime/judge.json), and the manual labels in manifest.json.

## 6. Re-verifying fixes against the real database

- Every current database chunk has a stored citation key; zero rows have an empty key.
- The ambiguous legacy key `ECB validation reporting instructions para. 1` now resolves to no rows, rather than merging unrelated sections. That is the safe outcome for an ambiguous old label.
- Calling the real `get_article` with successive offsets retrieved **all 185 Article 4 chunks across seven pages**. Incomplete pages carried explicit continuation instructions; the last page was complete. This verifies the pagination fix against actual stored data, beyond the earlier mocked probe.

Evidence: [tools.json](review/runtime/tools.json).

## 7. Engineering checks and next actions

Initial suite at the start of this review: **99 passed**. After concurrent fixes landed, a final suite run returned **102 passed in 9.24 s**, with Ruff passing. Frontend ESLint and the production build, including TypeScript, also passed. Frontend build checks were run before the later Python-only edits.

Recommended priorities based on executed behaviour:

1. Propagate disconnect cancellation and suppress later retries/tool/model calls.
2. Make agent finalisation detect incomplete required reads and use remaining budget before returning; retain explicit partial-answer reporting when completion is impossible.
3. Calibrate and audit automated judging, including score/rationale disagreement and exact routed-run selection.
4. Keep scope compliance separate from claim support and answer completeness in reports and UI signals.
5. Add a small local inference concurrency cap and readiness/warmup visibility.
6. Protect filtered vector recall before changing corpus size or relying on HNSW query plans.

To rerun the main measurements:

```powershell
.venv\Scripts\python.exe docs/review/runtime_checks.py retrieval
.venv\Scripts\python.exe docs/review/runtime_checks.py http
# The following phases make fresh subscription-model calls and append to the usage ledger:
.venv\Scripts\python.exe docs/review/runtime_checks.py live
.venv\Scripts\python.exe docs/review/runtime_checks.py judge
```

Not performed: sustained high-load testing, CPU-only benchmarks, real BYOK/Anthropic SDK billing-path tests, an independent legal-source freshness audit, a fresh 120-question paid answer benchmark, or new policy-gap matching/extraction runs. Saved gap reports and exports were exercised; that does not independently validate the 752 extracted obligations. Existing user database/container processes were left running; the review's temporary HTTP server exited.
