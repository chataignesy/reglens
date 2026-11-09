# Second review: design, code, and runtime

Reviewed commit **8a1a7bfd369fd0eaa8cbb84514a95095b5be76ed**, 8 November 2026. The worktree was clean at the start and application source remained unchanged throughout this pass. Added only review code and artifacts.

## Conclusion

The fixes substantially improve RegLens. Run manifests now identify real answer artifacts; citation labels reject ambiguous legacy references; article pagination is explicit; malformed answers are visibly unverified; the ordinary HTTP disconnect/retry path cancels correctly; admission control and filtered vector retrieval work in the tested scenarios. The documentation now distinguishes historical benchmarks from the post-fix smoke measurement.

However, **evidence delivery still operates at citation-key granularity rather than chunk/window granularity**. That leaves a P1 gap in the central guarantee. There are also remaining cancellation and evaluation-integrity defects. I would not yet mark all earlier findings fully closed.

## Executed verification

| Check | Result |
|---|---|
| Python tests | **133 passed in 11.76 s** |
| Ruff | Passed, including the new review runner |
| Frontend ESLint / production build / TypeScript | Passed |
| Live Postgres + CUDA retrieval, all four modes | 103 evaluable verified questions; reranked recall@10 **0.805** |
| Warm retrieval, nine observations per mode | Median lexical **5.9 ms**, dense **40.2 ms**, hybrid **44.9 ms**, reranked **335.3 ms** |
| Forced HNSW, former ECB-only shortage case | **30/30** rows and full overlap with exact search; ef_search=400, iterative_scan=relaxed_order |
| Real HTTP disconnect with controlled provider | One provider call; retry suppressed; both capacity slots recovered |
| Real HTTP admission control | Two accepted requests, third HTTP **429**; slots recovered |
| Readiness / run listing / selected demo / Excel endpoint | HTTP 200 in test mode with model warmup explicitly skipped |
| Fresh subscription Quick answer, pd-002 | **27.84 s including cold loading**, **5,984 tokens**, valid result, **5/5 mechanical checks** |
| Existing post-fix smoke run | All 30 answer artifacts matched their manifest SHA-256 values |

Used the existing healthy Postgres database and RTX 2070 SUPER. Retrieval remained sub-second warm and showed similar GPU contention to the first runtime review: six searches completed in 2.34 s with one worker versus 2.01 s with four, while individual latency increased. This remains a small local test, not a sustained-load SLA.

Full retrieval results are in [retrieval.json](review/second-check/retrieval.json), HTTP results in [http.json](review/second-check/http.json), HNSW results in [hnsw.json](review/second-check/hnsw.json), and the fresh answer in [live.json](review/second-check/live.json). Boundary reproductions are in [second_checks.py](review/second_checks.py) and [boundary.json](review/second-check/boundary.json).

The historical runner's retrieval function was reused with its output directory redirected to `docs/review/second-check`; previous review artifacts were not overwritten. Boundary tests use real local passages and isolated temporary database tables where noted. No public corpus tables were modified. The test HTTP server was shut down and the subprocess probe's child was explicitly cleaned up.

## Remaining findings

### S1 — P1: One delivered window still authorises the complete passage

Locations: `src/reglens/agent/run.py:165–181`; `src/reglens/agent/tools.py:119–132`, `:176–187`.

The delivery guard checks whether the *citation key* was received. All windows of one logical passage share that key. `_resolve` then reads and merges every window from the database. `partial_reads` also treats any untruncated occurrence of the key as a complete read, even if it was only a short final window.

**Real-corpus reproduction:** EBA GL downturn LGD paragraph 30 has two rows. Deliver only its shorter **978-character** row using the actual output formatter. The trace contains the citation key and no truncation marker. Final resolution produces **4,677 characters**, maps the key to C1, and `partial_reads` returns an empty set. Thus material the model never received becomes verified context, and R1's completeness check is bypassed.

This is not the original wholly-unseen-key issue: that guard now exists. It is the remaining window-level version of the same problem, on a default-scope passage directly relevant to the earlier downturn-LGD example.

**Fix:** retain structured delivered chunk/window IDs and coverage, not only regex-extracted keys. Resolve/check claims against exactly the delivered text, or require every necessary window before treating the logical unit as fully read. Distinguish partial snippets, complete windows, and complete legal units. Regression: return only the final window, then assert unseen text cannot contribute numbers or a full-read status.

### S2 — P2: SDK cancellation still permits tools to start after disconnect

Locations: `src/reglens/agent/api_loop.py:241–251`; `src/reglens/llm/provider.py` API response handling; `src/reglens/api/app.py` progress emitter.

The API provider checks cancellation before submitting a request. But if cancellation happens while that SDK call is in flight, the returned tool-use blocks are executed without another check. The progress emitter drops events rather than raising cancellation, so it does not stop the loop.

**Reproduction:** a fake SDK response sets the real CancelToken before returning two search tool-use blocks. The real API loop starts **both searches after cancellation**. Only the next model request notices cancellation. No remote call was made in this probe.

**Fix:** check cancellation immediately after provider return and before each tool, completeness continuation, and finalisation. Propagate `Cancelled` rather than turning it into an ordinary tool error. Keep the documented allowance for an already submitted SDK request to finish; prevent new downstream work.

### S3 — P2: CLI cancellation kills only the direct process

Locations: `src/reglens/cancel.py:64–69`.

`proc.kill()` stops the direct subprocess, but does not establish a process-tree termination contract. The CLI agent starts an MCP child process, so direct-process cancellation alone cannot guarantee release of all its resources.

**Runtime reproduction:** run the actual cancellable runner against a Python parent that starts a sleeping child. Cancel the token; the parent stops, but the child remains alive. The review explicitly killed its own surviving test child afterwards. This demonstrates the runner defect; it is not a claim that an actual Claude/MCP process was observed leaking in this pass.

**Fix:** use an appropriate Windows process group/job object or verified descendant cleanup, and the corresponding process-group strategy on other platforms. Test that the direct process and its descendants all exit on cancellation and timeout. Avoid killing unrelated processes by executable name.

### S4 — P2: Corpus fingerprints ignore answer-changing metadata

Location: `src/reglens/eval/fingerprint.py:51–69`.

The corpus digest includes chunk IDs, text hashes, citation keys, and edges. It excludes `applies_to`, `legal_level`, `version`, and `kind`, even though those affect retrieval inclusion, source classification, or answer dates. Correcting that metadata can therefore reuse an answer generated from the previous metadata.

**Live Postgres reproduction:** create temporary tables shadowing `chunks` and `edges`, copied from two real rows. Change only applicability, legal level, and version. Clear the in-process fingerprint cache before each measurement. The digest remains **f25378a0016a** before and after. Clearing the cache demonstrates that the problem is missing digest inputs, not just memoisation. User tables were untouched.

**Fix:** fingerprint all answer-relevant corpus and registry metadata, plus vector/model identity as appropriate. Tie memoisation to a known immutable generation or invalidate it on refresh. Test metadata-only updates as well as text/edge changes.

### S5 — P2: Retrieval evaluation still flattens alternative ranges

Location: `src/reglens/eval/retrieval.py:77–104`; compare `src/reglens/eval/citations.py:43–60`.

The new answer-level matcher correctly represents alternatives as OR over complete AND-groups. Retrieval evaluation still expands every alternative range member into an independent acceptable hit for each original reference member.

**Reproduction:** expected paragraph 71, with accepted alternative paragraphs 72–73. Return only paragraph 72. Answer-level credit is **0.5**, but retrieval recall@10 is **1.0**. Neither the original reference nor the complete alternative was retrieved.

**Fix:** have retrieval evaluate the same structured groups as answer-level evaluation, including the rank at which required members become available. Avoid separate normalisation/matching implementations. Recheck affected benchmark items; this probe does not establish how much the current aggregate score changes.

### S6 — P2: A historical run can be graded against a different question

Locations: `src/reglens/eval/judge.py:94–139`, `:150–175`; `src/reglens/eval/answers.py` manifest entries.

Artifact hashes now protect the answer bytes, but judge planning matches current golden items to a historical run by ID without verifying its stored `question_sha`. If a question is edited under the same ID, the old answer can be judged as if it answered the new question.

**Reproduction:** load the real post-fix smoke manifest, replace pd-002's question text in memory with an unrelated question, and call `plan`. It schedules a new judge call with **no problems reported**. The old answer's bytes remain valid, but the question/answer pair is no longer the one the run executed. No judge call was made.

**Fix:** validate question identity against the manifest and preferably store an immutable golden-set snapshot with the run. Reject question drift by default. If reference corrections are intentionally allowed for historical regrading, record that as a distinct regrade version rather than silently treating it as the original run.

### S7 — P2: Malformed gap verdict entries can still crash the batch

Location: `src/reglens/gap/match.py:148–152`, and `match`'s exception handling.

`v.get(...)` runs before the `isinstance(v, dict)` guard. A parseable reply such as `{"verdicts":[null]}` raises AttributeError instead of becoming an unassessed/invalid verdict. The surrounding matcher catches ValueError and JSONDecodeError, so it does not recover from this case.

**Reproduction:** pass that reply to the real parser; observed `AttributeError: 'NoneType' object has no attribute 'get'`.

**Fix:** validate the top-level verdict collection and each entry before accessing fields. Invalid entries and field types should become explicit unassessed outcomes without aborting the run. Add null, string, scalar, and malformed clause-list cases.

## Design assessment and status of earlier findings

The architecture is moving in the right direction: shared dispatch, immutable answer artifact checks, explicit UI signals, and per-question cancellation are sensible for a local MVP. The main residual design problem is that evidence completeness is still inferred from rendered strings instead of a structured coverage record (S1). Evaluation metadata similarly needs a complete identity contract (S4–S6).

| Earlier area | Second-check assessment |
|---|---|
| Parser paragraph ownership, definition qualifications, collision-safe citation labels, article pagination | Implemented with regression coverage; no new defect established here in those fixes |
| Entirely unseen agent citations | Guard added; **window-level delivery remains open (S1)** |
| Answer schema / honest mechanical-check labels / explicit incomplete state | Implemented; semantic support and prose-to-claims alignment remain explicitly deferred |
| PDF and extraction provenance | Content hashes and manifests added; fixture coverage passes. Converter version is recorded but not compared on cache reuse, so converter-upgrade reproducibility is still incomplete |
| Run artifact selection and hashes | Real smoke artifacts verified; **question identity and metadata cache inputs remain open (S4, S6)** |
| Citation range/part scoring | Answer-level grouping corrected; **retrieval alternative-range path remains open (S5)** |
| HTTP cancellation and two-slot admission | Ordinary disconnect/retry scenario verified; **SDK tools and process-tree edges remain open (S2, S3)** |
| Failed CLI usage accounting / standalone MCP lifetime | Implemented with passing regression tests; no real paid failure was deliberately induced |
| Filtered vector candidate shortage | Previously failing forced-HNSW case now returns 30/30 exact matches |
| Gap run selection / partial recall / empty evidence | Corrected paths and clearer UI; **malformed entry recovery remains open (S7)** |
| Judge inconsistency detection | Four real smoke verdicts are flagged, and raw verdicts retained. Detection works; practitioner adjudication remains outstanding |
| Scope vs completeness vs mechanical signals | Separated; these are observable output signals, not an independent semantic scope classifier |

## Quality and cost observations

The fresh Quick pd-002 result covers the two floor values, higher-of rule, and guarantee exception. It still omits the defaulted-retail fact required by the project's golden reference, just as the flagged smoke verdict notes. All five emitted claims pass mechanical checks. This is reference-based completeness feedback, not an independent legal determination or a claim that the stated floor values are wrong.

I inspected all four flagged smoke verdicts. pd-002 lists a missing reference fact despite score 2. mh-002 places text it expressly calls *not a contradiction* in its contradictions field. mh-006 records genuine missing reference topics and remains partial. mh-007 calls the answer marginally incomplete despite score 2. Retaining flags is correct; the raw 0.90 smoke score should remain qualified until these are adjudicated. Do not automatically downgrade every flagged contradiction: some are judge field-classification errors rather than wrong answers.

The documented 1.70M-token smoke cost is about 2.5 times its estimate, with no measured improvement over the earlier smoke correctness. That is a disclosed, still-open product tradeoff, not evidence that the fixes should be removed. Prefer targeted missing-unit fetches, avoiding whole-article rereads, and evaluating quality per token before reducing call limits indiscriminately. Correct S1 before tuning completeness behaviour around its current false full-read signals.

The deferred stable obligation IDs, register rebuild/re-match, staged corpus publication, vector model revision tracking, temporal modelling, held-out tests, and semantic claim checks remain legitimate roadmap work. They are not completed merely because the numbered review-fix steps are marked done. In particular, the current gap demo remains internally consistent historical output rather than a freshly rebuilt obligation register under every parser change.

## Recommended next actions and limits

1. Fix S1 with chunk/window-level evidence coverage and tests built from the real paragraph-30 reproduction.
2. Finish cancellation at SDK tool and process-tree boundaries (S2–S3).
3. Complete evaluation identity and shared scoring logic (S4–S6).
4. Make malformed gap output conservative rather than fatal (S7).
5. Adjudicate flagged smoke verdicts, then make a small targeted re-measure before considering another expensive full evaluation.

No full fresh model benchmark, real Anthropic BYOK request, sustained-load test, new policy matching run, independent legal audit, or fresh browser accessibility walkthrough was performed. The fresh subscription request used **5,984 tokens**; all other new checks were local/offline or used existing smoke artifacts. Default public corpus contents were left unchanged. These scope limits do not affect the concrete reproductions above, but prevent treating this report as production certification.
