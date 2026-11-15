# Golden-set validity review plan

Started 11 November 2026. Review all 123 records: 120 currently labelled verified and three
format-example drafts. Existing golden files and frozen snapshots remain unchanged during the
review; proposed corrections and evidence form a separate item-level audit.

1. Inventory every item, its file/line/hash, author/status, scope and expected references. Check
   duplicates, malformed references, empty answers and source coverage mechanically.
2. Establish source provenance: compare local raw files and cited chunks with sources.lock.json;
   check official EUR-Lex/EBA/ECB publications and version/status information online. Review
   against the project's pinned corpus, separately flagging claims about current applicability.
3. Resolve and read each cited passage, including ranges and every accepted alternative. Missing
   indexed evidence requires a raw-source check; retrieval failure alone is not invalid law.
4. Review every question and expected answer for factual support, numbers, omitted conditions and
   exceptions, legal force, version, applicability, ambiguity and whether the answer addresses
   the actual question. Assess out-of-scope items against explicit product boundaries.
5. Check benchmark fairness: required facts vs optional detail, equivalent valid answers,
   over-specific/incorrect citations, ambiguous multi-hop assumptions, development leakage and
   the lack of independent practitioner adjudication. A verified label is not itself evidence.
6. Produce a ledger for every ID: supported, needs_correction, or unresolved, with distinct
   question/answer/citation/scope findings, evidence locations, confidence and proposed changes.
   Publish a Chinese summary and prioritized recommendations. Preserve historical benchmarks;
   approved corrections need a new evaluation snapshot and a fresh baseline.

No external LLM grading or paid runs are needed for this review. Automated checks locate evidence;
semantic judgments are recorded separately. This is a source-grounded benchmark audit, not legal
sign-off. Unavailable official text or unresolved interpretation will be stated explicitly.
