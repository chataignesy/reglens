"""Match a policy against the obligation register: one verdict per obligation.

Each call gets the whole policy (numbered clauses) in the system prompt, which stays the same
for every call and is therefore read from the prompt cache, and a batch of obligations of one
topic. A short policy fits in full, so no obligation is missed because retrieval picked the wrong
section. For every obligation the model returns a status, the clauses it relies on, a verbatim
quote from the policy and a one-sentence rationale; code checks that the quote occurs in the
cited clauses. Batches are cached per prompt, policy text and obligation IDs.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from reglens.answer.pipeline import _parse_json
from reglens.config import PROJECT_ROOT
from reglens.gap.policy import Clause
from reglens.gap.register import Obligation, id_lookup, quote_in
from reglens.llm.provider import LLMProvider

STATUSES = ("covered", "partial", "missing", "contradicted", "not_applicable", "other_document")
FINDINGS = ("partial", "missing", "contradicted")
# statuses that make a claim about what the policy says: they need a cited clause and a quote
NEEDS_EVIDENCE = ("covered", "partial", "contradicted")
MATCH_DIR = PROJECT_ROOT / "data" / "gap" / "batches"
MATCH_TIER = "dev"
BATCH_SIZE = 15

MATCH_SYSTEM = """\
You review a bank's internal policy against regulatory obligations, as a credit risk model
validation expert would. Take what you know about the bank (its approaches, portfolios and
organisation) only from the policy itself.

For EACH obligation in the user message, decide how the policy below addresses it:
- "covered": the policy explicitly requires it, or states an equivalent or stricter requirement;
- "partial": the policy addresses it but misses an element (a weaker frequency, a narrower
  scope, only some of the required categories or actors);
- "contradicted": the policy states something incompatible with it (e.g. a longer period than
  allowed, a forbidden reporting line, permission for something the regulation prohibits);
- "missing": the policy does not address it at all;
- "not_applicable": it only applies to situations the policy shows the bank is not in (e.g.
  options it does not use). If the policy allows, plans or describes the situation, it is
  applicable: judge the policy against it;
- "other_document": a valid obligation that belongs in a different internal document (model
  development standards, rating-system operation, data management, outsourcing, general
  governance charters), not in a model validation policy as scoped in its section 1. Never use
  it for obligations on validation itself, on what validation must check or how often, on the
  independence or resources of validation, on findings and reporting of validation results, on
  internal audit of the rating systems, or on the roles of bodies and functions in model
  governance that the policy describes. If the policy has a section on the obligation's
  subject (e.g. data, definition of default, PD, LGD, MoC, CRM, scope of own estimates), the
  obligation is in scope even when it is worded as a duty of the model developers: judge
  whether the policy requires validation to check it.

Judge the policy as written: do not assume that unstated processes exist. A general sentence
("validation covers the model design and data") covers an obligation only if it clearly
includes what the obligation requires.

For each obligation give: "id"; "status"; "clauses": the policy clause IDs you rely on (e.g.
["§7.4"], empty for missing); "quote": a VERBATIM extract from those clauses (empty for
missing); "rationale": one sentence naming the decisive difference or match.

Reply with ONE JSON object and nothing else: {"verdicts": [ ... ]}

THE POLICY (clause IDs in brackets):
"""

MATCH_VERSION = hashlib.sha256(MATCH_SYSTEM.encode()).hexdigest()[:8]


@dataclass
class Verdict:
    obligation_id: str
    status: str
    clauses: list[str]
    quote: str
    quote_ok: bool  # the evidence holds: verbatim quote in a cited clause, or none needed
    rationale: str
    # "verified" (quote found in a cited clause), "not_verbatim" (quote not found: shown,
    # counted, for review), "none_required" (missing / not applicable / other document),
    # "invalid" (unusable model output: the status is "unassessed")
    evidence: str = "verified"
    policy_complete: bool = True


def system_prompt(clauses: list[Clause]) -> str:
    return MATCH_SYSTEM + "\n".join(c.render() for c in clauses)


def select_clauses(
    batch: list[Obligation], clauses: list[Clause], max_chars: int = 60_000
) -> tuple[list[Clause], bool]:
    """Whole short policies; bounded section/lexical candidates for long policies.
    The full clauses remain citable. Absence cannot be inferred from candidate-only coverage.
    Oversized clauses are excluded rather than silently truncated."""
    if sum(len(c.render()) + 1 for c in clauses) <= max_chars:
        return clauses, True
    terms = set(re.findall(r"[a-z]{4,}", " ".join(o.obligation for o in batch).lower()))
    ranked = sorted(
        enumerate(clauses),
        key=lambda pair: (
            -len(
                terms
                & set(re.findall(r"[a-z]{4,}", (pair[1].section + " " + pair[1].text).lower()))
            ),
            pair[0],
        ),
    )
    chosen, used = set(), 0
    # Include the policy's opening scope and adjacent clauses of each strong candidate.
    order = [0] + [i for index, _ in ranked for i in (index, index - 1, index + 1)]
    for index in order:
        if index in chosen or not 0 <= index < len(clauses):
            continue
        size = len(clauses[index].render()) + 1
        if used + size <= max_chars:
            chosen.add(index)
            used += size
    return [clauses[i] for i in sorted(chosen)], False


def batches(obligations: list[Obligation], size: int = BATCH_SIZE) -> list[list[Obligation]]:
    """Validation-relevant obligations grouped by topic, in register order."""
    by_topic: dict[str, list[Obligation]] = {}
    for o in obligations:
        if o.validation_relevant:
            by_topic.setdefault(o.topic, []).append(o)
    return [group[i : i + size] for group in by_topic.values() for i in range(0, len(group), size)]


def batch_prompt(batch: list[Obligation]) -> str:
    return "Obligations:\n" + "\n".join(
        f"- {o.id} [{o.key}] ({o.strength}) {o.obligation}" for o in batch
    )


def batch_id(batch: list[Obligation], policy: str, model: str = "") -> str:
    raw = json.dumps(
        [policy, model, "medium", batch_prompt(batch), [o.source_sha256 for o in batch]],
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def validate(oid: str, raw: dict, by_clause: dict[str, Clause]) -> Verdict:
    """One model verdict -> a Verdict, conservatively (review F6):
    - an unknown status is "unassessed (invalid output)", never turned into "missing";
    - covered / partial / contradicted assert what the policy says, so they need at least one
      existing clause and a non-empty quote; without them the verdict is "unassessed";
    - a quote not found verbatim in its clauses keeps the status, flagged "not_verbatim".
    """
    status = str(raw.get("status", "")).strip().lower()
    clauses = raw.get("clauses") or []
    if isinstance(clauses, str):  # "C3" instead of ["C3"]
        clauses = [clauses]
    named = [str(c) for c in clauses] if isinstance(clauses, list | tuple) else []
    malformed_clauses = not isinstance(clauses, list | tuple)
    cited = [c for c in named if c in by_clause]
    quote = str(raw.get("quote") or "").strip()
    rationale = str(raw.get("rationale", ""))

    def invalid(why: str) -> Verdict:
        return Verdict(
            oid,
            "unassessed",
            cited,
            quote,
            False,
            f"invalid output: {why}" + (f" ({rationale})" if rationale else ""),
            "invalid",
        )

    if status not in STATUSES:
        return invalid(f"status {status!r}")
    if malformed_clauses:
        return invalid(f"clauses must be a list, got {type(clauses).__name__}")
    if status not in NEEDS_EVIDENCE:
        return Verdict(oid, status, cited, quote, True, rationale, "none_required")
    if not cited:
        unknown = sorted(set(named) - set(cited))
        return invalid(
            f"'{status}' without an existing policy clause"
            + (f" (unknown: {', '.join(unknown)})" if unknown else "")
        )
    if not quote:
        return invalid(f"'{status}' without a quote from the policy")
    if any(quote_in(quote, by_clause[c].text) for c in cited):
        return Verdict(oid, status, cited, quote, True, rationale, "verified")
    return Verdict(oid, status, cited, quote, False, rationale, "not_verbatim")


def parse_verdicts(batch: list[Obligation], reply: str, clauses: list[Clause]) -> list[Verdict]:
    by_clause = {c.id: c for c in clauses}
    wanted = {o.id for o in batch}
    out: dict[str, Verdict] = {}
    data = _parse_json(reply)
    if not isinstance(data, dict):
        raise ValueError(f"reply is a JSON {type(data).__name__}, not an object")
    entries = data.get("verdicts")
    # second review S7: check the collection and each entry before reading fields; anything
    # malformed leaves its obligation unassessed below instead of aborting the run
    for v in entries if isinstance(entries, list) else []:
        if not isinstance(v, dict):
            continue
        oid = str(v.get("id", ""))
        if oid not in wanted or oid in out:
            continue
        out[oid] = validate(oid, v, by_clause)
    # an obligation the model skipped is reported, not silently treated as covered
    for o in batch:
        out.setdefault(
            o.id, Verdict(o.id, "unassessed", [], "", False, "no verdict returned", "invalid")
        )
    return [out[o.id] for o in batch]


def rescore(rows: list[dict], clauses: list[Clause]) -> list[Verdict]:
    """Re-validate the verdicts of a saved run under the current rules (no model calls)."""
    by_clause = {c.id: c for c in clauses}
    out = []
    for r in rows:
        if r["status"] == "unassessed" and r.get("evidence") != "invalid":
            out.append(
                Verdict(
                    r["obligation_id"],
                    "unassessed",
                    [],
                    "",
                    False,
                    r.get("rationale", ""),
                    "invalid",
                )
            )
            continue
        out.append(validate(r["obligation_id"], r, by_clause))
    return out


def match(
    provider: LLMProvider,
    obligations: list[Obligation],
    clauses: list[Clause],
    *,
    limit: int | None = None,
    log=print,
) -> tuple[list[Verdict], int]:
    out_dir = MATCH_DIR / MATCH_VERSION
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = batches(obligations)[:limit]
    verdicts, new_tokens = [], 0
    for n, batch in enumerate(todo, 1):
        selected, complete = select_clauses(batch, clauses)
        if not selected:
            verdicts += [
                Verdict(
                    o.id,
                    "unassessed",
                    [],
                    "",
                    False,
                    "No policy clauses fit the evidence budget",
                    "partial_policy",
                    False,
                )
                for o in batch
            ]
            continue
        system = system_prompt(selected)
        model = provider.config.model(MATCH_TIER) if hasattr(provider, "config") else ""
        path = out_dir / f"{batch_id(batch, system, model)}.json"
        if path.exists():
            reply = json.loads(path.read_text(encoding="utf-8"))["reply"]
        else:
            c = provider.complete(
                batch_prompt(batch), purpose="gap", system=system, tier=MATCH_TIER, effort="medium"
            )
            reply = c.text
            ids = [o.id for o in batch]
            path.write_text(json.dumps({"obligations": ids, "reply": reply}, ensure_ascii=False))
            new_tokens += c.usage.total_tokens
            used = c.usage.total_tokens
            log(f"  [{n}/{len(todo)}] {batch[0].topic} ({len(batch)}): {used:,} tokens")
        try:
            parsed = parse_verdicts(batch, reply, selected)
            if not complete:
                # Candidate retrieval cannot prove absence from an unseen part of a policy.
                for v in parsed:
                    v.policy_complete = False
                    if v.status in ("missing", "not_applicable", "other_document"):
                        v.status, v.evidence = "unassessed", "partial_policy"
                        v.quote_ok = False
                        v.rationale = (
                            "Partial policy searched; absence/applicability needs review. "
                            + v.rationale
                        )
            verdicts += parsed
        except (ValueError, TypeError, AttributeError) as e:  # JSONDecodeError is a ValueError
            log(f"  [{n}] unparseable reply: {e}")
            verdicts += [
                Verdict(o.id, "unassessed", [], "", False, f"unparseable reply: {e}", "invalid")
                for o in batch
            ]
    return verdicts, new_tokens


def to_rows(verdicts: list[Verdict], obligations: list[Obligation]) -> list[dict]:
    """Coverage matrix rows: obligation + verdict + an empty reviewer column."""
    by_id = id_lookup(obligations)
    rows = []
    for v in verdicts:
        o = by_id[v.obligation_id]
        rows.append(
            {
                "obligation_id": o.id,
                "source": o.key,
                "level": o.legal_level,
                "topic": o.topic,
                "actor": o.actor,
                "obligation": o.obligation,
                **{k: val for k, val in asdict(v).items() if k != "obligation_id"},
                "reviewer_status": "",
                "reviewer_comment": "",
            }
        )
    return rows
