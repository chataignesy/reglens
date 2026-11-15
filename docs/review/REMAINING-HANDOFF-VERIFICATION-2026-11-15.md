# Remaining handoff work: verification and decisions

Personal project; not affiliated with an employer or supervisor. Not legal or regulatory advice.

## Completed technical work

The amendment-introduction fix is implemented in shared evidence planning and `get_passage`.
It selects an actual enclosing point whose text establishes the amendment target, preserving
whole logical units, source/paragraph identity and caller filters. It shares the existing
single-pass context budget. A claim using a number absent from the child must also cite the
delivered introduction; an unread introduction still requires targeted reading. Context-only
citation repair shares the existing two-call draft limit. Mechanical number checks are unchanged.

The real-corpus check reproduces the `cmp-001` issue with Article 1(86)(a): the child alone
leaves 160 unsupported, whereas citation of the actual Article 1(86) introduction resolves it.
Both fresh live answers now receive full credit and pass the strict mechanical checks.

An opt-in `answer.routing: single_first` policy bypasses router inference while preserving the
normal scope/retrieval gate, caller filters, required-gap fallback, error handling and usage.
It is supported by runtime answering and CLI/evaluation routing; deterministic policy routes
never reuse LLM route-cache decisions. Answer cache identity includes the configured strategy.
The default remains `llm`; neither tracked default configuration was switched to the candidate.

**272 local tests pass**, including disposable Postgres checks. New regressions exercise
amendment context/delivery, strict number support, context budgets/filters, router-call avoidance,
required-gap handoff and cache separation. Ruff and whitespace checks pass. The
[free audit](remaining-handoff-local-2026-11-14.json) checks all 118 frozen policy routes and
the actual amendment structure; it is a pre-run diagnostic, not an answer-quality measurement.

## Broader paired verification

The user approved a fresh paired 14-question experiment with a **3M total token reserve**.
Both arms use identical frozen questions/references, product code, corpus and Codex model,
with isolated fresh answer caches. The cohort includes the main completeness cases, adjacent
controls, both practitioner-review cases, comparisons and one refusal control.

[Full comparison, answers and audit](../results/handoff-routing14-2026-11-15.md):

| Result | LLM routing | Single-first |
|---|---:|---:|
| In-scope automated mean | 92.3% | 88.5% |
| Full / partial / wrong | 11 / 2 / 0 | 10 / 3 / 0 |
| Correct out-of-scope refusal | 1/1 | 1/1 |
| Routing + completed answer tokens | 609,457 | 316,536 |
| Known total tokens including grading | 787,814 | 499,640 |

Single-first uses 48.1% fewer routing/answer tokens on these trajectories. It has one lower
governance grade. Both governance answers actually used single-pass plus a context-only rewrite,
so one sample does not establish routing as the cause; nevertheless quality equivalence is not
demonstrated. **Decision: retain LLM routing as default; keep single-first explicitly opt-in.**

Known total experiment usage is **1,287,454 tokens**, plus one quota-rejected request whose usage
is unknown. The LLM arm stopped immediately on quota rejection and was explicitly resumed by the
user on 15 November. Completed answers were reused within that same run. Every rejected request,
model-call record, usage receipt and answer attempt remains available; source identities match
and no product code changed during either arm. Known usage is a lower bound, not proof the rejected
request cost zero. Both arms' mechanical mean is 100%, yet silent partials remain.

These are automated, unreviewed development scores on one trajectory per arm. The full118 result
remains its original 86.4% baseline; no full rerun, independent holdout or practitioner sign-off
is implied. Given the remaining omissions and absent independent review, a new full run is
deferred rather than launched under the focused-run approval.

## External work deliberately pending

At the user's explicit request, independent practitioner review and separately authored holdout
questions remain pending. The technical preparation is complete:

- [Practitioner request](PRACTITIONER-REVIEW-REQUEST-2026-11-14.md) and
  [artifact-bound packet](practitioner-packets-2026-11-14.json): exact original questions,
  references, answers, grades, hashes, source fingerprints and proposed scope distinctions.
  All source references resolve. No practitioner identity or decision has been fabricated.
- [Holdout author brief and intake](../../evals/holdout/README.md), with a provenance template,
  separation/reveal protocol and existing normalized-overlap/freeze commands. No questions
  authored from the known failures have been falsely labelled independent.

No external outreach was sent. Historical references, receipts, answers and published scores were
not rewritten. The database remains available; the benchmark-owned inference service is stopped.
