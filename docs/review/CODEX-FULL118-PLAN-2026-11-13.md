# Full frozen118 benchmark with Codex

Personal project; not affiliated with an employer or supervisor; not legal or regulatory advice.

Status: completed on 14 November 2026 after a quota interruption and explicit resume.
All 118 questions graded; 5,776,251 known tokens plus one quota rejection with unknown usage.
See [results](../results/codex-frozen118-2026-11-14.md) and
[review findings](CODEX-FULL118-FINDINGS-2026-11-14.md).

- Product revision: `50afa58` on `codex/frozen118-followup`.
- Frozen dataset: `20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b`.
- All 118 verified questions: 69 factual, 23 multi-hop, 6 comparison, 5 applicability, 15 out of scope.
- Provider: Codex subscription; `config.codex.yaml`; `gpt-6.1-sol` for routing, answers and grading.
- Fresh Codex router decisions after the ordinary free scope/retrieval gate.
- Separate answer cache for this benchmark. No pilot answers reused; bounded fallback stays enabled.
- Grade all items against the unchanged frozen references. Preserve failed attempts and their usage.
- Record source/config/snapshot hashes, corpus generation, timing, usage receipts and original scores.
- Run the current code unchanged throughout. Publish a reviewable report after grading, including
  missing facts, citation issues, refusals, transport failures and comparisons with earlier results.
- Central estimate: 5.52 million tokens; planning range: 5–8 million. This includes routing, answers,
  grading and an allowance for fallback. `reglens estimate --model gpt-6.1-sol --input 20000
  --output 4000 --calls 230` reports 5,520,000 tokens; average-call assumptions are approximate.
- Proposed reserve: 8 million tokens. Stop before starting requests when their estimate exceeds the
  remaining reserve; a response can exceed its estimate. Stop on unknown usage or provider rejection.
- Project `CLAUDE.md` requires confirmation above 1 million tokens. The user confirmed this run's
  8-million-token reserve after reviewing the 5–8-million estimate, before live calls began.

Prepared harness: `docs/review/run_codex_frozen118.py`.
Dry run: `.venv/Scripts/python.exe docs/review/run_codex_frozen118.py`.
After confirmation: add `--live --budget 8000000`; requires the local database and inference service
on `127.0.0.1:18001`. Explicit resume accepts the saved comparison directory via `--resume` and
validates code/config/corpus/snapshot identity before reusing this benchmark's own completed work.

Verified during preparation: 118 verified items, 4,631 indexed chunks, database healthy, Ruff passed,
dry run made no model calls. The latest product verification remains 247 passing tests.
