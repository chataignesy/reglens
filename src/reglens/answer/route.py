"""Routing: a bulk-tier call selects single-pass or agent research.

Order in `answer_routed`: free retrieval gate -> router (bulk tier, low effort) -> answer; a
single-pass answer requests more research only for required, retrievable gaps.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date

from reglens.answer.pipeline import Answer, Progress, _parse_json, answer_question
from reglens.answer.prompts import SCOPE
from reglens.config import Config
from reglens.llm.provider import LLMError, LLMProvider
from reglens.retrieve.search import Filters, search

ROUTER_SYSTEM = """\
You route questions about EU credit risk regulation (CRR, RTS, EBA guidelines and Q&A, ECB guide
to internal models) to one of two answering modes.

"single": one search finds the answer: a definition, a threshold or number, a single article's
  requirement, or one guideline topic, even if the answer is long.
"agent": the answer must chain several provisions: a rule that depends on another (exposure
  class -> definition -> treatment), law plus the RTS or guideline that specifies it, two
  conditions from different articles combined, or a comparison of approaches or versions.

Choose based on what the question actually asks, not every related issue one could research:
- A specified document's content, stated scope, limits or version change is single when its
  passages can answer it. Do not add a current-law or wider-supervisory-framework investigation.
- Accept scenario assumptions the user has supplied (eligibility, full collateral coverage,
  absence of an override); do not route to agent just to independently establish them.
- Multiple requested facts in one article or guideline topic can still be single.
- A mention of law, an exception, date, comparison or a long answer alone does not require agent.
- Outside-corpus questions go to single for refusal, never agent to search unrelated topics.
- Use agent when indispensable evidence must actually be connected across provisions. If
  unsure whether extra research is needed, start single; a required evidence gap can escalate.

Reply with ONE JSON object and nothing else: {"route": "single", "reason": "a few words"}
"""

ROUTER_SYSTEM += "\nCorpus scope:\n" + SCOPE

ROUTER_VERSION = hashlib.sha256(ROUTER_SYSTEM.encode()).hexdigest()[:8]
ROUTES = ("single", "agent")


def route_question(
    provider: LLMProvider, question: str, *, strategy: str = "llm"
) -> tuple[str, str, int]:
    """(route, reason, tokens). Falls back to 'single' if the reply is unusable."""
    if strategy == "single_first":
        return "single", "Single-first policy; bounded required-gap fallback remains enabled", 0
    if strategy != "llm":
        raise ValueError("Routing must be 'llm' or 'single_first'")
    c = provider.complete(
        f"Question:\n{question}",
        purpose="route",
        system=ROUTER_SYSTEM,
        tier="bulk",
        effort="low",
    )
    try:
        data = _parse_json(c.text)
    except ValueError:
        return "single", "unparseable router reply", c.usage.total_tokens
    route = str(data.get("route", "")).strip().lower()
    reason = str(data.get("reason", ""))
    return (route if route in ROUTES else "single"), reason, c.usage.total_tokens


def gate_abstains(conn, config: Config, question: str, filters: Filters | None = None) -> bool:
    """The free retrieval gate: no relevant passage at all, so no router or answer call."""
    from reglens.answer.scope import refusal_reason

    if refusal_reason(question):
        return True
    top = search(conn, question, mode="rerank", k=1, filters=filters)
    return not top or top[0].score < float((config.answer or {}).get("abstain_below", 0.05))


def answer_routed(
    conn,
    provider: LLMProvider,
    config: Config,
    question: str,
    *,
    today: date | None = None,
    progress: Progress | None = None,
    filters: Filters | None = None,
) -> Answer:
    """`filters.applies_to` ("SI" / "LSI") holds in every route: gate, single pass, agent."""
    emit = progress or (lambda event: None)
    if gate_abstains(conn, config, question, filters):  # no router call: abstains for free
        return answer_question(
            conn, provider, config, question, today=today, progress=progress, filters=filters
        )

    emit({"stage": "routing"})
    router_unknown = 0
    try:
        strategy = (config.answer or {}).get("routing", "llm")
        route, reason, tokens = (route_question(provider, question) if strategy == "llm"
                                 else route_question(provider, question, strategy=strategy))
    except LLMError as e:
        route, reason, tokens = "single", f"router failed: {e}", e.tokens or 0
        router_unknown = int(not e.usage_known)
    emit({"stage": "routed", "route": route, "reason": reason})
    from reglens.agent.run import answer_agentic

    ans, outcome = dispatch(
        route,
        reason,
        tokens,
        single=lambda: answer_question(
            conn, provider, config, question, today=today, progress=progress, filters=filters
        ),
        agent=lambda: answer_agentic(
            conn, provider, config, question, today=today, progress=progress, filters=filters
        ),
        emit=emit,
        router_usage_unknown_calls=router_unknown,
        complete=lambda first: answer_agentic(
            conn,
            provider,
            config,
            question,
            today=today,
            progress=progress,
            filters=filters,
            research_requirements=first.missing_requirements,
        ),
    )
    ans.trace.insert(0, {"tool": "route"} | outcome)
    ans.usage_tokens = outcome["tokens"]
    ans.usage_unknown_calls = outcome["usage_unknown_calls"]
    return ans


def _failed(a) -> bool:
    """No usable answer (agent cost cap, no tool calls, invalid output, ...)."""
    if isinstance(a, dict):
        return not a.get("abstained") and (
            not str(a.get("answer") or "").strip() or bool(a.get("unverified"))
        )
    return not a.abstained and (not a.answer.strip() or a.unverified)


def _interrupted(a) -> bool:
    """Changing answer strategy cannot repair a provider-wide outage or quota refusal."""
    from reglens.llm.provider import transient_error

    if isinstance(a, dict):
        if "retryable_error" in a:
            return bool(a["retryable_error"])
        return any(transient_error(str(e)) for e in a.get("errors", []))
    return a.retryable_error


def _gap(a) -> bool:
    from reglens.answer.research import needs_research

    return needs_research(a)


def _tokens(a) -> int:
    return int((a.get("usage_tokens") if isinstance(a, dict) else a.usage_tokens) or 0)


def dispatch[A](
    planned: str,
    reason: str,
    router_tokens: int,
    *,
    single: Callable[[], A],
    agent: Callable[[], A],
    emit: Callable[[dict], None] = lambda e: None,
    router_usage_unknown_calls: int = 0,
    complete: Callable[[A], A] | None = None,
) -> tuple[A, dict]:
    """Run the routed plan; the ONE place that decides fallbacks (used by the app and the eval).

    - planned agent: if the agent ends without a usable answer, answer single-pass instead;
    - planned single: if the answer reports missing information, try the agent; keep the
      single-pass answer if the agent then fails.
    Works on Answer objects or on cached answer records (dicts). Returns (final answer,
    outcome) where outcome records the plan, every attempt and all tokens spent, including
    the router and failed attempts.
    """
    attempts: list[str] = []
    spent = router_tokens
    unknown = router_usage_unknown_calls
    attempt_errors = []

    def run(mode: str, previous=None):
        nonlocal spent, unknown
        attempts.append(mode)
        a = (
            complete(previous)
            if mode == "agent" and previous is not None and complete
            else (agent if mode == "agent" else single)()
        )
        spent += _tokens(a)
        unknown += int(
            a.get("usage_unknown_calls", 0) if isinstance(a, dict) else a.usage_unknown_calls
        )
        errors = a.get("errors", []) if isinstance(a, dict) else a.errors
        if not errors and _failed(a):
            errors = ["empty or unverified answer"]
        if errors:
            attempt_errors.append({"mode": mode, "errors": list(errors)})
        return a

    if planned == "agent":
        final = run("agent")
        if _failed(final) and not _interrupted(final):
            why = "; ".join(
                (final.get("errors", []) if isinstance(final, dict) else final.errors)
                or ["empty or unverified answer"]
            )
            emit({"stage": "agent_failed", "reason": why})
            final, route, reason = run("single"), "single", f"agent stopped ({why}); single pass"
        else:
            route = "agent"
    else:
        final, route = run("single"), "single"
        if not _interrupted(final) and (_failed(final) or _gap(final)):
            emit({"stage": "fallback"})
            first = final
            final = run("agent", first)
            if _failed(final):
                final, reason = first, f"agent fallback failed; single-pass answer ({reason})"
            else:
                route, reason = "agent", f"fallback: single pass lacked information ({reason})"
    outcome = {
        "planned": planned,
        "route": route,
        "reason": reason,
        "attempts": attempts,
        "router_tokens": router_tokens,
        "tokens": spent,
        "usage_unknown_calls": unknown,
        "attempt_errors": attempt_errors,
    }
    return final, outcome


__all__ = ["ROUTER_SYSTEM", "ROUTER_VERSION", "answer_routed", "dispatch", "route_question"]
