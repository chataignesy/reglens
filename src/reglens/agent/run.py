"""Agentic answering: Claude uses the RegLens MCP tools in a bounded loop, then answers in JSON
citing passage keys (e.g. "CRR Art. 178(1)"). Keys are resolved back to chunks so the same
citation check, as-of line and rendering as the single-pass pipeline apply.

Bounds: the MCP server stops serving data after `max_calls` tool calls, and `claude -p
--max-budget-usd` caps the cost of one question. Runs on the subscription (`claude -p`).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

from reglens.agent.tools import key_of, resolve_key
from reglens.answer.pipeline import Answer, Claim, _parse_json, as_of_statement
from reglens.answer.prompts import SCOPE
from reglens.config import Config
from reglens.llm.provider import ClaudeCLIProvider
from reglens.retrieve.search import Hit, search

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
- Before answering, check the legal basis:
  (a) if the passages you rely on cite CRR or RTS provisions (e.g. "Article 181(1)(b)", "the RTS
      on economic downturn"), read the main one with `get_article`, or `follow_reference` first;
  (b) if the question asks what is required and all your passages are supervisory (EBA
      guidelines, Q&A, ECB guide), `search` for the underlying CRR or RTS text.
  Answer from supervisory passages alone only if these calls find nothing; then say so.
- You have a small tool budget (about {{max_calls}} calls). Make independent calls together in
  one turn (e.g. several `get_article` calls at once): every extra turn re-reads all passages.
  Once the checks above are done, stop as soon as you can answer.

Rules:
1. Every claim must be supported by passages you received and cite their keys exactly as shown in
   brackets, e.g. [CRR Art. 178(1)] or [EBA GL definition of default (GL/2016/07) para. 71].
   Never use outside knowledge and never cite a key you did not receive.
2. Abstain only when the question is outside the scope above or no passage answers any part of
   it. If passages answer part of the question, answer that part and say in the text what is
   missing. Missing information goes in the answer text, never in "claims".
3. Label each claim "law" (CRR or RTS), "supervisory" (EBA guideline, Q&A, ECB guide or
   instructions) or "interpretation" (your inference; say so in the text).
4. Quote numbers exactly as the passages give them. Be concise; no legal-advice disclaimers.

Final reply: ONE JSON object and nothing else:
{{"abstain": false, "abstain_reason": "",
  "answer": "short answer in Markdown citing keys in brackets",
  "claims": [{{"text": "one atomic claim", "citations": ["CRR Art. 178(1)"], "kind": "law"}}]}}
"""


def _mcp_config(max_calls: int, trace_path: str) -> str:
    cfg = {
        "mcpServers": {
            "reglens": {
                "command": sys.executable,
                "args": ["-m", "reglens.agent.mcp_server"],
                "env": {
                    "REGLENS_MAX_TOOL_CALLS": str(max_calls),
                    "REGLENS_TRACE_FILE": trace_path,
                    "PYTHONIOENCODING": "utf-8",
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


def _resolve(
    conn, keys: list[str], received: list[str] = ()
) -> tuple[list[Hit], dict[str, list[str]]]:
    """Cited keys -> context hits (in citation order, one per chunk) and key -> ['C#', ...].
    A key may list several passages ("A; B"); shortened keys are matched to `received` keys."""
    context: list[Hit] = []
    by_chunk: dict[str, str] = {}
    mapping: dict[str, list[str]] = {}
    for key in keys:
        if key in mapping:
            continue
        cids = []
        for part in (p.strip() for p in key.split(";") if p.strip()):
            rows = resolve_key(conn, part)
            if not rows and (alt := _match_received(part, received)):
                rows = resolve_key(conn, alt)
            if not rows:
                cids.append("C?")  # unknown key -> flagged by the citation check
                continue
            if rows[0].id not in by_chunk:
                merged = rows[0].hit(1.0)
                merged.text = "\n".join(r.text for r in rows)  # windowed chunks: all parts
                context.append(merged)
                by_chunk[rows[0].id] = f"C{len(context)}"
            cids.append(by_chunk[rows[0].id])
        mapping[key] = cids
    return context, mapping


def _read_trace(path: str) -> list[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [json.loads(line) for line in lines if line.strip()]


def _run_once(provider, question, max_calls, opts, extra) -> tuple:
    """One `claude -p` agent run with a fresh MCP server; returns (completion, tool trace)."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        trace_file = f.name
    mcp_file = _mcp_config(max_calls, trace_file)
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
        Path(mcp_file).unlink(missing_ok=True)
        trace = _read_trace(trace_file)
        Path(trace_file).unlink(missing_ok=True)
    return completion, trace


def answer_agentic(
    conn,
    provider: ClaudeCLIProvider,
    config: Config,
    question: str,
    *,
    today: date | None = None,
) -> Answer:
    opts = (config.answer or {}) | (config.agent or {})
    today = today or date.today()
    max_calls = int(opts.get("max_calls", 10))

    # Same retrieval gate as the single-pass pipeline: no LLM call for clearly unrelated questions.
    top = search(conn, question, mode="rerank", k=1)
    best = top[0].score if top else 0.0
    if best < float(opts.get("abstain_below", 0.05)):
        return Answer(
            question,
            True,
            f"no relevant passage found (best score {best:.3f})",
            "",
            [],
            top,
            as_of_statement(top, today),
        )

    allowed = ",".join(f"mcp__reglens__{t}" for t in TOOLS)
    extra = ["--allowedTools", allowed, "--max-budget-usd", str(opts.get("max_budget_usd", 0.75))]
    tokens = 0
    for _attempt in range(2):  # a run without any tool call means the tools were not available
        completion, trace = _run_once(provider, question, max_calls, opts, extra)
        tokens += completion.usage.total_tokens
        if trace:
            break

    ans = Answer(
        question,
        False,
        "",
        "",
        [],
        [],
        "",
        model=completion.model,
        usage_tokens=tokens,
        trace=trace,
    )
    if not trace:
        ans.errors.append("agent made no tool calls (RegLens MCP tools unavailable?)")
    try:
        data = _parse_json(completion.text)
    except (ValueError, json.JSONDecodeError) as e:
        ans.errors.append(f"unparseable model output: {e}")
        ans.answer = completion.text
        return ans

    claims_raw = data.get("claims") or []
    text = str(data.get("answer") or "")
    keys = [str(k) for c in claims_raw for k in c.get("citations", [])]
    keys += re.findall(r"\[([^\[\]]+?)\]", text)
    received = [k for t in trace for k in t.get("keys", [])]
    context, mapping = _resolve(conn, keys, received)
    text = re.sub(
        r"\[([^\[\]]+?)\]",
        lambda m: "".join(f"[{c}]" for c in mapping.get(m.group(1), ["C?"])),
        text,
    )
    unresolved = [k for k, cids in mapping.items() if "C?" in cids]
    if unresolved:
        ans.trace.append({"tool": "answer", "unresolved_keys": unresolved})

    ans.abstained = bool(data.get("abstain"))
    ans.abstain_reason = str(data.get("abstain_reason") or "")
    ans.answer = text
    ans.context = context
    ans.as_of = as_of_statement(context, today)
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
