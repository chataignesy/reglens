# AI pre-review of mh-006 and mh-014 (not a practitioner adjudication)

Personal project; not affiliated with an employer or supervisor. Not legal or regulatory advice.

Reviewer: Claude (Opus 5.5) as an AI assistant in a Claude Code session, 15 November 2026.
**This is not an independent practitioner review.** Under the
[guide](PRACTITIONER-REVIEW-GUIDE-2026-11-15.md) it counts as an author-side check, because Claude
sessions have helped build this repository. The project author later approved it. See
[Recorded decision](#recorded-decision-author-practitioner-review-15-november-2026).

Independence limits:
- The [request](PRACTITIONER-REVIEW-REQUEST-2026-11-14.md) was read first. It contains the raw
  grades and the proposed rulings, so stage 1 was **not blind**.
- Stage 1 was still written from the primary texts before the packet answers and references were
  opened: CRR `02013R0575-20260626` (local `crr3-consolidated.txt`) and the ECB PDF (sha256
  `f0bef87b…`, cover page "February 2019", PDF CreationDate 2019-02-28).
- Both answer artifacts match the packet hashes (`10cad714…`, `9f0d9c22…`).

## mh-006: PD back-testing under 185(b) and submission under Section 2.2

### Stage 1: source assessment

**Minimum adequate answer.**
- Art. 185(b): regularly compare realised default rates with estimated PDs **for each grade**.
- Where realised default rates fall outside the grade's expected range, specifically analyse the
  reasons for the deviation.
- Use historical data covering as long a period as possible.
- Document the methods and data used.
- Update the analysis and documentation at least annually.
- Section 2.2: institutions submit the validation-tool results to the ECB on the ECB templates,
  together with their annual report on the outcomes of internal model validation.

**Essential facts:**
- the per-grade realised-vs-estimated comparison;
- the deviation analysis;
- long historical data;
- documentation;
- the annual update;
- submission alongside the annual validation report on the ECB templates.

**Useful but not decisive:**
- templates are completed at consolidated level unless the Decision says otherwise;
- the one-year observation period with a constant end date;
- free-text comments and references to the internal validation report;
- the file naming convention.

**Optional:**
- the 185(b) sentence on analogous analysis for own LGD and CCF estimates. It is real law, but it
  is not PD back-testing, and the question asks only about PD.
- 185(c)–(e), including the significant-deviation standards in (e).
- AUC and other individual tests.

**Uncertainty:** none on the law. The 2019 instructions are historical. The question frames them
that way, so the answer does not need a currency caveat.

### Stage 2: answer assessment

Assessment: **complete**.
- Every 185(b) PD element is stated accurately and cited to C1.
- The Section 2.2 submission content is accurate and cited to C2. That covers the timing with the
  annual report, the templates, the consolidated-level default, free text and references, the
  observation period and naming.
- The Section 2.2 claims are labelled as supervisory, not law, which is correct.
- Nothing is wrong or unsupported.
- The LGD/CCF sentence is omitted. That does not change how a reader would answer the PD question.

Minor point, not a scoring matter: the as-of line says "other sources as downloaded 27 Oct 2026".
It does not name the February 2019 edition. The packet's source fingerprint also gives the
download date as `version`. Under hard rule 4, the edition date would be better in both places.

### Stage 3: rubric comparison

- **Frozen reference:** correct, but it over-demands. Making the analogous LGD/CCF clause
  mandatory turns "what the provision also says" into "what the question requires".
- **Automated verdict (partial, score 1):** not justified for this answer. Its only "missing" item
  is the LGD/CCF clause, which is outside the question's scope.
- **Opinion after disclosure:** unchanged. It matches the request's proposal, which was seen
  before stage 1 (see the independence limits above).
- **Recommended rubric change:** in a new rubric version, mark the LGD/CCF clause optional for
  mh-006. Keep the published raw score as is.
- **Recommended answer-level decision:** `accepted`.

## mh-014: eligible central government guarantee on an IRB retail mortgage

### Stage 1: source assessment

**Minimum adequate answer.**
- Art. 159a covers the whole of Chapter 3, including retail, with an express reference to
  164(4). On the part of the exposure covered by an eligible guarantee from a central government,
  central bank or the ECB, the PD and LGD input floors do not apply.
- On the uncovered part they do apply:
  - PD floor of 0.05% for retail that is not QRRE revolvers (Art. 163(1)(b));
  - LGD floor of 5% for retail secured by residential property (Art. 164(4), Table 1). Under
    164(4a)(d) this is fixed "irrespective of the level of collateral".

**Essential facts:**
- the covered/uncovered split;
- no floors on the covered part;
- the floors and their values on the uncovered part.

**Optional:**
- CCF floors (166(8c)). The question asks about PD and LGD only.
- How the guarantee is recognised: substitution, or adjusting PD/LGD under 164(2) and 183.
- Higher national LGD floors under 164(6) and (10).

**Uncertainty:** none material, given the stated eligibility assumption.

### Stage 2: answer assessment

Assessment: **complete**.
- It keeps the eligibility assumption ("assuming the guarantee is eligible").
- It splits the covered and uncovered parts explicitly.
- Both floor values are correct.
- "Irrespective of the level of residential property collateral" is supported by 164(4a)(d) (C3).
- "Higher LGD floors set by the relevant authorities may apply" is supported by 164(6) and 164(10)
  (C4, C5).
- No unsupported qualification was found.

### Stage 3: rubric comparison

- **Frozen reference:** appropriate. It mentions CCF in passing because it paraphrases 159a, but
  CCF should not count as a required fact.
- **Automated verdict (full credit, score 2):** justified.
- **Opinion after disclosure:** unchanged.
- **Recommended rubric change:** optional. A future version could add a grading note that CCF
  floors and the mechanics of recognising the guarantee are out of scope.
- **Recommended answer-level decision:** `accepted`.

## Recorded decision (author practitioner review, 15 November 2026)

The project author reviewed and approved this analysis. The author, MistVista, is an EU
credit-risk practitioner. Both decisions were recorded with `reglens adjudicate` as **author
review, not independent review**. The reviewer wrote the frozen references and directed the
product changes, and stage 1 was not blind.

| Case | Answer artifact sha256 | Decision | Adjudication record (`data/evals/adjudications/`) |
|---|---|---|---|
| mh-006 | `10cad714…3912c7` | accepted | `f0084f855058a422327746cb2fba9386e0dbe005f4cfc2ecc462560c0634c121.json` |
| mh-014 | `9f0d9c22…4fe98` | accepted | `0d645f414ee5ef5f7d9e78f9db21c988f922c0f5a90a24e44e4e68ab205632f3.json` |

The raw automated scores are unchanged: mh-006 is still partial (1) and mh-014 is still full (2).
The recommended mh-006 rubric change, to make the own-LGD/CCF clause optional, needs a new
versioned rubric.

## What this does and does not support

This review gives an author-side practitioner opinion on these two cases only. It is not
independent evidence and supports no claim of independent practitioner validation. No raw answer,
reference or score was changed.
