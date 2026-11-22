# Architecture implementation

Branch: `codex/architecture-foundations`, started 11 November 2026.

This table records the completed foundation milestone. The Q&A follow-up work has been merged;
see the [14 November handoff](archive/HANDOFF-2026-11-14.md) (archived). Foundation steps marked
done below do not imply that answer completeness is solved.

The target remains a local modular application using Postgres. Each step includes runnable
acceptance checks. Unknown legal dates/conditions remain unknown rather than being inferred.

| Step | Deliverable | Status |
|---|---|---|
| 1 | Staged immutable corpus generations, validated publication/rollback, pinned model revisions, readers pinned to a generation | Done: 3 disposable-Postgres integration checks; existing 149 tests pass |
| 2 | Stable obligation identities, compatible migration of existing references/results, bounded long-policy matching | Done: 752 IDs migrated with aliases; 15 planted gaps resolve; 14 focused tests pass |
| 3 | Provision-level temporal/applicability metadata and explicit query constraints with unknown-coverage reporting | Done: 6 metadata/date/database checks; frontend type check |
| 4 | Separate semantic evidence review and prose/claim alignment reporting; auditable practitioner adjudication | Done: opt-in review, strict response checks and hash-bound append-only practitioner records; 2 tests |
| 5 | Structured research checklist, evidence coverage, and targeted completion within the existing budgets | Done: five evidence-linked checks, unread/partial evidence rejected, targeted SDK completion bounded by existing limits; CLI instructions share checklist |
| 6 | Shared runtime tool contracts and parity scenarios for CLI/MCP and SDK paths | Done: common schemas/validation/execution, identical delivery/trace/budget parity scripts; 20 related tests |
| 7 | Shared local inference instance across API/MCP processes, bounded execution, explicit readiness | Done: loopback service, process owner guard, bounded queue, fail-closed model identity; 13 related checks and real two-process GPU smoke (0.65–0.68 s warm embed+rerank) |
| 8 | Frozen evaluation snapshots/holdouts, leakage checks, immutable adjudication and run provenance; documentation and final checks | Done: development snapshot, future-holdout overlap rejection, frozen judge references, reproducible answer evidence, 170 tests and real GPU/API/retrieval checks |

Code changes and offline/local-model checks are authorised by the implementation request.
Fresh paid/subscription evaluations are separate: estimate tokens first and respect the project
budget. Historical scores will not be relabelled as measurements of the new architecture.

Operation, migration and remaining limits: [ARCHITECTURE-OPERATIONS.md](ARCHITECTURE-OPERATIONS.md).

## Q&A follow-up status — 14 November 2026

| Work | Status and evidence |
|---|---|
| Codex subscription transport using the shared bounded tool loop | Implemented; Claude remains default; API keys still use the Anthropic adapter |
| Amendment source opt-in, requested ranges, parent qualifiers, relevant sibling paragraphs, available required definitions | Implemented in `50afa58`; bounded to four extra rows / 12,000 characters; filters and whole units preserved |
| Full frozen118 Codex runtime benchmark | Complete, documented in `107d254`; 86.4% mean, 76 full / 26 partial / one wrong or unanswered; 15/15 refusals; 247-test product baseline |
| Scope/addressee recovery for required applicability gaps | **Next — not implemented**; reproduce `app-004` without changing its reference |
| Broader completeness checks for conditions, components and exceptions | **Next — not implemented**; 22/26 graded partial answers did not report a gap |
| Nested amendment introduction and citation support | Queued after the two completeness tasks; retain `cmp-001`'s mechanical warning |
| Routing cost reduction | Later; 24.5% of known benchmark tokens, with quality-regression checks required |
| Rubric adjudication and independent holdout | Pending; tools exist, actual practitioner decisions and independent questions still needed |

That work started from the [handoff](archive/HANDOFF-2026-11-14.md) (now archived), reproduced the saved failures with
free local checks, settled the implementation design, and then made scoped fixes. The full
benchmark's code and reference artifacts remain historical evidence and must not be rewritten.
