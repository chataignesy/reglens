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
from dataclasses import asdict, dataclass

from reglens.answer.pipeline import _parse_json
from reglens.config import PROJECT_ROOT
from reglens.gap.policy import Clause
from reglens.gap.register import Obligation, quote_in
from reglens.llm.provider import LLMProvider

STATUSES = ("covered", "partial", "missing", "contradicted", "not_applicable", "other_document")
FINDINGS = ("partial", "missing", "contradicted")
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
    quote_ok: bool  # empty quote for missing counts as ok
    rationale: str


def system_prompt(clauses: list[Clause]) -> str:
    return MATCH_SYSTEM + "\n".join(c.render() for c in clauses)


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


def batch_id(batch: list[Obligation], policy: str) -> str:
    raw = policy + "|" + ",".join(o.id + o.obligation for o in batch)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def parse_verdicts(batch: list[Obligation], reply: str, clauses: list[Clause]) -> list[Verdict]:
    by_clause = {c.id: c for c in clauses}
    wanted = {o.id for o in batch}
    out: dict[str, Verdict] = {}
    for v in _parse_json(reply).get("verdicts") or []:
        oid = str(v.get("id", ""))
        if oid not in wanted or oid in out:
            continue
        status = str(v.get("status", "")).strip().lower()
        cited = [str(c) for c in v.get("clauses") or [] if str(c) in by_clause]
        quote = str(v.get("quote", ""))
        ok = not quote or any(quote_in(quote, by_clause[c].text) for c in cited)
        out[oid] = Verdict(
            oid, status if status in STATUSES else "missing", cited, quote, ok,
            str(v.get("rationale", "")),
        )
    # an obligation the model skipped is reported, not silently treated as covered
    for o in batch:
        out.setdefault(o.id, Verdict(o.id, "unassessed", [], "", True, "no verdict returned"))
    return [out[o.id] for o in batch]


def match(
    provider: LLMProvider,
    obligations: list[Obligation],
    clauses: list[Clause],
    *,
    limit: int | None = None,
    log=print,
) -> tuple[list[Verdict], int]:
    system = system_prompt(clauses)
    out_dir = MATCH_DIR / MATCH_VERSION
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = batches(obligations)[:limit]
    verdicts, new_tokens = [], 0
    for n, batch in enumerate(todo, 1):
        path = out_dir / f"{batch_id(batch, system)}.json"
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
            verdicts += parse_verdicts(batch, reply, clauses)
        except (ValueError, json.JSONDecodeError) as e:
            log(f"  [{n}] unparseable reply: {e}")
            verdicts += [Verdict(o.id, "unassessed", [], "", True, "unparseable") for o in batch]
    return verdicts, new_tokens


def to_rows(verdicts: list[Verdict], obligations: list[Obligation]) -> list[dict]:
    """Coverage matrix rows: obligation + verdict + an empty reviewer column."""
    by_id = {o.id: o for o in obligations}
    rows = []
    for v in verdicts:
        o = by_id[v.obligation_id]
        rows.append(
            {
                "obligation_id": o.id, "source": o.key, "level": o.legal_level, "topic": o.topic,
                "actor": o.actor, "obligation": o.obligation,
                **{k: val for k, val in asdict(v).items() if k != "obligation_id"},
                "reviewer_status": "", "reviewer_comment": "",
            }
        )
    return rows
