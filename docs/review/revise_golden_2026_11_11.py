"""Apply the reviewed 26-item revision once, with precondition hashes and a before/after log."""

# Reference-answer literals are intentionally kept intact for auditable before/after data.
# ruff: noqa: E501

import hashlib
import json

from reglens.config import PROJECT_ROOT


def citations(*pairs):
    return [{"source": source, "ref": ref} for source, ref in pairs]


CRR = "crr3-consolidated"
DOD = "eba-gl-dod"
ECB = "ecb-guide-internal-models"
RTS = "rts-default-materiality"

UPDATES = {
    "dod-003": {
        "expected_answer": "The authority-set absolute component must not exceed EUR 100 (or its national-currency equivalent). The relative component is between 0% and 2.5%, normally 1% where the authority considers that reasonable. Its denominator is the institution's, parent's and subsidiaries' total on-balance-sheet exposures to the obligor, excluding equity exposures. Both components must be exceeded for the material past-due criterion; the applicable consecutive-day period must also be met.",
        "expected_citations": citations((RTS, "Art. 1(2)"), (RTS, "Art. 1(5)")),
        "review_note": "The non-retail EUR 500 cap is optional context, not a required fact for this retail question. These are RTS settings/caps, not an assertion of the actual setting in every jurisdiction.",
    },
    "dod-004": {
        "expected_answer": "At least three months after the conditions in CRR Articles 178(1)(b) and 178(3) cease to be met. This is a minimum probation period, not automatic cure; the other reclassification conditions must also be satisfied.",
        "expected_citations": [
            {
                "source": DOD,
                "ref": "para. 71",
                "alternatives": [{"source": ECB, "ref": "Credit risk, para. 173(a)"}],
            }
        ],
        "review_note": "Required: the three-month minimum and its start. Details of the broader cure assessment are optional. ECB 170/172 are not standalone equivalents for the minimum-period fact.",
    },
    "dod-005": {
        "expected_citations": citations((DOD, "para. 72"), (DOD, "para. 73")),
        "review_note": "Keep the one-year latest-of start and the cure conditions distinct. ECB 170/172/173 do not individually replace both EBA paragraphs. This reference uses the registered 2016 guideline wording; the 2026 amendment changes the forbearance terminology without changing the one-year minimum.",
    },
    "pd-003": {
        "expected_answer": "Normally at least five years for at least one data source, using a longer available period where relevant and a representative mix of good and bad years. At IRB implementation, the competent authority may permit relevant data covering two years, then an additional year each year until five years is covered. For non-retail exposures this exception is restricted to institutions without permission to use own LGD estimates or IRB-CCF; the retail implementation exception is also subject to authority permission.",
        "expected_citations": citations((CRR, "Art. 180(1)"), (CRR, "Art. 180(2)")),
        "review_note": "The concluding subparagraphs supply the implementation exceptions. A categorical five-year-only answer is incomplete; the two-year exception is not unconditional or available to every non-retail A-IRB institution.",
    },
    "sa-001": {
        "question": "Under the ordinary CRR3 Article 125(1) loan-splitting treatment for an eligible residential-property exposure, with a sole first lien and no national override, what risk weight applies to the part up to 55% of the property value?",
        "expected_answer": "20%. The question assumes eligibility for Article 125(1), a sole first lien and no higher national risk weight or lower national property-value percentage.",
        "review_note": "Required: 20% for the specified eligible part. Junior/pari-passu lien allocation and other property-treatment branches are optional context, not required facts.",
    },
    "floor-001": {
        "expected_answer": "55% for the period from 1 January to 31 December 2026, under CRR Article 465(1)(b).",
        "expected_citations": citations((CRR, "Art. 465(1)(b)")),
        "review_note": "Required: the 2026 factor. Other phase-in years, the 72.5% end state and the conditional group/solo derogation are optional, not required to receive full answer credit.",
    },
    "mh-001": {
        "question": "An A-IRB bank has an exposure classified as general corporate, not specialised lending, to a non-financial corporate group with EUR 800 million consolidated sales measured under CRR Article 142(1)(5a). May it use own LGD and CCF estimates for that exposure?",
        "review_note": "The scenario expressly excludes the specialised-lending exception and treats sales as the regulatory measure, not an arbitrary single-year number.",
    },
    "mh-003": {
        "expected_answer": "Article 181(1)(b) requires downturn-appropriate LGD when more conservative than the long-run average. Identify downturn periods using the relevant economic indicators and their most severe 12-month values; the duration is at least 12 months and may be longer. Where observed loss data cannot support calibration, first consider estimating the downturn impact using Section 6 of the EBA downturn guidelines. Only where neither observed-impact nor Section 6 calibration is possible may the paragraph-36 fallback be used: justify that inability to the competent authority, include a strictly positive Category A MoC for missing data, and ensure final downturn LGD including MoC is at least min(long-run average LGD + 15 percentage points, 105%). No observed impact, no relevant data, and inability to estimate impact are different cases.",
        "expected_citations": citations(
            (CRR, "Art. 181(1)(b)"),
            ("rts-economic-downturn", "Art. 4"),
            ("rts-economic-downturn", "recital 14"),
            ("eba-gl-downturn-lgd", "para. 36"),
        ),
        "review_note": "Required: the normal downturn rule, consideration of estimated-impact calibration before the final fallback, and the conditional fallback safeguards. Do not infer a flat 15-point add-on whenever a bank lacks observed downturn data.",
    },
    "mh-005": {
        "question": "An A-IRB bank recognises eligible financial collateral that fully secures an other-retail exposure after the relevant volatility and currency adjustments. Which CRR dependence/currency requirements and LGD input floor apply?",
        "expected_answer": "Consider dependence between the obligor and the funded protection or provider, and address significant dependence conservatively (Article 181(1)(c)). Treat currency mismatches conservatively in LGD (Article 181(1)(d)). The fully eligible secured floor is 0%, compared with 30% for unsecured other-retail exposures (Article 164(4)); full coverage after the relevant adjustments is required under Article 164(4a). Partially secured exposures instead use a weighted floor.",
        "expected_citations": citations(
            (CRR, "Art. 181(1)(c)"),
            (CRR, "Art. 181(1)(d)"),
            (CRR, "Art. 164(4)"),
            (CRR, "Art. 164(4a)"),
        ),
        "review_note": "The question supplies full eligible adjusted coverage. Details of the partial-collateral formula are optional context.",
    },
    "mh-006": {
        "question": "For an IRB institution covered by the ECB reporting Decision referred to in the February 2019 validation-reporting instructions, what PD back-testing does CRR Article 185(b) require, and how are the results submitted under Section 2.2 of those instructions?",
        "expected_answer": "Regularly compare realised default rates with estimated PDs for each grade and analyse deviations outside the expected range. Use historical data covering as long a period as possible, document methods/data, and update the analysis and documentation at least annually; analogous comparisons apply to own LGD/CCF estimates. Under Section 2.2 of the February 2019 instructions, institutions covered by the Decision submit validation-exercise results to the ECB using its templates when submitting their annual internal-validation report.",
        "review_note": "The reporting obligation is limited to institutions covered by the referenced Decision. AUC is not established by Section 2.2 and is not a required scoring fact. The instruction version is explicitly historical.",
    },
    "mh-007": {
        "question": "Which input and output floors constrain an ordinary IRB retail residential-mortgage portfolio in 2026, assuming no eligible sovereign/central-bank guarantee under Article 159a and an institution subject to the output floor without the group/solo derogation?",
        "expected_answer": "Per exposure, the normal PD input floor is 0.05% for retail exposures other than QRRE revolvers and the residential-property LGD input floor is 5%. In 2026 the output-floor factor is 55%, applied to the institution's total risk exposure amount by comparison with its standardised total, not independently to this portfolio. Input floors and the institution-wide output floor are distinct constraints.",
        "expected_citations": citations(
            (CRR, "Art. 163(1)(b)"),
            (CRR, "Art. 164(4)"),
            (CRR, "Art. 465(1)(b)"),
            (CRR, "Art. 92(3)"),
        ),
        "review_note": "The question expressly excludes the Article 159a and group/solo exceptions. Details of SA mortgage treatment are optional, not needed to explain the different floor levels.",
    },
    "cmp-002": {
        "question": "According to the June 2026 ECB guide's foreword, what changed in its CCF-estimation content compared with the preceding guide, and why?",
        "expected_answer": "All content on estimating conversion factors (CCF) was removed because the EBA was preparing guidelines on that topic.",
        "expected_citations": citations((ECB, "Foreword, para. 7")),
        "review_note": "Required: removal of all CCF-estimation content and the stated reason. Release numbers, dates from the release table and the 2025 release history are optional.",
    },
    "app-001": {
        "question": "What do paragraphs 1-3 of the ECB guide's foreword establish about its legal force and purpose, and do those passages alone establish whether an NCA-supervised less significant institution must follow the guide?",
        "expected_answer": "They explain the ECB's understanding of the applicable rules and its approach to assessing internal-model permissions, and support consistency among supervisory teams. The guide does not replace or overrule EU or national law. Those passages alone do not establish an obligation for an NCA-supervised LSI to follow the guide; that requires further evidence about the applicable supervisory framework.",
        "review_note": "A bounded answer acknowledging that LSI applicability is not established by these passages is required. Do not require an unsupported categorical SI/LSI allocation or imply that EBA guidelines have identical legal force to regulations.",
    },
    "sa-005": {
        "question": "Under the ordinary CRR3 Article 126(1) loan-splitting treatment for an eligible non-IPRE commercial-property exposure, with a sole first lien and no national override, what risk weight applies to the part up to 55% of property value?",
        "expected_answer": "60% for that eligible part. The question assumes the Article 124/126(1) eligibility conditions, a sole first lien and no higher national risk weight or lower national property-value percentage.",
        "review_note": "Required: 60%. Other property branches and junior/pari-passu lien adjustments are optional contextual qualifications.",
    },
    "sa-008": {
        "question": "Under the fully phased-in general rule in CRR Article 133(3), excluding transitional/grandfathered treatment and the exceptions in paragraphs 4-7 or Part Two, what risk weight applies to equity exposures?",
        "expected_answer": "250% under Article 133(3). This is the end-state general rule, not an assertion of the applicable risk weight for every equity exposure during the Article 495a transition.",
        "review_note": "The question explicitly asks for the end state outside Article 495a and other exceptions. Mentioning transitional treatment is acceptable optional context.",
    },
    "irb-003": {
        "question": "Under the general rule in CRR Article 150(1), outside the equity transitional arrangements in Article 495, which approach must an IRB institution use for equity exposures?",
        "expected_answer": "The standardised approach for the equity exposure class in Article 147(2)(e), under Article 150(1)(a). This answer is limited to the general rule; it does not deny the separate transitional treatment for previously permitted equity exposures in Article 495.",
        "review_note": "Required: the general SA rule within the stated exclusion. Do not mark a correctly qualified answer about existing transitional permissions wrong. Full Article 495 calculations are not required by this question.",
    },
    "irb-004": {
        "expected_answer": "With competent-authority permission and compliance with Section 6, IRB-CCF is used for eligible undrawn revolving commitments under IRB that would not have a 100% SA-CCF. Article 151(8) also limits exposure-class eligibility: institution exposures, other financial-sector entities and large corporates outside specialised lending must use SA-CCFs. SA-CCFs also apply to the other off-balance-sheet items, particularly non-revolving undrawn commitments, and where permission or minimum requirements are absent.",
        "expected_citations": citations(
            (CRR, "Art. 166(8b)"), (CRR, "Art. 166(8)"), (CRR, "Art. 151(8)")
        ),
        "review_note": "Required: revolving/non-100%-SA conditions, permission/minimum requirements, and the mandatory-SA exposure-class restriction. Revolving alone is insufficient.",
    },
    "dod-008": {
        "question": "Under the original 2016 text of EBA/GL/2016/07, before the amendments applying from 19 October 2026, which situations were treated as technical past due and how were they handled?",
        "review_note": "Historical source-comprehension question, not current-law guidance. The registered corpus contains the original 2016 text, whose factoring limb uses 30 days. EBA/GL/2026/05 replaces that limb with a 90-day rule and additional cases; a current-rule answer must not be scored against this historical reference. Remove or replace this question when introducing an updated-current-law-only dataset.",
        "extra_tags": ["historical-rule", "eba-gl-2016-07-original"],
    },
    "mh-010": {
        "question": "How is LGD in-default set for a defaulted retail exposure under own LGD estimates, and when does EBA paragraph 184 require no additional adjustment of the ELBE basis for current economic conditions?",
        "expected_answer": "LGD in-default is ELBE plus the estimated increase in loss rate from possible additional unexpected losses during recovery. Under EBA paragraph 184, ELBE is estimated on the long-run average LGD basis without a further current-conditions adjustment where the model directly includes a macroeconomic risk driver, a material risk driver is sensitive to economic conditions, or realised LGD for defaulted exposures is insensitive to the relevant economic factors. The first two cases capture conditions through the model; they do not permit ignoring economic conditions.",
        "review_note": "No additional adjustment is different from ignoring current conditions. Accept explanations that the model already reflects the cycle.",
    },
    "mh-011": {
        "expected_answer": "Use the relevant indicators by exposure type, including GDP, unemployment and available aggregate default rates/losses, plus appropriate sector/property and other relevant indicators. Examine a 20-year historical window ending at identification, extending it when its variability is not representative of the likely future range. Identify the most severe 12-month indicator values and set a downturn period of at least 12 months, longer where needed to cover related prolonged severity or adjacent peaks/troughs.",
        "review_note": "Required: relevant indicators, the 20-year rule with its representativeness exception, and the minimum rather than fixed 12-month duration.",
    },
    "mh-023": {
        "expected_answer": "Under CRR Article 108(3), Chapter 3 recognition of unfunded credit protection requires the institution to use own LGD estimates for both the original exposure and comparable direct exposures to the protection provider. In that case, Articles 160(4) and 161(3) permit recognition in PD or LGD in accordance with Article 183; in other cases Article 108(3) directs recognition under Chapter 4. Article 183(1) requires clearly specified recognised-guarantor criteria, the relevant obligor-rating rules for guarantors, and a written, non-cancellable/non-changeable, enforceable guarantee covering the specified amount and tenor until satisfaction, which meets the unconditionality requirements.",
        "expected_citations": citations(
            (CRR, "Art. 108(3)"), (CRR, "Art. 160(4)"), (CRR, "Art. 161(3)"), (CRR, "Art. 183(1)")
        ),
        "review_note": "Do not apply the historical Q&A 2016_2593 as an unconditional current Chapter-3-only rule. The comparable guarantor exposure's own-LGD treatment matters. Nuances of permitted guarantee clauses are valid optional detail.",
    },
    "cmp-003": {
        "expected_answer": "Without own LGD estimates, apply consistently either M of 2.5 years (0.5 for securities financing transactions) or the calculation under Article 162(2). With own LGD estimates, calculate M under Article 162(2), subject to paragraphs 3-5; normally M is capped at five years, with the express Article 384(2) exception. Special short-term/netting cases have their own floors, and Article 162(4) permits an option for qualifying EU non-large corporates. A one-year floor and five-year cap are not universal for every transaction.",
        "expected_citations": citations(
            (CRR, "Art. 162(1)"), (CRR, "Art. 162(2)"), (CRR, "Art. 162(4)")
        ),
        "review_note": "Required: consistent fixed-or-calculated treatment without own LGD, calculated treatment with own LGD, and qualified rather than universal limits. Exhaustive listing of short-term cases is optional.",
    },
    "cmp-006": {
        "question": "Compare CRR3 SA and own-estimate IRB treatment of an ordinary retail residential mortgage eligible for Article 125(1), assuming a sole first lien, no national override and no eligible sovereign guarantee under Article 159a.",
        "expected_answer": "SA applies the 20% loan-splitting risk weight to the part up to 55% of property value under Article 125(1); any remainder is treated as an unsecured exposure to the counterparty. Retail IRB uses own PD/LGD estimates in the relevant formula, subject under the stated assumptions to the 0.05% PD floor and 5% residential-property LGD floor. These are parameter floors, not a 5% risk weight or capital ratio.",
        "review_note": "The question supplies eligibility and excludes the relevant national/guarantee branches. Required: distinguish the SA risk weight from IRB parameter floors; do not require a calculation without necessary loan/model inputs.",
    },
    "dt-003": {
        "expected_answer": "For the calibration segment, paragraph 27(a) requires examining: (i) elevated realised LGDs, including annual default cohorts and incomplete-recovery patterns; (ii) reduced annual recoveries by relevant recovery source, with/without repossessions where applicable; (iii) reduced proportions of defaults returning to non-default within an appropriate fixed horizon; and (iv) increased time in default. Use as many sufficiently supported time points as possible, merge consecutive years where sparse data makes that useful, and consider lags between the downturn and observed losses. Paragraph 28 requires the calibration method to be coherent with that evidence.",
        "review_note": "Required: all four minimum evidence dimensions and relevant data/lag considerations. Do not treat elevated LGD alone as the complete minimum impact analysis.",
    },
    "dod-013": {
        "question": "For a retail obligor where default is applied at obligor level, how is materiality assessed when an individual credit obligation is late, and does crossing materiality alone immediately put all individual exposures in past-due default?",
        "expected_answer": "Assess the threshold on the obligor's individual credit obligations, excluding joint credit obligations with other persons/entities (EBA paragraph 105). Crossing materiality alone is not immediate past-due default: the applicable consecutive-day criterion in CRR Article 178(1)(b) must also be met. Once that individual-obligor default criterion is met, all its individual exposures are treated as defaulted; separate unlikeliness-to-pay triggers remain relevant.",
        "expected_citations": citations((DOD, "para. 105"), (CRR, "Art. 178(1)(b)")),
        "review_note": "Separate materiality aggregation from the time/default trigger. The question explicitly supplies obligor-level application and does not ask for facility-level contagion rules.",
    },
    "val-004": {
        "question": "In Section 2.4.2 of the ECB's February 2019 validation-reporting instructions, what illustrative potential RWEA-impact bands distinguish major from severe deficiencies?",
        "expected_answer": "The illustrative major-deficiency band is an impact magnitude of at least 5% but below 10%; the severe-deficiency example is 10% or more. The classification concerns significant/severe bias in risk-parameter estimates: these are illustrative potential-impact examples, not an exclusive automatic legal test based only on a percentage.",
        "expected_citations": citations(
            ("ecb-validation-reporting", "Section 2.4.2, para. 3"),
            ("ecb-validation-reporting", "Section 2.4.2, para. 4"),
        ),
        "review_note": "Require the section as well as the list-item/paragraph number. Unrelated PD/LGD/CCF statistics numbered 3 or 4 must receive no citation credit. The other two grades are optional context.",
    },
}


def main():
    directory = PROJECT_ROOT / "docs/review/golden-validity"
    audit = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    ledger = json.loads((directory / "items.json").read_text(encoding="utf-8"))
    target = {
        r["id"]
        for r in ledger
        if r["original_status"] == "verified" and r["verdict"] == "needs_correction"
    }
    assert target == set(UPDATES) and len(target) == 26
    manifest = directory / "revision-2026-11-11.json"
    if manifest.exists():
        existing = json.loads(manifest.read_text(encoding="utf-8"))
        for name, expected in existing["after_file_sha256"].items():
            assert (
                hashlib.sha256((PROJECT_ROOT / "evals/golden" / name).read_bytes()).hexdigest()
                == expected
            )
        print("Revisions already applied; hashes verified.")
        return
    before_hash = audit["source_and_scorer_inventory"]["input_sha256"]
    for name, expected in before_hash.items():
        assert (
            hashlib.sha256((PROJECT_ROOT / "evals/golden" / name).read_bytes()).hexdigest()
            == expected
        )
    changes = []
    for path in sorted((PROJECT_ROOT / "evals/golden").glob("*.jsonl")):
        with path.open(encoding="utf-8", newline="") as f:
            lines = f.readlines()
        for n, line in enumerate(lines):
            if not line.strip():
                continue
            row = json.loads(line)
            if row["id"] not in target | {"pd-004", "oos-014"}:
                continue
            original = dict(row)
            if row["id"] in target:
                updates = dict(UPDATES[row["id"]])
                note = updates.pop("review_note")
                tags = updates.pop("extra_tags", [])
                row.update(updates)
                row["notes"] = (
                    row.get("notes", "")
                    + " Source audit revision 2026-11-11 (Codex; not practitioner sign-off). "
                    + "Grading criteria and assumptions are in grading_notes."
                ).strip()
                row["grading_notes"] = note
                row["tags"] = list(
                    dict.fromkeys([*row.get("tags", []), "source-reviewed-2026-11-11", *tags])
                )
            else:
                row["status"] = "draft"
                row["notes"] = (
                    row.get("notes", "")
                    + " Quarantined 2026-11-11: unresolved in source audit; excluded from new frozen benchmark pending current-law/scope adjudication."
                ).strip()
                row["tags"] = list(
                    dict.fromkeys([*row.get("tags", []), "quarantined-source-audit"])
                )
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            lines[n] = json.dumps(row, ensure_ascii=False) + newline
            changes.append(
                {
                    "id": row["id"],
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line": n + 1,
                    "before": original,
                    "after": row,
                }
            )
        with path.open("w", encoding="utf-8", newline="") as f:
            f.writelines(lines)
    record = {
        "date": "2026-11-11",
        "revised_ids": sorted(target),
        "quarantined_ids": ["pd-004", "oos-014"],
        "before_file_sha256": before_hash,
        "after_file_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((PROJECT_ROOT / "evals/golden").glob("*.jsonl"))
        },
        "changes": changes,
    }
    with manifest.open("x", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    print(f"Revised {len(target)} items; quarantined 2; original draft examples unchanged.")


if __name__ == "__main__":
    main()
