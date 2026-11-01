# RegLens Demo Bank — Model Validation Policy

> **Synthetic document.** RegLens Demo Bank is fictitious. This policy was written from scratch
> as demo input for the RegLens gap analysis; it is deliberately incomplete and contains planted
> deficiencies. It is not based on any real institution's policy and must not be used as one.

| | |
|---|---|
| Document owner | Head of Model Validation |
| Approved by | Management Board, 14 March 2026 |
| Version | 3.2 |
| Next review | March 2027 |

## 1. Purpose, scope and document control

1.1 This Policy sets out how RegLens Demo Bank ("the Bank") validates the internal models it uses
to calculate own funds requirements for credit risk under the Internal Ratings Based (IRB)
Approach of Regulation (EU) No 575/2013 (CRR).

1.2 The Policy applies to all IRB rating systems and their components: probability of default
(PD) models, loss given default (LGD) models including LGD in-default and the best estimate of
expected loss (ELBE), and conversion factor (CCF) models. The Bank uses own estimates of PD, LGD
and CCF for retail exposures and own estimates of PD for corporate exposures.

1.3 The Policy applies to the Bank and to all subsidiaries that use the Bank's IRB rating systems.

1.4 The Head of Model Validation owns this Policy. Changes are recorded in the version history
held in the Bank's policy register.

## 2. Definitions

2.1 **Rating system:** all methods, processes, controls, data collection and IT systems that
support the assessment of credit risk, the assignment of exposures to grades or pools and the
quantification of default and loss estimates for a given type of exposure.

2.2 **Initial validation:** the validation of a new rating system before its first use for own
funds requirements. **Regular validation:** the recurring validation of a rating system in use.

2.3 **Finding:** a deficiency identified by the validation function, rated by severity (§13).

2.4 **Margin of conservatism (MoC):** the add-on to risk parameter estimates that reflects
identified deficiencies and estimation error.

2.5 **Default:** as defined in §7.

## 3. Governance and roles

3.1 The **Management Board** approves this Policy and receives the annual validation report. It
is responsible for ensuring that the Bank's rating systems are sound and appropriately validated.

3.2 The **Model Risk Committee (MRC)**, chaired by the Chief Risk Officer, oversees model risk,
approves validation plans and decides on the use of models with open findings.

3.3 **Model owners** in the business and risk departments are responsible for the performance
and use of their models. **Model developers** in the Model Development & Analytics department
design, estimate, calibrate and document the models.

3.4 New rating systems are approved by the MRC after initial validation. Material changes to
rating systems are approved by the Head of Model Development, who informs the MRC at its next
meeting.

## 4. Independence and resources of the validation function

4.1 Validation is performed by the Model Validation team. The team is part of the Model
Development & Analytics department and reports to the Head of Model Development, with a dotted
reporting line to the Chief Risk Officer for validation matters.

4.2 Validators do not validate models they have developed themselves. Where a validator was
previously involved in the development of a model, another validator is assigned.

4.3 The Model Validation team is staffed with sufficient quantitative and credit risk expertise
for the Bank's model inventory. Staffing and skills are reviewed annually as part of the
validation plan.

## 5. Model inventory and materiality

5.1 All IRB models are recorded in the model inventory, maintained by Model Validation. Each
entry records the model owner, developer, scope of application, status, last validation date and
open findings.

5.2 Models are classified into three tiers based on the exposure covered and the
risk-weighted exposure amounts. The tier determines the depth of validation work, not whether a
model is validated.

## 6. Validation types and frequency

6.1 **Initial validation** is performed for every new rating system before the Bank applies for
permission to use it or before its first use for own funds requirements.

6.2 **Regular validation** is performed at least annually for all rating systems in use. It
covers the model design, the data, the quantitative performance (discriminatory power,
calibration and stability) and the use of the model. Validation relies on the Bank's internal
data only: external data sources and benchmarks are not used, because they are not considered
representative of the Bank's portfolios.

6.3 **Ad hoc validation** is performed at the request of the MRC, for example after a
significant deterioration of model performance.

6.4 The annual validation plan is approved by the MRC.

## 7. Data and definition of default

7.1 Validation checks the data used for estimation and application for completeness, accuracy
and timeliness, and reviews the results of the data quality controls performed by the model
owners.

7.2 **Default definition.** An obligor is in default when (a) the Bank considers the obligor
unlikely to pay its credit obligations in full without realisation of collateral, or (b) the
obligor is more than 90 days past due on a material credit obligation.

7.3 **Materiality threshold.** For retail exposures a credit obligation past due is material
when the amount past due exceeds both EUR 100 and 1 % of the total on-balance-sheet exposure
to that obligor. For other exposures the thresholds are EUR 500 and 1 %.

7.4 **Return to non-defaulted status.** An exposure returns to non-defaulted status when no
default trigger has applied for one month and the obligor's situation has improved. Exposures
subject to distressed restructuring remain in default for at least one year.

7.5 Validation checks that the same definition of default is applied consistently across
models, portfolios and subsidiaries, and in the data used for estimation.

## 8. PD validation

8.1 Validation assesses the rating process, the assignment of obligors to grades, and the
stability of the rating distribution over time.

8.2 **Discriminatory power** is assessed annually using the area under the ROC curve (AUC) and
its change compared with the initial validation.

8.3 **Calibration.** Back-testing compares realised default rates with estimated PDs for each
grade every two years, using binomial and Jeffreys tests. Deviations outside the tolerance
levels in the Annex are analysed and reported to the MRC.

8.4 Validation reviews whether the PD estimates are long-run averages of one-year default rates.

## 9. LGD, ELBE and LGD in-default validation

9.1 **Back-testing.** Realised LGDs are compared with estimated LGDs for each pool or grade
annually. Validation reviews the treatment of incomplete recovery processes and of costs.

9.2 **Defaulted exposures.** Validation checks that ELBE reflects current economic
circumstances and that LGD in-default exceeds ELBE by an amount that reflects possible
additional losses during the recovery period.

9.3 Validation reviews the discount rate and the treatment of cures and repeated defaults in the
realised LGD data.

## 10. CCF validation

10.1 Where the Bank uses own estimates of conversion factors, validation compares realised and
estimated CCFs per pool, reviews the treatment of facilities with limits and checks that own
estimates are only used where the CRR permits them.

## 11. Margin of conservatism

11.1 Validation reviews the deficiencies identified by the model developers in data and
methodology (Category A) and assesses whether the MoC quantified for them is adequate.

11.2 The overall MoC and its components are documented in the model documentation and in the
validation report.

## 12. Credit risk mitigation and scope checks

12.1 Validation checks that collateral and guarantees are recognised in LGD estimates only where
they meet the Bank's eligibility criteria and that the value of collateral is monitored.

12.2 Corporate exposures are rated under the foundation approach. Exposures to large corporates
may migrate to own estimates of LGD where the Bank has at least five years of loss data for that
segment and the MRC approves the change.

## 13. Findings, severity and remediation

13.1 Findings are rated *high*, *medium* or *low*. Each finding has an owner and a remediation
deadline: six months for high, twelve months for medium and eighteen months for low findings.

13.2 Model Validation tracks all open findings in the model inventory and reports overdue
findings to the MRC quarterly.

13.3 Where a high finding is not remediated in time, the MRC decides on measures, which may
include an additional MoC or restrictions on the use of the model.

## 14. Reporting

14.1 Model Validation prepares a validation report for every validation, addressed to the model
owner and the MRC.

14.2 An annual validation report summarising the results for all rating systems, open findings
and the overall assessment of model risk is presented to the Management Board.

14.3 As a significant institution, the Bank reports the results of the annual validation of its
IRB models to the ECB in line with the ECB's reporting instructions.

## 15. Internal audit

15.1 Internal Audit reviews the Model Validation team every three years as part of the audit plan,
including its independence, methods and the quality of its reports.

## 16. Policy review

16.1 This Policy is reviewed at least annually by the Head of Model Validation and whenever
regulatory changes require it, for example changes to input floors or the output floor under
CRR3. Changes are approved by the Management Board.

16.2 Model owners update the estimates of their models when validation identifies material
deficiencies.

## Annex — standard tests and tolerance levels

| Parameter | Test | Green | Amber | Red |
|---|---|---|---|---|
| PD | AUC (change since initial validation) | ≥ −5 pp | −5 to −10 pp | < −10 pp |
| PD | Jeffreys test per grade (p-value) | ≥ 5 % | 1–5 % | < 1 % |
| LGD | Realised vs estimated (difference) | ≤ 5 pp | 5–10 pp | > 10 pp |
| CCF | Realised vs estimated (difference) | ≤ 5 pp | 5–10 pp | > 10 pp |
| All | Population stability index | < 0.10 | 0.10–0.25 | > 0.25 |
