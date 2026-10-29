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

TOOLS = ["search", "get_article", "follow_reference", "get_definition", "get_qa"]

AGENT_SYSTEM = f"""\
You are RegLens, an assistant for credit risk modellers and validators. You answer questions about
EU credit risk regulation using ONLY passages returned by the RegLens tools.

{SCOPE}

How to work:
- Start with `search`. Read the passages. If a key passage depends on other provisions (an
  exposure class, a defined term, a threshold in an RTS, a guideline paragraph), use
  `follow_reference` on its key and then `get_article` / `get_definition` to read them.
- Use `get_qa` when an EBA interpretation of a CRR article could matter.
- You have a small tool budget (about {{max_calls}} calls). Stop as soon as you can answer.

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


def _mcp_config(max_calls: int) -> str:
    cfg = {
        "mcpServers": {
            "reglens": {
                "command": sys.executable,
                "args": ["-m", "reglens.agent.mcp_server"],
                "env": {
                    "REGLENS_MAX_TOOL_CALLS": str(max_calls),
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


def _resolve(conn, keys: list[str]) -> tuple[list[Hit], dict[str, str]]:
    """Unique cited keys -> context hits (in citation order) and key -> 'C#'."""
    context: list[Hit] = []
    mapping: dict[str, str] = {}
    for key in keys:
        if key in mapping:
            continue
        rows = resolve_key(conn, key)
        if not rows:
            mapping[key] = "C?"  # unknown key -> flagged by the citation check
            continue
        merged = rows[0].hit(1.0)
        merged.text = "\n".join(r.text for r in rows)  # windowed chunks: verify against all parts
        context.append(merged)
        mapping[key] = f"C{len(context)}"
    return context, mapping


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
    max_calls = int(opts.get("max_calls", 8))

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

    mcp_file = _mcp_config(max_calls)
    allowed = ",".join(f"mcp__reglens__{t}" for t in TOOLS)
    try:
        completion = provider.complete(
            question,
            purpose="agent",
            system=AGENT_SYSTEM.replace("{max_calls}", str(max_calls)),
            tier=opts.get("tier", "dev"),
            effort=opts.get("effort"),
            extra_args=[
                "--mcp-config",
                mcp_file,
                "--allowedTools",
                allowed,
                "--max-budget-usd",
                str(opts.get("max_budget_usd", 0.5)),
            ],
        )
    finally:
        Path(mcp_file).unlink(missing_ok=True)

    ans = Answer(
        question,
        False,
        "",
        "",
        [],
        [],
        "",
        model=completion.model,
        usage_tokens=completion.usage.total_tokens,
    )
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
    context, mapping = _resolve(conn, keys)
    for key, cid in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(f"[{key}]", f"[{cid}]")

    ans.abstained = bool(data.get("abstain"))
    ans.abstain_reason = str(data.get("abstain_reason") or "")
    ans.answer = text
    ans.context = context
    ans.as_of = as_of_statement(context, today)
    ans.claims = [
        Claim(
            str(c.get("text", "")),
            [mapping.get(str(k), "C?") for k in c.get("citations", [])],
            str(c.get("kind", "")),
        )
        for c in claims_raw
    ]
    return ans


__all__ = ["AGENT_SYSTEM", "answer_agentic", "key_of"]
