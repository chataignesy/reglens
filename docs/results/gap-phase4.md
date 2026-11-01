# Policy gap analysis — Phase 4 (2026-11-01)

A synthetic Model Validation Policy for the fictitious RegLens Demo Bank
([policy](../synthetic-policy/model-validation-policy.md), 53 clauses) checked against an
obligation register extracted from EU credit risk regulation
([register](../../register/obligations.jsonl)). 15 deficiencies were planted in the policy
([answer key](../synthetic-policy/gaps.yaml)); the matcher never sees the key. Reproduce:

```
uv run reglens register --yes   # obligation register (cached)
uv run reglens gap --yes        # coverage matrix + planted-gap eval (cached)
```

## Obligation register

| | |
|---|---|
| Passages in scope ([scope.yaml](../../src/reglens/gap/scope.yaml)) | 322 (≈ 95k tokens): CRR Arts. 144–191 selection, EBA GL DoD / PD-LGD / downturn LGD sections, RTS IRB assessment Ch. 3 + 14, ECB guide validation, audit, MoC |
| Obligations extracted (Sonnet, 31 calls, 229k tokens) | **752**, of which 720 flagged relevant to a validation policy |
| Quotes found verbatim in the source passage | **746 / 752**; the 6 misses are PDF-conversion artefacts (footnotes inserted mid-sentence), not invented quotes |
| By source | CRR 217 · ECB guide 221 · RTS IRB 119 · EBA GL PD/LGD 111 · EBA GL DoD 54 · EBA GL downturn 30 |

Each obligation is atomic (one actor, one action, one condition), keeps its citation key, legal
level, `applies_to`, topic and strength (shall / should / expects).

## Planted gaps

Five of each type: **missing** (e.g. no downturn LGD validation, no LGD input-floor check),
**partial** (e.g. PD back-testing every two years, MoC review of Category A only), and
**contradicted** (e.g. 1-month probation vs 3 months, internal audit every three years vs
annually, validation reporting to the head of model development). Each gap is linked to the
register obligations it breaks (28 in total).

The first draft planted a "2 % retail materiality threshold vs 1 %" gap. Checking the RTS showed
it allows competent authorities to set 0–2.5 % (the 1 % for significant institutions is in an
ECB regulation outside the corpus), so that gap was dropped and replaced (CRR Art. 185(c),
external data in validation).

## Results

The matcher (Sonnet) sees the whole policy in every call (cached system prompt) and returns one
verdict per obligation: covered / partial / missing / contradicted / not applicable / belongs in
another document, with the policy clauses and a verbatim quote (checked in code).

| | Run 1 | **Run 2** |
|---|---|---|
| Planted gaps found (recall) | 11 / 15 (0.73) | **15 / 15 (1.00)** |
| — missing / partial / contradicted | 4/5 · 3/5 · 4/5 | **5/5 · 5/5 · 5/5** |
| Flag type matches the planted type | 0.91 | **1.00** |
| Obligations flagged (partial + missing + contradicted) | 429 / 720 | 604 / 720 |
| "Belongs in another document" | 222 | 40 |
| Policy quotes not verbatim | 2 | 3 |
| Tokens | 381k | 410k |

**What changed between runs** (prompt only, no change to policy or key):
1. The bank's profile was hard-coded in the prompt ("foundation approach for corporates"), so
   the large-corporate LGD rule looked *not applicable* even though the policy's §12.2 allows
   own LGD for large corporates. The matcher now takes the bank's profile from the policy.
2. "Belongs in another document" was used for obligations worded as developer duties (MoC
   categories, PD observation period, data representativeness) although the policy has
   sections on those subjects. Now an obligation is in scope when the policy has a section on
   its subject.

**Caveats.**
- Run 2's recall is partly a tuning result: the prompt was revised after seeing which gaps
  run 1 missed, and re-tested on the same 15 gaps. A second synthetic policy with its own
  planted gaps is the clean test.
- **Precision.** A random sample of 20 non-planted findings from run 2: **20/20 factually
  correct** (the policy really does not address them), but only **≈ 11/20 belong in a
  validation policy**; the rest (e.g. repayment-likelihood criteria, currency mismatches,
  credit risk control unit staffing, the internal audit work plan) belong in other documents.
  Run 2 over-corrected run 1's over-use of "another document". The coverage matrix is a
  reviewer's starting point, filterable by topic and status, with reviewer columns in the
  Excel export, not a list of confirmed deficiencies.

## Next

1. Second synthetic policy (or a variant) with fresh planted gaps, to measure recall without
   tuning bias.
2. Precision: calibrate "belongs in another document" on a reviewer-labelled sample (e.g. 60
   findings) rather than on the planted gaps.
3. For long real policies: retrieve candidate clauses per obligation instead of sending the
   whole policy.
