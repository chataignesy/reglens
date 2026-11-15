# Golden evaluation set

One question per line in `*.jsonl`. Validate with `uv run reglens golden`.
Target: 30 questions in Phase 0 (incl. ≥ 5 out-of-scope), ~150 by Phase 2.

| Field | Meaning |
|---|---|
| `id` | Stable key, e.g. `dod-001` |
| `question` | As a modeller/validator would ask it |
| `type` | `factual` · `multi_hop` (needs cross-references/definitions) · `comparison` (e.g. SA vs IRB, CRR2 vs CRR3) · `applicability` (SI vs LSI) · `out_of_scope` (system must abstain) |
| `expected_answer` | Short reference answer: the key facts a correct answer must contain |
| `expected_citations` | `[{"source": "<id from sources.yaml>", "ref": "Art. 178(1)(b)"}]`; empty for `out_of_scope`. Optional `"alternatives": [{"source": …, "ref": …}]` per citation: equivalent references that also count as finding it (e.g. the ECB guide restating an EBA paragraph) |
| `applies_to` | `SI` · `LSI` · `all` |
| `topic` | e.g. `definition-of-default`, `pd-estimation`, `lgd`, `crm`, `validation`, `output-floor` |
| `difficulty` | `easy` · `medium` · `hard` |
| `author` | Who wrote it |
| `status` | `draft` until checked against the source text, then `verified` |
| `notes` | Optional: pitfalls, ambiguity and review provenance; not sent as grading instructions |
| `grading_notes` | Optional: required vs optional facts, date/scenario assumptions; included in the judge prompt and verdict cache key |
| `tags` | Optional list |

Guidelines:
- Write from real practice — the questions you or your validators actually ask.
- Mix types: about 50% factual, 25% multi-hop, 10% comparison/applicability, 15% out-of-scope.
- Cite the most specific paragraph you can; the retrieval eval scores against these refs.
- Only `verified` items count in milestone (published) results.
- `examples.jsonl` holds format examples written by Claude — **check or replace them**; they are
  `draft` and not authoritative.

## Reviewed baseline (11 November 2026)

The current working set has 118 source-checked (`verified`) records and five drafts. Twenty-six
formal questions were revised following the [source audit](../../docs/GOLDEN-VALIDITY-REVIEW-2026-11-11.md).
The unresolved `pd-004` and `oos-014` are drafts excluded from evaluation; the three original
example drafts remain unchanged. `verified` records a source check, not practitioner sign-off.
Published milestone claims still need appropriate independent domain adjudication.

For repeated PDF list numbers use a section-qualified reference, e.g.
`Section 2.4.2, para. 3`. The scorer checks the retrieved passage's stored hierarchy; a paragraph
with the same number in another section earns no credit. Missing historical section metadata
also earns no credit for a section-qualified reference. `Foreword, para. 7` remains a
part-qualified reference.

See the [snapshot index](../frozen/README.md) for the revised 118-item snapshot and the unchanged
original 120-item snapshot. These are development baselines. Historical and end-state questions
are explicitly qualified; the dataset is not a complete statement of current law.
