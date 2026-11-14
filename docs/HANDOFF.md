# RegLens handoff — 14 November 2026

Personal project; not affiliated with any employer or supervisor. Not legal or regulatory advice.

## Start here

The full frozen118 Codex benchmark is **complete**. The user requested this documentation/handoff
update and intends to open a new session for the fixes. This documentation session makes no
product changes or model calls. The next session should work on **scope/addressee recovery and
answer completeness**, then verify a small focused set. Settle the implementation design before
coding; the direction below is a handoff, not a claim that those fixes are already implemented.

Workspace: `C:\Development\RegLens`. Shell: PowerShell. Branch: `codex/frozen118-followup`.

- `d8c8b40`: latest measured product code, bounded context/completeness helpers.
- `482d52e`: completed full Codex benchmark, exporter, audit and findings.
- This handoff and the accompanying architecture/roadmap updates form the next documentation
  commit; check `git log` and `git status` rather than assuming the checkout has not changed.
- An untracked `.codegraph/` directory belongs to the existing workspace. Leave it intact.
  Follow the user's CodeGraph-first instructions when locating code. Its index predates some
  recent helpers; if it cannot find a file or reports drift, inspect the current source directly.
- Read `CLAUDE.md` and applicable `AGENTS.md` instructions before work. Public sources only;
  no employer material, no secrets, no model calls from unit tests.

## Read these first

1. [Full-run findings and priorities](review/CODEX-FULL118-FINDINGS-2026-11-14.md).
2. [Full results](results/codex-frozen118-2026-11-14.md), then selected records in
   [all answers/grades](results/codex-frozen118-2026-11-14.json). Process the large JSON locally;
   do not load the full corpus or entire answer dump into model context.
3. [Current design](DESIGN.md), [operations](ARCHITECTURE-OPERATIONS.md), and
   [roadmap](ROADMAP.md). The dated current sections supersede historical performance examples.
4. [Integrity audit](review/codex-full118-audit-2026-11-14.json) and
   [earlier implemented fixes](review/COMPLETENESS-FOLLOWUP-2026-11-13.md).

## Baseline and immutable evidence

| Item | Completed baseline |
|---|---|
| Frozen development snapshot ID | `20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b` |
| Frozen file | `evals/frozen/20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b.json` |
| Full run | `20261114-090457-612837-routed-codex-full118` |
| Full run manifest | `data/evals/runs/20261114-090457-612837-routed-codex-full118.json` |
| Run records / receipts | `data/evals/comparisons/20261113-224005-859471-codex-full118/` |
| Final raw result | `result-20261114-081359-431720.json` in that directory |
| Dataset | 118 verified development questions: 103 in scope, 15 out of scope |
| Mean score | 86.4%; 76 full / 26 partial / one wrong or unanswered; full-credit rate 73.8% |
| Refusals | 15/15 correct |
| Citation-group recall / mechanical checks | 85.8% / 99.0%; neither proves completeness |
| Silent partials | 22/26 answers graded partial did not set `missing_info` |
| Usage | 5,776,251 known tokens; one quota-rejected request has unknown usage |
| Judge | `gpt-6.1-sol`, prompt version `75d32dd9`; automated, no practitioner sign-off |
| Last product verification | 247 tests passed, including disposable Postgres integration checks |

The snapshot ID is the canonical payload identity; its on-disk file hash is separately recorded
in the audit. Preserve both meanings. The run was interrupted by a Codex subscription limit,
then explicitly resumed after the reported reset. All 118 routes and the first 45 answers were
reused from this run, with no pilot-answer reuse. All 119 answer-attempt artifacts were verified.
Grading used 100 new model calls, three exact-content cached verdicts and 15 deterministic refusals.

Do not rewrite the frozen references, old manifests, answers, receipts, grades or published reports
to demonstrate improvement. New code needs new run artifacts. This is a development set already
used for fixes; new paraphrases of it are also development tests, not an independent holdout.

## Already implemented — do not redo

- Staged corpus publication/rollback, query constraints, provenance and frozen-evaluation tooling.
- Shared local inference and shared tool validation/trace contracts.
- Required-answer checklist and bounded completion/fallback paths; opt-in semantic review.
- Codex subscription adapter, alongside default Claude subscription and Anthropic API support.
- Registry-driven amendment source opt-in for explicit change queries; caller restrictions win.
- Small requested paragraph ranges, parent qualifications and relevant parallel paragraphs.
- Availability checks for model-declared required **quoted definitions**, including bounded plural
  fallback. This guard recovered the maturity definition in the full run (`mh-015`, full credit).
- Context additions share **four extra rows / 12,000 characters** with existing proviso expansion;
  preserve whole units and source/date/institution/applicability constraints.

An opt-in review or a checklist is not independent proof of entailment or coverage. The current
guards cover selected patterns; broader stopping/completeness limitations remain open.

## Fix first: required scope/addressee evidence

Reproduce `app-004`: “Do the EBA guidelines on the definition of default apply to less significant
institutions?” The current answer says its passages cannot establish applicability and reports
missing scope text, but remains on a single-pass route. The frozen rubric gives zero for failing
to answer; it is not an affirmative false legal claim. Indexed scope/addressee paragraphs exist:

- `eba-gl-dod:paragraph:b0:7:`
- `eba-gl-dod:paragraph:b0:8:`

The actual context instead contains technical paragraphs 86/88/94 and ECB material. The earlier
30-case Codex answer got full credit after an agent fallback; the current valid-looking single
answer stops too soon. A missing required scope fact needs a bounded availability/read/escalation
path. Confirm the exact implementation from code and saved records rather than copying the answer
or hard-coding a question ID, paragraph number or legal conclusion.

Preserve legitimate missing user inputs and genuinely absent corpus evidence. An `applies_to`
registry label is a filter/coverage annotation, not a substitute for cited legal scope text.

## Fix next: completeness across requested facts

Representative development failures are cure conditions (`dod-005`), validation requirements
(`val-001`), governance responsibilities (`lom-001`), realised-loss components (`mh-012`), and
maturity exceptions (`irb-007`). The full report lists all 27 non-full-credit outcomes.

Develop bounded coverage checks for requested conditions, components and exception lists. Use
source structure and explicit answer requirements, not just whether existing claims have citations
or whether the model self-reports a gap. Optional background and unasked classifications must not
trigger indiscriminate research. A finite probe can identify available evidence; it cannot certify
that no other legal exception exists. Record unresolved requirements honestly when bounds are hit.

The concrete design is for the next session to settle. Keep the current modular Postgres/tool
architecture and existing budgets; there is no demonstrated need for a new database, provider,
unbounded agent or separate paid judge on every answer.

## Code and test entry points

| Path | Role |
|---|---|
| `src/reglens/answer/context_plan.py` | Requested units, bounded expansion, available required definitions |
| `src/reglens/answer/research.py` | `guard`, gap decisions, completion hints, proviso expansion |
| `src/reglens/answer/pipeline.py` | Single-pass retrieval, expansion, drafting and guard integration |
| `src/reglens/answer/route.py` | Shared dispatch, required-gap handoff, fallback and usage aggregation |
| `src/reglens/agent/api_loop.py` | Bounded API/Codex tool loop and pre-final completeness nudge |
| `src/reglens/agent/run.py` | Agent context resolution, delivery checks and post-answer guard |
| `src/reglens/agent/tools.py` | Filtered whole-unit reads, definitions and trace coverage |
| `src/reglens/retrieve/intent.py` | Original-question source opt-ins and explicit caller scope |
| `src/reglens/eval/fingerprint.py` | Update answer-affecting cache identity for any new helpers |
| `tests/test_context_completeness.py` | Current bounded-context regressions |
| `tests/test_scoped_research.py`, `tests/test_dependency_scope.py` | Avoid optional/unresolvable research and unnecessary escalation |
| `tests/test_frozen118_followup.py`, `tests/test_generations.py` | Fallback/provenance and disposable database scenarios |

Inspect existing contract/schema/prompt fields before adding overlapping representations. Agent
citations use corpus keys during research and become `C#` keys after resolution; coverage must
be based on actually delivered whole windows, including passages read but not finally cited.
Apply fixes consistently across single, routed and shared API/Codex paths, preserving Claude/MCP
tool contracts. Do not promise identical model trajectories across transports.

## Verification sequence for the new session

1. Check branch/status and inspect the saved failures. Add failing local regressions using real
   structural examples and filtered mock/SQL scenarios. No model calls are needed to reproduce the
   indexed-but-unread scope gap.
2. Implement the agreed bounded design. Verify whole-unit delivery, source/part ambiguity, explicit
   restrictions, dates/institution constraints, missing user inputs, optional checks and budget caps.
3. Run focused tests, then the full local suite with disposable Postgres checks. Example commands:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_context_completeness.py tests/test_scoped_research.py tests/test_dependency_scope.py -q
.venv\Scripts\ruff.exe check src tests

# Requires the local test database service; creates/drops disposable test databases.
@'
import os, pytest
from reglens.index.db import DEFAULT_URL
os.environ['REGLENS_TEST_ADMIN_URL'] = DEFAULT_URL
raise SystemExit(pytest.main(['-q']))
'@ | .venv\Scripts\python.exe -
```

4. Use free SQL/retrieval checks against the real corpus. Add new development variations and adjacent
   topics so the test does not simply reward memorising the known failures. Record specificity as
   well as recovery: available optional text must not automatically cause more calls.
5. Estimate a small focused Codex answer-and-grade run before live calls. Include routing, all agent
   turns, repairs/fallback and grading. Even a small cohort can exceed 1M tokens; do not assume it
   is under the threshold. Use new labels/namespaces and retain unsuccessful attempts.
6. Compare scores, missing-fact lists, gap flags, citation checks and token/time costs. Only after
   focused evidence warrants it, propose a fresh full benchmark with a new estimate/approval.

## Runtime and budget reminders

- Python environment: `.venv\Scripts\python.exe`. Database service: `docker compose up -d db`.
- The database was left running after the benchmark. The benchmark-owned inference processes on
  port 18001 were stopped. Check current state before starting a new process; do not assume a
  service is still up or start duplicate GPU owners.
- Shared inference example: `.venv\Scripts\python.exe -m uvicorn reglens.inference:app --host
  127.0.0.1 --port 18001 --workers 1`; callers need
  `REGLENS_INFERENCE_URL=http://127.0.0.1:18001`. Start background services hidden on Windows.
- `config.yaml` remains Claude by default; select `config.codex.yaml` explicitly for Codex tests.
  API support is Anthropic-only; this project does not have a generic LLM API adapter.
- The full run's 8M-token approval is **completed-run scope**, not a standing budget for new
  evaluations. Follow `CLAUDE.md`: state estimates, confirm above 1M, free checks first. Subscription
  quota is separate from that budget. Stop on quota rejection/unknown usage and preserve receipts.
- Do not resume the completed full-run directory after code changes. The harness should reject a
  revision mismatch; use new artifacts. `run_codex_frozen118.py` is for a fresh full benchmark,
  not a cheap targeted test.

## Later work — keep separate from the first fixes

`cmp-001` still has `unsupported_number(160)` because the cited nested amendment text lacks its
enclosing introduction. Routing used 24.5% of known tokens. Both deserve follow-up after coverage
behaviour is verified. Practitioner adjudication of `mh-006` / `mh-014` and a separately authored
holdout remain pending; do not silently relax reference answers to raise the score.

## Suggested opening message for the new session

> Read `docs/HANDOFF.md` and the linked full-benchmark findings. Reproduce the scope/addressee gap
> and silent completeness failures, settle a bounded implementation design, then implement the
> first two fixes and verify them locally. Keep frozen references and past results unchanged.
> Estimate a small focused Codex evaluation before any live calls; do not launch a full rerun yet.
