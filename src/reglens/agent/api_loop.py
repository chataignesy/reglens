"""Agent loop on the Anthropic Messages API (bring-your-own-key demo): the same tools, prompt and
citation keys as the `claude -p` + MCP path, but the loop and all limits run in RegLens code.

Limits per question (config `agent`):
- `max_calls` tool calls: the Toolbox stops returning data after this many;
- `max_turns` model calls: a hard stop, whatever the model does;
- `max_tokens_per_question`: total tokens across turns (from each response's usage).
When a limit is reached the model is told to answer now with what it has; tool calls after that
get an error result. Every model call goes through the provider, so it is logged to the ledger.

Tools run in-process (no MCP server). Uses the documented manual tool-use loop.
"""

from __future__ import annotations

import re

from reglens.agent.contracts import TOOL_SCHEMAS
from reglens.agent.contracts import invoke as _run_tool
from reglens.agent.tools import Toolbox, partial_reads, trace_entry
from reglens.llm.provider import AnthropicAPIProvider, LLMError

STOP_NOTE = (
    "Limit reached: no more tool calls. Answer now with the passages you already have, in the "
    "required JSON, and say in the answer text what is missing."
)


def _check_cancel(provider) -> None:
    """Second review S2: stop downstream work (tools, continuation, final answer) as soon as
    the question is cancelled, even while an SDK request was in flight. Raises Cancelled."""
    token = getattr(provider, "cancel", None)
    if token is not None:
        token.check()


def _with_cache(messages: list[dict]) -> list[dict]:
    """Copy with a cache breakpoint on the last block, so each turn reuses the previous prefix."""
    out = [dict(m) for m in messages]
    last = out[-1]
    content = last["content"]
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    content = [dict(b) if isinstance(b, dict) else b for b in content]
    if isinstance(content[-1], dict):
        content[-1] = content[-1] | {"cache_control": {"type": "ephemeral"}}
    last["content"] = content
    return out


def _completeness_note(text: str, trace: list[dict], conn=None, question: str = "") -> str | None:
    """Why a first final answer is not complete yet (review R1): it cites passages read only
    as truncated snippets, or it reports missing information itself. None when complete."""
    from reglens.answer.schema import parse_reply

    data, problems = parse_reply(text)
    if problems or not data or data.get("abstain"):
        return None
    from reglens.answer.research import guard

    guard(question, data, [])
    cited = {str(k) for c in data.get("claims") or [] for k in c.get("citations") or []}
    cited |= set(re.findall(r"\[([^\[\]]+?)\]", str(data.get("answer") or "")))
    cut = sorted(cited & partial_reads(trace, conn))
    if cut:
        return (
            "Your answer relies on passages you only saw in part (truncated, or not all "
            "of their parts): " + "; ".join(cut) + ". Read them in full with get_passage."
        )
    from reglens.answer.research import completion_note, needs_research

    if not needs_research(data):
        return None
    if note := completion_note(data):
        return note
    if data.get("missing_info"):
        return (
            "Your answer says information is missing. If a tool can find it (the RTS or "
            "article a passage refers to, a truncated passage), look for it."
        )
    return None


def run_api_agent(
    conn,
    provider: AnthropicAPIProvider,
    question: str,
    *,
    system: str,
    tier: str | None,
    effort: str | None,
    max_calls: int,
    max_turns: int,
    max_tokens: int,
    progress=None,
    applies_to: str | None = None,
    filters=None,
) -> tuple[str, list[dict], int, str, list[str]]:
    """Run the loop. Returns (final text, tool trace, total tokens, model, errors).

    Limits are enforced BEFORE each request (review F8):
    - a request is sent only if the tokens spent so far plus the expected size of that request
      (the previous request grows by its tool results; 1.3x as margin) stay within
      `max_tokens` minus a reserve for the final answer; otherwise that turn is the final one;
    - the final turn (call budget used, reserve reached, or last turn) is sent with
      `tool_choice: none`, so the model must answer and cannot keep calling tools;
    - once `max_tokens` is spent, no request is sent at all.
    The only overshoot possible is the final answer request itself exceeding its reserve.
    """
    box = Toolbox(conn, max_calls=max_calls, applies_to=applies_to, filters=filters)
    messages: list[dict] = [{"role": "user", "content": question}]
    trace: list[dict] = []
    tokens, model, errors = 0, "", []
    reserve = max(max_tokens // 5, 1)  # kept for the final answer
    last = 0  # tokens of the previous request: the next one is at least that big
    stop = False  # set once a limit is reached: the next turn must answer
    nudged = False  # the one completeness round (R1) has been used
    for turn in range(max_turns):
        if tokens >= max_tokens:
            errors.append(f"token budget ({max_tokens:,}) spent before the final answer")
            return "", trace, tokens, model, errors
        if not stop and (tokens + int(last * 1.3) > max_tokens - reserve or turn + 1 >= max_turns):
            stop = True  # no room for another tool round: this turn answers
            if turn:
                messages[-1]["content"].append({"type": "text", "text": STOP_NOTE})
        try:
            response, usage, model = provider.create(
                _with_cache(messages),
                purpose="agent",
                system=system,
                tier=tier,
                effort=effort,
                tools=TOOL_SCHEMAS,
                tool_choice={"type": "none"} if stop else None,
            )
        except LLMError as e:
            raise LLMError(
                str(e), tokens=tokens + (e.tokens or 0), usage_known=e.usage_known,
                retryable=e.retryable,
            ) from e
        tokens += usage.total_tokens
        last = usage.total_tokens
        _check_cancel(provider)  # cancelled while the request was in flight: do nothing more
        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
            note = None if (stop or nudged) else _completeness_note(text, trace, box.conn, question)
            room = box.calls < max_calls and turn + 2 < max_turns
            if note and room and tokens + int(last * 1.3) <= max_tokens - reserve:
                nudged = True  # R1: one more round to read what the answer relies on
                if progress:
                    progress({"stage": "completing", "reason": note})
                messages.append({"role": "assistant", "content": response.content})
                left = max_calls - box.calls
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"{note} You have {left} tool call(s) left: read it now, "
                                    "then give the "
                                    "final JSON answer again."
                                ),
                            }
                        ],
                    }
                )
                continue
            return text, trace, tokens, model, errors
        if stop:  # tools were forbidden on this turn
            errors.append("agent asked for tools on its final turn")
            return "", trace, tokens, model, errors

        messages.append({"role": "assistant", "content": response.content})
        results: list[dict] = []
        for block in (b for b in response.content if getattr(b, "type", "") == "tool_use"):
            _check_cancel(provider)
            out, values = _run_tool(box, block.name, dict(block.input or {}))
            err = out.startswith(("Tool error", "Unknown tool"))
            chunks = getattr(box, "last_chunks", None)
            trace.append(trace_entry(box.calls, block.name, values, out, chunks))
            if progress:
                progress({"stage": "tool"} | trace[-1])
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": out, "is_error": err}
            )
        stop = box.calls >= max_calls
        if stop:
            results.append({"type": "text", "text": STOP_NOTE})
        messages.append({"role": "user", "content": results})

    errors.append(f"agent did not finish within {max_turns} turns")
    return "", trace, tokens, model, errors


__all__ = ["TOOL_SCHEMAS", "run_api_agent"]
