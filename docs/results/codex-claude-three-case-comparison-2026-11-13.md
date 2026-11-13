# Preliminary comparison of saved answers — 2026-11-13

Personal open-source project; not affiliated with an employer or supervisor; not legal advice.

This compares the three cases already executed. **It is not the proposed 30-question comparison,
which is awaiting token-budget approval.** No new model calls were made for this document.

| Case | Saved Claude result | Saved Codex result | What this shows |
|---|---|---|---|
| `mh-013`: CCF floor and required SA-CCF use | Empty final answer after 91,497 tokens | Substantive cited answer after 68,309 tokens; states drawn amount plus 50% of undrawn SA exposure value and required SA-CCF cases | Codex produced a usable answer in this attempt; the old empty-output failure is observable directly |
| `mh-014`: partly government-guaranteed retail mortgage | Identifies uncovered-part floors but says the covered-part outcome is unresolved; 41,346 tokens | Identifies Article 159a exemption for the covered portion and the uncovered-part floors; 47,570 tokens | Codex covered the core fact omitted by this Claude answer; it did not use fewer tokens in this case |
| `oos-006`: SEC-IRBA calculation | Says it cannot give the calculation but expands into neighbouring provisions and sets `abstained=false`; 9,314 tokens | Direct refusal, no model call | The scope guard improved the system's refusal behaviour; this is a code-path change, not evidence that Codex itself refuses better |

The two Codex answers were graded 2/2 by Codex and passed all mechanical claim checks. The old
Claude answers were graded by Haiku; the empty answer's zero and refusal failure are also
deterministically checkable. Different graders mean those original scores should not be used
as a clean model ranking. The planned comparison will apply a common grader to both sets.

Both Codex answers originally carried unnecessary neutral-reference warnings. A deterministic
replay now shows the dependency fix removes those warnings; no saved output or score was edited.
The next live run must check the broader behaviour again.

**Practical conclusion:** Codex subscription access worked for these cases and recovered two
previously failing examples. This does not establish overall model superiority. The model,
guard code and research workflow changed, only three cases were checked, and generation varies.

Evidence: [Claude full-run report](frozen-118-rerun-2026-11-13.md),
[Codex three-case report](../review/CODEX-SUBSCRIPTION-FOLLOWUP-2026-11-13.md),
[dependency replay](../review/dependency-scope-replay-2026-11-13.json),
[30-question plan](../review/CODEX-CLAUDE-SMOKE30-PLAN-2026-11-13.md).
