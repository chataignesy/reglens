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
| `notes` | Optional: pitfalls, ambiguity, why it is hard |
| `tags` | Optional list |

Guidelines:
- Write from real practice — the questions you or your validators actually ask.
- Mix types: about 50% factual, 25% multi-hop, 10% comparison/applicability, 15% out-of-scope.
- Cite the most specific paragraph you can; the retrieval eval scores against these refs.
- Only `verified` items count in milestone (published) results.
- `examples.jsonl` holds format examples written by Claude — **check or replace them**; they are
  `draft` and not authoritative.
