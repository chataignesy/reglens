"""Routing: a cheap Haiku call decides whether a question goes to the single-pass pipeline
(~6k tokens) or the agent (~50k tokens). Single-answer questions never pay the agent's cost.

Order in `answer_routed`: free retrieval gate -> router (bulk tier, low effort) -> answer; a
single-pass answer that reports missing information (`missing_info`) is re-run with the agent.
"""

from __future__ import annotations

import hashlib
from datetime import date

from reglens.answer.pipeline import Answer, _parse_json, answer_question
from reglens.config import Config
from reglens.llm.provider import LLMError, LLMProvider
from reglens.retrieve.search import search

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


def answer_routed(
    conn, provider: LLMProvider, config: Config, question: str, *, today: date | None = None
) -> Answer:
    opts = config.answer or {}
    top = search(conn, question, mode="rerank", k=1)
    if not top or top[0].score < float(opts.get("abstain_below", 0.05)):
        return answer_question(conn, provider, config, question, today=today)  # gate abstains

    try:
        route, reason, tokens = route_question(provider, question)
    except LLMError as e:
        route, reason, tokens = "single", f"router failed: {e}", 0
    from reglens.agent.run import answer_agentic

    if route == "agent":
        ans = answer_agentic(conn, provider, config, question, today=today)
    else:
        ans = answer_question(conn, provider, config, question, today=today)
        if ans.missing_info:  # single pass reports a gap: let the agent look further
            tokens += ans.usage_tokens
            ans = answer_agentic(conn, provider, config, question, today=today)
            route, reason = "agent", f"fallback: single pass lacked information ({reason})"
    ans.trace.insert(0, {"tool": "route", "route": route, "reason": reason, "tokens": tokens})
    ans.usage_tokens += tokens
    return ans


__all__ = ["ROUTER_SYSTEM", "ROUTER_VERSION", "answer_routed", "route_question"]
