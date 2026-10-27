# Synthetic Model Validation Policy — outline

Demo input for the Phase 4 gap analysis. The bank is **fictitious** ("RegLens Demo Bank"), the
policy is written from scratch, and it shares no text or structure with any real institution's
policy (CLAUDE.md, hard rule 2).

**Scope of the policy:** validation of IRB Pillar 1 credit risk models (PD, LGD, LGD in-default,
ELBE, CCF) of a bank with A-IRB permission for retail and F-IRB for corporates.

**How it will be used:** in Phase 4 the full text is written so that most requirements are covered
and **~15 gaps are planted** (missing, partial, contradicted). The answer key lives in a separate
file (`gaps.yaml`, not in the policy text) and is the ground truth for the gap-analysis eval.

The *Requirements to cover* column is the coverage map: what a complete policy section must address.
References were checked in the downloaded texts unless marked *(check)*.

| # | Section | Contents | Requirements to cover |
|---|---|---|---|
| 1 | Purpose, scope and document control | Objective; models in scope (PD/LGD/ELBE/LGD-in-default/CCF); entities covered; owner, approval, version history | CRR Art. 185; ECB guide, Overarching principles (model risk framework, model register) |
| 2 | Definitions | Validation types, model change, finding, MoC, default, rating system | CRR Art. 4(1)(54)–(56), Art. 142; Art. 178 |
| 3 | Governance and roles | Management body / committee approval; senior management; model owner, developers, credit risk control unit, validation function, internal audit | CRR Art. 189 (approval of material aspects), Art. 190 (credit risk control independence and tasks), Art. 191; ECB guide para. 19 (independence of validation from development) |
| 4 | Independence and resources of the validation function | Organisational separation, reporting lines, staffing and skills, conflicts of interest | ECB guide, Overarching principles — internal validation *(check exact paras)* |
| 5 | Model inventory and materiality | Model register, model tiering, materiality-based validation intensity | ECB guide, Overarching principles (model register) |
| 6 | Validation types and frequency | Initial validation of new models; validation of material changes and extensions; regular (at least annual) validation; ad hoc triggers | CRR Art. 185; ECB guide para. 18 (initial validation scope) *(check)*; ECB validation reporting (annual cycle) |
| 7 | Data and definition of default | Data quality checks, representativeness, observation periods, consistency of the default definition (incl. materiality threshold, probation) | CRR Art. 178, Art. 179(1), Art. 180(1)(h), 180(2)(e); RTS 2018/171; EBA GL/2016/07 paras. 71–73 |
| 8 | PD validation | Rating process, discriminatory power (AUC), calibration and back-testing per grade, stability, rating philosophy | CRR Art. 185(b); EBA GL/2017/16; ECB validation reporting (PD tests) |
| 9 | LGD, ELBE and LGD-in-default validation | Back-testing of realised vs estimated LGD, downturn LGD, treatment of defaulted exposures, input floors | CRR Art. 181(1)(b), Art. 164(4), Art. 185(b); RTS 2021/930; EBA GL/2019/03 (incl. para. 36); EBA GL/2017/16 |
| 10 | CCF validation | Back-testing of conversion factors; scope after CRR3 (IRB-CCF only where allowed) | CRR Art. 151(7)–(8), Art. 166(8)–(8b); ECB guide v4.1 removed CCF content — note |
| 11 | Margin of conservatism | Review of identified deficiencies (Categories A, B, C) and MoC quantification | EBA GL/2017/16 paras. 36–43 |
| 12 | CRM and scope checks | Recognition of collateral and guarantees in LGD; A-IRB scope (large corporates, financial sector entities) | CRR Art. 181(1)(c)–(d), Art. 164(2), Art. 183, Art. 151(8); EBA GL/2020/05 |
| 13 | Findings, severity and remediation | Rating of findings, deadlines, tracking, escalation, effect on model use and MoC | CRR Art. 189(2); ECB guide (validation findings) *(check)* |
| 14 | Reporting | Validation reports to management body and model owners; annual reporting of validation results to the supervisor (SI) | CRR Art. 189; ECB validation reporting instructions (Feb 2019) |
| 15 | Internal audit | Review of the validation function and rating systems at least annually | CRR Art. 191 |
| 16 | Policy review | Annual review, triggers for update (regulatory change, e.g. CRR3 output floor and input floors) | CRR Art. 189 |
| A | Annex: test catalogue | Standard tests and thresholds (traffic lights) per parameter | ECB validation reporting (test definitions) |

## Gap ideas for Phase 4 (not part of the policy text)

Candidates for planted gaps — to be finalised in `gaps.yaml` with the expected finding:

- **Missing:** no requirement for internal audit to review the rating systems at least annually (Art. 191).
- **Contradicted:** validation function reports to the head of model development (independence, ECB guide para. 19).
- **Partial:** PD back-testing per grade only every two years, not regularly with annual reporting (Art. 185(b)).
- **Contradicted:** probation period of 1 month after default cure (EBA GL/2016/07 para. 71: ≥ 3 months).
- **Missing:** no downturn LGD validation, or no fallback when downturn impact cannot be observed (EBA GL/2019/03 para. 36).
- **Partial:** MoC review covers Category A only (EBA GL/2017/16 para. 36).
- **Contradicted:** own LGD estimates allowed for large corporates (CRR3 Art. 151(8)(c)).
- **Missing:** no check of LGD input floors (Art. 164(4)).
- **Partial:** management body approves the policy but not material changes to rating systems (Art. 189(1)).
- **Missing:** observation period requirement for PD data (Art. 180(1)(h)).

(Ten here; five more to add when the full text is written.)

## Next steps

1. You review the section list (anything a real validation policy would have that's missing?).
2. Phase 4: write the full policy text (~15–20 pages) with the planted gaps, and `gaps.yaml`.
