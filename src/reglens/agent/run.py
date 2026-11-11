"""Agentic answering: Claude uses the RegLens MCP tools in a bounded loop, then answers in JSON
citing passage keys (e.g. "CRR Art. 178(1)"). Keys are resolved back to chunks so the same
citation check, as-of line and rendering as the single-pass pipeline apply.

Two backends, picked by the provider:
- subscription (`claude -p`): Claude Code runs the loop over the RegLens MCP server; the server
  stops serving data after `max_calls` tool calls and `--max-budget-usd` caps the cost;
- Anthropic API (bring-your-own-key demo): `api_loop` runs the loop in RegLens code with hard
  limits on tool calls, turns and tokens per question.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
from datetime import date
from pathlib import Path

from reglens.agent.tools import coverage, delivered_chars, key_of, partial_reads, resolve_key
from reglens.answer.pipeline import Answer, Claim, Progress, as_of_statement
from reglens.answer.prompts import SCOPE
from reglens.answer.research import INSTRUCTION
from reglens.answer.schema import parse_reply
from reglens.config import Config
from reglens.llm.provider import AnthropicAPIProvider, ClaudeCLIProvider, LLMError
from reglens.retrieve.search import Filters, Hit, search

AGENT_CAP_ERROR = "the research agent reached its cost cap before answering"
TOOLS = ["search", "get_article", "get_passage", "follow_reference", "get_definition", "get_qa"]

AGENT_SYSTEM = f"""\
You are RegLens, an assistant for credit risk modellers and validators. You answer questions about
EU credit risk regulation using ONLY passages returned by the RegLens tools.

{SCOPE}

How to work:
- Start with `search`. Read the passages. If a key passage depends on other provisions (an
  exposure class, a defined term, a threshold in an RTS, a guideline paragraph), use
  `follow_reference` on its key and then `get_article` / `get_definition` to read them.
- Use `get_qa` when an EBA interpretation of a CRR article could matter.
- Search results are snippets. If a passage you rely on is marked truncated, read it in full
  with `get_passage` on its key (tables and long lists often continue there).
- Long articles come in pages: if a `get_article` reply says it is incomplete and the part you
  need is not shown, call it again with the `offset` it gives (or ask for one paragraph).
- `follow_reference` lists target provisions without their text: read a target before citing it.
- Check the legal basis needed for the requested conclusion. If that conclusion depends on a
  cross-reference, read the relevant provision. For a question about a legal requirement, check
  the underlying law where necessary. A guideline may supply operational detail absent from the
  CRR: once its legal role is clear, the absence of the same numerical detail in the CRR is not
  itself a gap. For a question about a specified document's content or limits, do not research
  unrelated law or broader supervisory scope just to complete a checklist.
- You have a small tool budget (about {{max_calls}} calls). Make independent calls together in
  one turn (e.g. several `get_article` calls at once): every extra turn re-reads all passages.
  Once the checks above are done, stop as soon as you can answer.

Rules:
1. Every claim must be supported by passages you received and cite their keys exactly as shown in
   brackets, e.g. [CRR Art. 178(1)] or [EBA GL definition of default (GL/2016/07) para. 71].
   Never use outside knowledge and never cite a key whose text you did not receive: such
   citations are rejected.
2. Abstain only when the question is outside the scope above or no passage answers any part of
   it. If passages answer part of the question, answer that part and say in the text what is
   missing. Missing information goes in the answer text, never in "claims".
3. Label each claim "law" (CRR or RTS), "supervisory" (EBA guideline, Q&A, ECB guide or
   instructions) or "interpretation" (your inference; say so in the text).
4. Quote numbers exactly as the passages give them. Be concise; no legal-advice disclaimers.

5. Set "missing_info": true only for unanswered requirements of the actual question; state
   them in "missing_requirements" and explain them in the answer. Set "research_needed" true
   only if another corpus lookup could resolve a required gap. Optional background and
   limitations the question explicitly asks you to identify are not unanswered requirements.

Final reply: ONE JSON object and nothing else:
{{"abstain": false, "abstain_reason": "", "missing_info": false,
  "research_needed": false, "missing_requirements": [],
  "answer": "short answer in Markdown citing keys in brackets",
  "claims": [{{"text": "one atomic claim", "citations": ["CRR Art. 178(1)"], "kind": "law"}}]}}
"""


AGENT_SYSTEM += INSTRUCTION


def _mcp_config(
    max_calls: int,
    trace_path: str,
    applies_to: str | None = None,
    generation: str | None = None,
    query_context: dict | None = None,
) -> str:
    cfg = {
        "mcpServers": {
            "reglens": {
                "command": sys.executable,
                "args": ["-m", "reglens.agent.mcp_server"],
                "env": {
                    **(
                        {"REGLENS_QUERY_CONTEXT": json.dumps(query_context)}
                        if query_context
                        else {}
                    ),
                    **({"REGLENS_CORPUS_GENERATION": generation} if generation else {}),
                    **(
                        {"REGLENS_INFERENCE_URL": os.environ["REGLENS_INFERENCE_URL"]}
                        if "REGLENS_INFERENCE_URL" in os.environ
                        else {}
                    ),
                    "REGLENS_MAX_TOOL_CALLS": str(max_calls),
                    "REGLENS_TRACE_FILE": trace_path,
                    "PYTHONIOENCODING": "utf-8",
                    **({"REGLENS_APPLIES_TO": applies_to} if applies_to else {}),
                    **(
                        {"REGLENS_DATABASE_URL": os.environ["REGLENS_DATABASE_URL"]}
                        if "REGLENS_DATABASE_URL" in os.environ
                        else {}
                    ),
                },
            }
        }
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as f:
        json.dump(cfg, f)
        return f.name


_REF_RE = re.compile(r"(?:Art\.|Article|paras?\.|recital|Section)\s*\S.*$")


def _match_received(key: str, received: list[str]) -> str | None:
    """A shortened key ("para. 26", "EBA GL downturn LGD para. 26") -> the one received key
    with the same reference whose name contains all the words given. None if not unique."""
    m = _REF_RE.search(key)
    if not m:
        return None
    ref, words = m.group(), set(re.findall(r"\w+", key[: m.start()].lower()))
    hits = {
        k
        for k in received
        if k.endswith(ref) and words <= set(re.findall(r"\w+", k[: -len(ref)].lower()))
    }
    return hits.pop() if len(hits) == 1 else None


_RANGE_RE = re.compile(r"^(.*?)\bparas?\.\s*(\d+)\s*(?:-|–|to|and)\s*(\d+)$")
_POINT_RE = re.compile(r"\([^()]*\)(?:\s*(?:-|–|and|to)\s*\([^()]*\))?$")  # "(b)" or "(b)-(c)"


def _expand_range(key: str) -> list[str]:
    """'EBA GL … paras. 71-73' -> one key per paragraph (at most 10)."""
    m = _RANGE_RE.match(key)
    if not m or not 0 < int(m.group(3)) - int(m.group(2)) < 10:
        return [key]
    return [f"{m.group(1)}para. {n}" for n in range(int(m.group(2)), int(m.group(3)) + 1)]


def _lookup(conn, key: str, received: list[str]) -> list:
    """Exact key, then a shortened key matched to a received one, then the enclosing passage
    ('CRR Art. 178(1)(b)' -> 'CRR Art. 178(1)'), since passages are stored per paragraph."""
    while True:
        rows = resolve_key(conn, key)
        if not rows and (alt := _match_received(key, received)):
            rows = resolve_key(conn, alt)
        if rows or not _POINT_RE.search(key):
            return rows
        key = _POINT_RE.sub("", key).rstrip()


def _resolve(
    conn,
    keys: list[str],
    received: list[str] = (),
    *,
    delivered: set[str] | None = None,
    undelivered: list[str] | None = None,
    canonical: dict[str, str] | None = None,
    got: dict[str, int] | None = None,
    partial: set[str] | None = None,
) -> tuple[list[Hit], dict[str, list[str]]]:
    """Cited keys -> context hits (in citation order, one per chunk) and key -> ['C#', ...].
    A key may list several passages ("A; B"); shortened keys are matched to `received` keys.
    With `delivered` (keys of passages the tools returned), a key that names a real passage the
    agent never received is not accepted: it becomes 'C?' and is listed in `undelivered`.
    With `got` (chunk id -> delivered chars, second review S1) the context holds exactly the
    delivered text of each window, never unseen windows; units not read whole go to `partial`."""
    context: list[Hit] = []
    by_chunk: dict[str, str] = {}
    mapping: dict[str, list[str]] = {}
    for key in keys:
        if key in mapping:
            continue
        cids = []
        parts = [p.strip() for p in key.split(";") if p.strip()]
        for part in (q for p in parts for q in _expand_range(p)):
            rows = _lookup(conn, part, received)
            unit = rows
            if rows and got is not None:  # window-level delivery
                if coverage(rows, got) == "partial" and partial is not None:
                    partial.add(key_of(rows[0]))
                rows = [r for r in rows if got.get(r.id, 0) > 0]
                if not rows and undelivered is not None:
                    undelivered.append(part)
            elif rows and delivered is not None and key_of(rows[0]) not in delivered:
                if undelivered is not None:
                    undelivered.append(part)
                rows = []
            if not rows:
                cids.append("C?")  # unknown or unread key -> flagged by the citation check
                continue
            uid = unit[0].id
            if uid not in by_chunk:
                merged = rows[0].hit(1.0)
                if got is None:  # old trace without chunk records: all window parts
                    merged.text = "\n".join(r.text for r in rows)
                else:  # exactly the text that was delivered, nothing unseen
                    merged.text = "\n".join(r.text[: got[r.id]] for r in rows)
                context.append(merged)
                by_chunk[uid] = f"C{len(context)}"
                if canonical is not None:  # C# -> the passage's own citation key
                    canonical[by_chunk[uid]] = key_of(unit[0])
            if by_chunk[uid] not in cids:
                cids.append(by_chunk[uid])
        mapping[key] = cids
    return context, mapping


def _read_trace(path: str) -> list[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [json.loads(line) for line in lines if line.strip()]


def _watch_trace(path: str, emit, stop: threading.Event) -> None:
    """Report each tool call as the MCP server appends it to the trace file."""
    from reglens.cancel import Cancelled

    seen = 0
    while True:
        entries = _read_trace(path)
        try:
            for entry in entries[seen:]:
                emit({"stage": "tool"} | entry)
        except Cancelled:
            return  # the provider kills the subprocess; nothing left to report
        seen = max(seen, len(entries))
        if stop.wait(0.5):
            return


def _run_once(provider, question, max_calls, opts, extra, progress=None, applies_to=None) -> tuple:
    """One `claude -p` agent run with a fresh MCP server; returns (completion, tool trace)."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        trace_file = f.name
    mcp_file = _mcp_config(
        max_calls, trace_file, applies_to, opts.get("corpus_generation"), opts.get("query_context")
    )
    stop = threading.Event()
    watcher = None
    if progress:
        watcher = threading.Thread(target=_watch_trace, args=(trace_file, progress, stop))
        watcher.start()
    try:
        completion = provider.complete(
            question,
            purpose="agent",
            system=AGENT_SYSTEM.replace("{max_calls}", str(max_calls)),
            tier=opts.get("tier", "dev"),
            effort=opts.get("effort"),
            extra_args=["--mcp-config", mcp_file, *extra],
        )
    finally:
        stop.set()
        if watcher:
            watcher.join()
        Path(mcp_file).unlink(missing_ok=True)
        trace = _read_trace(trace_file)
        Path(trace_file).unlink(missing_ok=True)
    return completion, trace


def answer_agentic(
    conn,
    provider: ClaudeCLIProvider | AnthropicAPIProvider,
    config: Config,
    question: str,
    *,
    today: date | None = None,
    progress: Progress | None = None,
    filters: Filters | None = None,
) -> Answer:
    """`progress`, if given, receives stage events, including one per tool call. `filters`:
    only `applies_to` ("SI" / "LSI") is used: the search tool then only finds texts that apply
    to that institution type (or to all), and the agent is told which type was asked about."""
    opts = (config.answer or {}) | (config.agent or {})
    from reglens.index.generations import current

    opts["corpus_generation"] = current(conn)
    from dataclasses import asdict

    from reglens.context import coverage, instruction

    opts["query_context"] = asdict(filters) if filters else {}
    today = today or date.today()
    max_calls = int(opts.get("max_calls", 10))
    applies = filters.applies_to if filters else None
    asked = question
    question += instruction(filters)
    if applies:
        question = (
            f"{question}\n\n(Institution type: {applies}. Search results are limited to "
            f"texts that apply to {applies} institutions or to all; say which applies.)"
        )

    # Same retrieval gate as the single-pass pipeline: no LLM call for clearly unrelated questions.
    top = search(conn, asked, mode="rerank", k=1, filters=filters)
    best = top[0].score if top else 0.0
    if best < float(opts.get("abstain_below", 0.05)):
        return Answer(
            asked,
            True,
            f"no relevant passage found (best score {best:.3f})",
            "",
            [],
            top,
            as_of_statement(top, today),
            coverage=coverage(top, filters),
            corpus_generation=current(conn),
        )

    system = AGENT_SYSTEM.replace("{max_calls}", str(max_calls))
    if progress:
        progress({"stage": "agent", "max_calls": max_calls})
    if isinstance(provider, AnthropicAPIProvider):  # bring-your-own-key: loop runs in RegLens
        from reglens.agent.api_loop import run_api_agent

        text, trace, tokens, model, errors = run_api_agent(
            conn,
            provider,
            question,
            system=system,
            tier=opts.get("tier", "dev"),
            effort=opts.get("effort"),
            max_calls=max_calls,
            max_turns=int(opts.get("max_turns", max_calls + 3)),
            max_tokens=int(opts.get("max_tokens_per_question", 200_000)),
            progress=progress,
            applies_to=applies,
            filters=filters,
        )
    else:
        allowed = ",".join(f"mcp__reglens__{t}" for t in TOOLS)
        budget = str(opts.get("max_budget_usd", 0.75))
        extra = ["--allowedTools", allowed, "--max-budget-usd", budget]
        tokens, errors = 0, []
        try:
            for _attempt in range(2):  # a run without any tool call: the tools were unavailable
                completion, trace = _run_once(
                    provider, question, max_calls, opts, extra, progress, applies
                )
                tokens += completion.usage.total_tokens
                if trace:
                    break
            text, model = completion.text, completion.model
            if not trace:  # no tool call means an ungrounded answer: drop it, routing falls back
                text = ""
                errors.append("agent made no tool calls (RegLens MCP tools unavailable?)")
        except LLMError as e:
            if "max_budget" not in str(e):
                raise
            # claude -p stops without an answer at --max-budget-usd: report it, don't crash;
            # the tokens it spent are counted (and were logged to the ledger by the provider)
            text, model, trace = "", None, []
            tokens += e.tokens or 0
            errors.append(AGENT_CAP_ERROR + ("" if e.tokens is not None else " (usage unknown)"))

    ans = Answer(asked, False, "", "", [], [], "", model=model, usage_tokens=tokens, trace=trace)
    ans.corpus_generation = current(conn)
    from reglens.sources import load_sources

    ans.source_registry = {s.id: asdict(s) for s in load_sources(conn=conn)}
    ans.errors += errors
    if not text:
        return ans
    # No retry here: it would re-run the whole tool loop. An invalid reply is unverified and
    # has no answer text, so routing falls back to a single-pass answer.
    data, found = parse_reply(text)
    if found:
        ans.unverified, ans.raw_output = True, text
        ans.errors.append("invalid model output: " + "; ".join(found))
        return ans

    claims_raw = data.get("claims") or []
    text = str(data.get("answer") or "")
    keys = [str(k) for c in claims_raw for k in c.get("citations", [])]
    keys += re.findall(r"\[([^\[\]]+?)\]", text)
    received = [k for t in trace for k in t.get("keys", [])]  # passages with text, not refs
    unread: list[str] = []
    canonical: dict[str, str] = {}
    got = delivered_chars(trace)
    partial: set[str] = set()
    context, mapping = _resolve(
        conn,
        keys,
        received,
        delivered=set(received),
        undelivered=unread,
        canonical=canonical,
        got=got,
        partial=partial,
    )
    text = re.sub(
        r"\[([^\[\]]+?)\]",
        lambda m: "".join(f"[{c}]" for c in mapping.get(m.group(1), ["C?"])),
        text,
    )
    unresolved = [k for k, cids in mapping.items() if "C?" in cids]
    if unresolved:
        ans.trace.append({"tool": "answer", "unresolved_keys": unresolved})
    if unread:
        ans.errors.append(f"cited passages the agent never read: {', '.join(unread)}")
    # R1: passages cited after reading only a truncated snippet of them
    snippets_only = partial if got is not None else partial_reads(trace)
    ans.partial_cids = sorted(c for c, k in canonical.items() if k in snippets_only)
    if ans.partial_cids:
        names = ", ".join(canonical[c] for c in ans.partial_cids)
        ans.errors.append(f"relies on passages read only in part: {names}")
    ans.missing_info = bool(data.get("missing_info")) or bool(ans.partial_cids)
    ans.research_needed = data.get("research_needed")
    ans.missing_requirements = data.get("missing_requirements", [])
    if ans.partial_cids:
        ans.research_needed = True
        ans.missing_requirements = [*ans.missing_requirements, "Read cited passages in full"]

    ans.abstained = bool(data.get("abstain"))
    ans.abstain_reason = str(data.get("abstain_reason") or "")
    ans.answer = text
    for hit in context:
        hit.generation = ans.corpus_generation
    ans.context = context
    ans.coverage = coverage(context, filters)
    ans.as_of = as_of_statement(context, today)
    from reglens.answer.research import report

    ans.research = report(data, set(received), snippets_only)
    ans.claims = [
        Claim(
            str(c.get("text", "")),
            [cid for k in c.get("citations", []) for cid in mapping.get(str(k), ["C?"])],
            str(c.get("kind", "")),
        )
        for c in claims_raw
    ]
    return ans


__all__ = ["AGENT_SYSTEM", "answer_agentic", "key_of"]
