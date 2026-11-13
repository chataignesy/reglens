# Review and implementation — frozen-118 runtime findings

Date: 13 November 2026. Baseline: `506d334`, answer run
`20261111-230849-885073-routed-all`, frozen development set `24da390d…`.
Personal open-source project; not affiliated with an employer or supervisor; not legal advice.

The complete baseline and raw verdicts remain in
[the runtime report](../results/frozen-118-full-2026-11-13.md). The 84.0% raw mean is provisional:
10 verdicts have consistency warnings and source checks exposed additional grading problems.
No retrospective improvement to that score is claimed.

## Findings and acceptance criteria

| ID | Priority | Finding / examples | Required change | Status |
|---|---|---|---|---|
| R1 | P1 | Judge cannot resolve C1/C2; contradictory verdicts; `sa-004` reference omits Article 123(4) | Supply bounded citation evidence and include it in cache identity; validate verdicts and label disputed scores provisional; clarify working reference and create a new development freeze | Implemented; historical verdicts triaged, not re-scored |
| R2 | P1 | Required research stops early (`mh-015`, `mh-012`, `mh-003`) | Bounded retrieval of explicit provisos; code checks for unread decisive dependencies and admissions of missing evidence; scoped requirements in prompts; retain no-extra-research controls | Implemented and regression checked |
| R3 | P1 | Invalid agent JSON falls back to an insufficient answer (`mh-001`) | One bounded format-only repair using already-read evidence; retain failed output, repair usage and fallback provenance; never silently turn an unresolved fallback into a complete answer | Implemented and mock checked |
| R4 | P1 | Partly read evidence still displayed (`mh-006`, `mh-021`); filename placeholders become C? | Withhold unverified answers after unresolved evidence-read checks; preserve ordinary bracketed text while checking actual citations | Implemented; whole-unit definition reads also fixed |
| R5 | P2 | Helpers, failed parsing and repeated grading undercount usage | Sum all reported models; count failed/retried calls and unknown usage; distinguish invocation usage from cumulative grading usage | Implemented, including known cached fallback estimates |

## Verification plan

1. Implement code and meaningful regressions from recorded failures, without changing original
   answers, verdicts or freezes. Use mocks for unit tests and a disposable database for integration.
2. Replay deterministic guards, citation mapping and formatting against saved baseline artifacts.
3. Run affected local checks and the full test suite; retain strict date/applicability filters.
4. State an LLM budget before any targeted live test. Re-run only a small regression set; do not
   silently start another full 118-question benchmark or claim an improved aggregate score.
5. Record verification, remaining limits and the new snapshot identity here when finished.

## Design boundaries

Research guards are conservative signals, not proof of legal completeness. They must respect the
question's scope and assumptions, date constraints, source filters and finite tool/context budgets.
Optional date metadata and missing inputs that cannot affect the outcome must not reintroduce broad
research loops. Format repair may reformat existing content only and must not perform fresh research.
Raw model scores stay visible; an AI review must not be attributed to a practitioner.

## 已完成的改动

程序现在会有限预读明确列出的同条款例外，优先装入完整的小段落，避免一个长段落
占满全部四个额外片段。独立检查会识别正文承认的必要证据缺口，升级研究时把具体
缺口清单一起传给代理。明确给定的情景分类和已经足以决定结果的条件不再要求重复证明。
这些规则是保守的检查信号，不能证明全部法律例外都已被发现。

格式修复只允许一次不带工具的调用，受剩余 tokens 和可确定的剩余 CLI 费用预算约束。
原答案全文和声明内容不能缩短或新增事实；不满足内容保留检查时仍返回未验证结果。
读取不完整的引用不会作为已验证正文展示，路由保留失败尝试和用量；仍可能返回明确
标记缺口的普通回答，而不是保证所有研究都成功。

定义工具还有一个运行中确认的问题：查找“大企业”时，父段落由两个窗口组成，旧工具
只返回包含销售口径的匹配窗口，却引用整个父段落。现在会同时交付完整逻辑段落的窗口，
继续遵守过滤和返回长度限制，不会把从数据库补查的内容伪装成旧模型已经读过的内容。

## Frozen reference and grading records

- New development freeze: `evals/frozen/20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b.json`, still 118 items.
- Only `sa-004` changed: distinguish the Article 123(1) threshold from Article 123(4)'s natural-person exception. See [before/after and source](sa-004-revision-2026-11-13.json).
- Both previous freezes and the original complete answer/judge run remain unchanged.
- All 10 inconsistent historical verdicts were triaged in [the review ledger](frozen118-verdict-triage-2026-11-13.json). These are AI review notes requiring adjudication, not practitioner sign-off or rewritten raw scores.
- The judge receives cited source/ref/hierarchy and bounded evidence excerpts. That map participates in cache identity. Malformed verdict fields are rejected; contradictory scores or empty rationales leave the report labelled `requires_review`.
- New grading records separately report invocation usage, immutable cumulative usage receipts, and unknown calls. Historical caches retain their original accounting; they are not retroactively normalized.

## Verification completed

- **204 tests passed**, including live disposable-Postgres integration checks, with no skipped DB integration checks in the configured run. Ruff and diff checks passed.
- [Saved-answer replay](frozen118-guard-replay-2026-11-13.json) detects the necessary gaps in `mh-003`, `mh-012`, `mh-015`; document-content controls `app-001` and `cmp-002` do not acquire new research gaps.
- Real database check: `get_definition('large corporate')` delivers the definition and both Article 142(1) parent windows; no partially read key remains for this result.
- Unit regressions cover citation-map cache invalidation, conflicting score/rationale, failed grading and cumulative usage, targeted fallback requirements, proviso filters, optional inputs/dates, format preservation, ordinary placeholders, partial-read withholding and unknown usage.

Targeted live tests were iterative; the first two iterations exposed defects that were then fixed.
No failed intermediate attempt was deleted or replaced in place.

| Issue | Last tested result | Run |
|---|---|---|
| `mh-001`: large-corporate scenario | Complete answer, model score 2, no required gap | `20261113-091239-589821-routed-all` |
| `mh-012`: economic loss components and discount rate | Complete answer, model score 2, no required gap | `20261113-091940-701539-routed-all` |
| `mh-015`: maturity election and size condition | Complete answer, model score 2, citation recall 1.0, no required gap | `20261113-092400-672579-routed-all` |
| `oos-001`: outside scope | Correct refusal | `20261113-091239-589821-routed-all` |

Detailed answers, exact run/answer hashes, intermediate outcomes, namespaces and usage receipts
are in [validation evidence](frozen118-fix-validation-2026-11-13.json). Known new usage across all
three answer runs and their grading was **1,233,089 tokens**, including helpers; no unknown-usage
calls occurred. Each individual answer/grade run was below the project's one-million-token
confirmation threshold. A research question used about 398k tokens despite the original lower
pilot estimate; default estimates were raised and known cached fallbacks are now included.

These are development regressions from different implementation stages, not an independently
sampled cohort or a fresh full-118 result. At implementation completion only these targeted
checks had run. The subsequent [complete rerun](../results/frozen-118-rerun-2026-11-13.md)
records all 118 items, including quota recovery and newly observed failures. The old 84.0% raw
score remains unchanged. Format recovery and guards can still fail;
tool/context limits and incomplete corpus dates remain explicit limitations. Practitioner
adjudication of disputed historical verdicts remains separate from this implementation.

The next [post-rerun follow-up](REVIEW-FROZEN118-FOLLOWUP-2026-11-13.md) addresses the remaining
empty-output, retry-cache, dependency and scope failures. It records 223 passing tests and
real SQL checks, together with the subscription-quota interruption that prevented confirmation
of the two complex answers. The original full-run score and artifacts remain unchanged.
