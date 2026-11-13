# Frozen development datasets

| Version | Items | Snapshot | Meaning |
|---|---:|---|---|
| 2026-11-13 runtime-review revision | 118 | [20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b.json](20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b.json) | Current development baseline: clarify Article 123(1) threshold versus Article 123(4) natural-person exception in `sa-004` |
| 2026-11-11 source-audit revision | 118 | [24da390da84fc23a115c266f0ddb6d422af0819fb5844aa0e9e53e1c06856a9f.json](24da390da84fc23a115c266f0ddb6d422af0819fb5844aa0e9e53e1c06856a9f.json) | Historical source-audit baseline: 26 revised items, two unresolved items quarantined |
| 2026-11-11 original | 120 | [21c65bff731ac866cd1710f1411849ec3441089b5eb6b3a5949a34e1c2844326.json](21c65bff731ac866cd1710f1411849ec3441089b5eb6b3a5949a34e1c2844326.json) | Original pre-audit development references, retained unchanged for historical reproducibility |

All are **development** datasets, not independent holdouts or practitioner-certified legal
truth. Snapshot filenames hash their canonical JSON content. Do not edit a snapshot in place;
change the working golden files and create another content-addressed snapshot instead.

The revised dataset excludes `pd-004` (current-law reconciliation) and `oos-014` (scope decision).
Those records remain in the working set as drafts, along with the three original example drafts.
`dod-008` is explicitly a historical question about the original 2016 DoD text before the
amendment applying from 19 October 2026. Its 30-day answer is not current-law guidance. The corpus
was not updated in this revision; a current 90-day question needs the amended source ingested.

Revisions, rationale and required/optional grading guidance are documented in
[the revision note](../../docs/GOLDEN-REVISION-2026-11-11.md). Judge guidance and qualified PDF
sections are now used in scoring. Historical answers without section metadata cannot establish
a section-qualified citation. The legacy parent/child reference matcher remains permissive;
a frozen reference set does not certify the whole scorer or semantic correctness.

Dry run (no LLM calls unless `--yes` is explicitly added):

```powershell
uv run reglens eval-answers --set all --snapshot evals/frozen/20d15f898cdbb3884c604c0fd36d67f414b764833768b200baaa8122132eba7b.json
```

After an actual answer run, use its emitted run ID with `reglens judge --run RUN_ID`.
Do not compare old headline scores with the revised set as if question/reference/cohort and
scoring rules were identical. The 11 November set has a complete recorded run; the 13 November
revision has targeted live regressions, not a new full benchmark. See the
[runtime review and implementation](../../docs/review/REVIEW-FROZEN118-2026-11-13.md).
