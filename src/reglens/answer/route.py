"""Routing: a cheap Haiku call decides whether a question goes to the single-pass pipeline
(~6k tokens) or the agent (~50k tokens). Single-answer questions never pay the agent's cost.

Order in `answer_routed`: free retrieval gate -> router (bulk tier, low effort) -> answer; a
single-pass answer that reports missing information (`missing_info`) is re-run with the agent.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date

from reglens.answer.pipeline import Answer, Progress, _parse_json, answer_question
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

Reply with ONE JSON object and nothing else: {"route": "single", "reason": "a few words"}
"""

ROUTER_VERSION = hashlib.sha256(ROUTER_SYSTEM.encode()).hexdigest()[:8]
ROUTES = ("single", "agent")


def route_question(provider: LLMProvider, question: str) -> tuple[str, str, int]:
    """(route, reason, tokens). Falls back to 'single' if the reply is unusable."""
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
        return answer_question(conn, provider, config, question, today=today, progress=progress,
                               filters=filters)

    emit({"stage": "routing"})
    try:
        route, reason, tokens = route_question(provider, question)
    except LLMError as e:
        route, reason, tokens = "single", f"router failed: {e}", 0
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
    )
    ans.trace.insert(0, {"tool": "route"} | outcome)
    ans.usage_tokens = outcome["tokens"]
    return ans


def _failed(a) -> bool:
    """No usable answer (agent cost cap, no tool calls, invalid output, ...)."""
    if isinstance(a, dict):
        return not a.get("answer") and bool(a.get("errors")) and not a.get("abstained")
    return not a.answer and bool(a.errors) and not a.abstained


def _gap(a) -> bool:
    return bool(a.get("missing_info") if isinstance(a, dict) else a.missing_info)


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

    def run(mode: str):
        nonlocal spent
        attempts.append(mode)
        a = (agent if mode == "agent" else single)()
        spent += _tokens(a)
        return a

    if planned == "agent":
        final = run("agent")
        if _failed(final):
            why = "; ".join(final.get("errors") if isinstance(final, dict) else final.errors)
            emit({"stage": "agent_failed", "reason": why})
            final, route, reason = run("single"), "single", f"agent stopped ({why}); single pass"
        else:
            route = "agent"
    else:
        final, route = run("single"), "single"
        if _gap(final):  # single pass reports a gap: let the agent look further
            emit({"stage": "fallback"})
            first = final
            final = run("agent")
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
    }
    return final, outcome


__all__ = ["ROUTER_SYSTEM", "ROUTER_VERSION", "answer_routed", "dispatch", "route_question"]
