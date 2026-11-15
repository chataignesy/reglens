# Remaining handoff work

Personal project; not affiliated with an employer or supervisor. Not legal or regulatory advice.

The user requested the remaining handoff tasks after the completeness follow-up.

1. Add enclosing amendment introductions under the existing whole-unit/context budgets.
   Deliver them through single-pass expansion and get_passage, and independently require their
   citation when a claim uses an article number absent from the child. Keep mechanical number
   checks unchanged; use the existing context-only second draft when all evidence is delivered.
2. Add an opt-in `answer.routing: single_first` strategy. Preserve the current `llm` default,
   deterministic scope/retrieval gate, required-gap fallback, caller filters and usage accounting.
   No model inference should be used merely to select the single-first route.
3. Prepare a fixed 14-question paired development evaluation: latest code with the LLM router
   versus latest code with single-first. Both arms use fresh answers and frozen references.
   Cases: dod-005, pd-003, mh-006, cmp-001, cmp-002, app-001, lgd-007, val-001, lom-001,
   mh-012, oos-006, mh-014, app-004, irb-007. Compare omissions, contradictions, flags,
   citations, fallback, total route/answer/grade usage and active call time. Do not infer
   policy quality solely from agreement with question-type route labels.
4. Historical usage on these cases is 474,854 route+answer tokens for one arm. With grading,
   current completion/agent paths and two fresh arms, plan around 1.5M tokens with a 3M aggregate
   reserve. Reserve checks apply before every request; retain all attempts and stop on unknown
   usage/quota rejection. Live execution needs new approval under CLAUDE.md (>1M threshold).
5. Prepare artifact-bound practitioner packets for mh-006/mh-014 with source links, immutable
   hashes, competing scope interpretations and explicit pending decisions. Do not impersonate a
   practitioner, alter frozen references or retroactively change published grades.
6. Prepare a separate-author holdout intake and contamination protocol. Do not write questions
   informed by these failures and label them independent. An independent author/reviewer is an
   external prerequisite; no outreach or messages to others are authorized by this task.

Verification: failing targeted regressions, focused checks, full local suite with disposable SQL,
free actual-corpus amendment checks, then dry-run/approval/live paired evaluation. Keep configs
on LLM routing until paired evidence supports a separately recorded adoption decision.
