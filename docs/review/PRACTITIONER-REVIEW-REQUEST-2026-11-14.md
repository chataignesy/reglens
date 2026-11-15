# Independent practitioner review request

Personal project; not affiliated with any employer or supervisor. Not legal or regulatory advice.

Status: **pending an independent practitioner**. This is an evidence pack and proposed scope
analysis prepared by Codex, not a completed adjudication or practitioner certification. No raw
answer, frozen reference, grade or benchmark report has been changed.

The [structured packet](practitioner-packets-2026-11-14.json) contains each exact question,
frozen reference, answer, raw grade, immutable answer-artifact hash and source fingerprints.

Conduct the review using the [staged guide](PRACTITIONER-REVIEW-GUIDE-2026-11-15.md) and
[worksheet](PRACTITIONER-REVIEW-FORM-2026-11-15.md). This request includes proposed interpretations;
disclose it only after the reviewer has recorded their independent source/answer assessment.

## mh-006: PD question and the own-LGD/CCF clause

The raw Codex grade is partial because the answer omits the analogous own-LGD/conversion-factor
analysis. That conditional obligation appears in Article 185(b); the question specifically asks
about PD back-testing and submission under the historical February 2019 instructions. The
question for review is whether that additional clause must be stated to answer the actual ask,
not whether it exists in the provision. See [CRR, registered consolidated version](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02013R0575-20260626)
and [ECB instructions, Section 2.2](https://www.bankingsupervision.europa.eu/activities/internal_models/shared/pdf/instructions_validation_reporting_credit_risk.en.pdf).

Proposed for review: distinguish optional adjacent obligations from indispensable PD facts.
Alternatively, retain mandatory status and explain why omission materially changes this answer.
Any approved future rubric change needs a new version; the published raw score remains partial.

## mh-014: guaranteed mortgage and question scope

The completed Codex baseline already gives this answer full credit. Review the supplied eligible
guarantee assumption, covered/uncovered split and whether discussion of CCF floors is optional
for a question expressly asking about PD and LGD. Do not reopen eligibility as a missing user
input solely because it is supplied as an assumption. The frozen source anchors are CRR 159a,
163(1)(b) and 164(4), with qualifications preserved in the original record. See the
[registered CRR version](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02013R0575-20260626).

Proposed for review: retain the existing raw full-credit result; clarify future rubric scope if
needed. Identify any disagreement by precise source text and its effect on the answer.

## Recording the independent review

For each case, supply reviewer identity/role, decision (`accepted`, `rejected`, `needs_evidence`),
reasoning, source/date basis and any conflicts. Only after an actual practitioner supplies a
decision, record it against the packet's exact answer artifact:

```powershell
.venv\Scripts\reglens.exe adjudicate <exact-answer-artifact.json> --reviewer '<actual reviewer>' --decision <decision> --reason '<actual reasoning>'
```

The command creates a separate content-addressed adjudication. It does not overwrite old scores
or make the reviewer independent merely because a name was entered. Disclose how the reviewer
was selected and whether they authored development references or product changes.

The independent holdout is out of scope at the user's request as of 15 November 2026.
