# Conducting the practitioner review

Personal project; not affiliated with an employer or supervisor. Not legal or regulatory advice.

Scope decision, 15 November 2026: the independent holdout is out of scope. The current task is
practitioner adjudication of `mh-006` and `mh-014`, with the original evidence retained.

## Reviewer and brief

Ask a practitioner with relevant EU credit-risk/IRB modelling, validation or regulatory experience
who did not write these reference answers or implement the fixes. Agree whether they may be
named publicly; a reviewer ID can be used in the published record with their role and relevant
experience disclosed. If you conduct the review yourself, record it as author review rather
than independent review.

Explain that they are checking two specific answers and the scope of their grading criteria.
The questions are judged against the registered source versions and their stated assumptions,
including the expressly historical February 2019 ECB instructions. This is not a request to
approve every answer the product could generate. Supply registered public sources only.

## Three-stage process

1. **Independent source assessment.** Send the question and source/version references first.
   Ask the reviewer to write a minimum adequate answer and separate essential facts from optional
   background. Withhold our model answer, expected answer, automated grade and proposed ruling.
   Record their initial notes before revealing those materials.
2. **Answer assessment.** Give the exact saved model answer identified by its artifact hash.
   Ask whether it is complete, partial, wrong or unassessable for the actual question. Require
   precise sources and an explanation of the consequence of every material omission or error.
   Check whether citations support the claims, supplied assumptions were respected and the
   answer distinguishes covered and uncovered portions where relevant.
3. **Rubric adjudication.** Reveal the frozen reference, grading notes, automated verdict and
   proposed scope analysis from the full packet. Ask whether each demanded fact is essential
   to the actual question or merely adjacent information. Preserve any change from the initial
   opinion and its reason. If disagreement remains, record it or obtain a second review rather
   than forcing agreement.

The full [request](PRACTITIONER-REVIEW-REQUEST-2026-11-14.md) includes proposed interpretations;
do not send it at stage 1. Use the [worksheet](PRACTITIONER-REVIEW-FORM-2026-11-15.md) and disclose
its later-stage sections only when that stage begins.

## Required review record

For each case capture reviewer ID/role, date, exact answer artifact/hash, source/version basis,
minimum adequate answer, essential versus optional facts, answer assessment, material findings,
recommended rubric changes, uncertainty and relevant involvement/conflicts. Keep the independent
first-stage notes alongside the final opinion. No prefilled recommendation is a human decision.

The application stores an answer-level sidecar decision as `accepted` (adequate for the question),
`rejected` (materially incorrect/incomplete), or `needs_evidence` (not yet assessable). For a partial
answer, explain what is correct and missing in the reason; a rejected-as-complete sidecar does not
mean every statement is wrong and does not replace the automated numeric score.

Only record an actual reviewer-supplied decision. The existing command is:

```powershell
.venv\Scripts\reglens.exe adjudicate <exact-answer-artifact.json> --reviewer '<reviewer ID and role>' --decision <accepted|rejected|needs_evidence> --reason '<actual findings and source basis>'
```

Keep the old references and scores unchanged. An approved change to what a future question
requires belongs in a new, versioned rubric/snapshot. Report the practitioner opinion separately
from raw automated scores and disclose the number and selection of cases reviewed.

## Invitation text

> I’m building RegLens as a personal project using public EU credit-risk sources. Would you review
> two saved answers and their grading criteria in your personal capacity? I’d first send the
> questions and source references, then the answers, and finally our existing grading material.
> I’m looking for source-backed findings on correctness, completeness and which facts the actual
> question requires. Please also let me know whether you may be named in the review record.

After these two cases, an optional mixed sample of additional answers can support a broader
practitioner-review statement. Two targeted adjudications alone support only claims about those
cases; omitting the holdout means no claim of performance on an independently authored unseen set.
