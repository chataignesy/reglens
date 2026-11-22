# Fix verification — 9 November 2026

**Result: all seven findings from the second review pass their original failure-case checks. No remaining blocking defect was found in the changed paths exercised here.** This closes those specific reproductions; it is not a new overall answer-accuracy benchmark.

Reviewed the uncommitted changes on top of `86315c1beab378e3b33b9cd0f870b00d35c99442`. Application source was not edited by this review. Additional edits appeared during verification (including the import-order correction and a converter-version test); the final suite and lint checks were repeated. Initial and final diff hashes are recorded in [manifest.json](review/third-check/manifest.json).

## Findings rechecked

| Finding | Executed result | Status |
|---|---|---|
| S1: one window authorised unseen text | On the real EBA downturn-LGD paragraph 30, delivering 978 characters now produces exactly 978 characters of resolved context, with the passage marked partially read. It no longer expands to 4,677 unseen characters. Tests also cover every window delivered and truncated prefixes. | Fixed in tested cases |
| S2: SDK tools started after cancellation | The same in-flight cancellation response starts **zero** downstream tools. Cancellation propagates instead of becoming a tool-error message. | Fixed |
| S3: child survived parent cancellation | The real parent/child process reproduction now leaves **no surviving child**. Test helper cleanup is scoped to the probe's own process tree. | Fixed on Windows |
| S4: metadata changes reused corpus identity | In isolated temporary Postgres tables, metadata-only changes now change the corpus fingerprint. No public corpus table was updated. | Fixed |
| S5: alternative-range scoring mismatch | Retrieving only paragraph 72 of the accepted 72–73 alternative now earns **0.5 in both evaluators**. | Fixed |
| S6: historical answers graded against changed questions | Editing a question under the same ID now produces an explicit question-changed problem and **no judge call is scheduled**. | Fixed |
| S7: malformed gap verdict crashed parsing | `{"verdicts":[null]}` now produces **unassessed / invalid**, without crashing. Regression coverage includes scalar entries and malformed clause fields. | Fixed |

Evidence: [boundary.json](review/third-check/boundary.json), [third_checks.py](review/third_checks.py), and `tests/test_second_review.py`. The historical second-review runner was adapted to supply the new structured per-window delivery records and the new fingerprint API; previous evidence was not overwritten.

## Code and runtime checks

- **149 tests passed in 11.72 seconds** on the final healthy-database run.
- **Ruff passed**. An initial import-order error in `ingest/pdf.py` was corrected in the working tree during the check; the final check is clean.
- **Frontend ESLint and production build passed**, including TypeScript.
- Real HTTP checks passed: readiness in warmup-skipped test mode, gap-run listing, selected demo, and Excel endpoint.
- HTTP disconnect suppressed the malformed-output retry: **one provider call**, cancellation set, both question slots recovered.
- Admission control accepted two requests, rejected the third with **429**, then recovered both slots.
- Real Postgres/CUDA retrieval rerun covered **103 evaluable in-scope verified questions**, with one item excluded by the evaluator and out-of-scope questions excluded.

| Retrieval mode | Recall@10 | Warm median, nine observations |
|---|---:|---:|
| Lexical | 0.594 | 5.8 ms |
| Dense | 0.758 | 39.2 ms |
| Hybrid | 0.772 | 45.3 ms |
| Reranked hybrid | **0.805** | **345.9 ms** |

The retrieval quality and latency are consistent with the last check. Six reranked searches took 2.45 seconds serially versus 2.03 seconds with four workers; increased concurrency still trades higher per-request latency for a modest throughput gain. This is a small local performance sample, not a sustained-load measurement.

Evidence: [retrieval.json](review/third-check/retrieval.json), [http.json](review/third-check/http.json).

## Environment and limits

Docker Desktop and the existing RegLens container were initially stopped. They were started for the runtime checks; the existing database reported 4,631 chunks with 4,631 embeddings. Initial database connection attempts timed out before startup; the completed measurements above are from the successful rerun. A transient Windows sharing error loading a PyTorch DLL also disappeared on retry. These initial environment failures were not attributed to the application fixes.

The test HTTP server exited; Docker Desktop and the existing RegLens database were left running. Review artifacts were added, but application fixes were neither edited nor committed.

No new paid/subscription model calls were made. The four flagged smoke judgments still require practitioner adjudication, model-revision pinning remains deferred, and answer/prose semantic support is outside these mechanical checks. The latest code changes invalidate answer-cache namespaces; the earlier smoke result should not be presented as a fresh accuracy measurement of this exact working tree. A larger re-measure remains a separate budgeted activity.
