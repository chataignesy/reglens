"""RegLens MCP server (stdio): the corpus tools for Claude or any MCP client.

Run: uv run python -m reglens.agent.mcp_server
Env: REGLENS_MAX_TOOL_CALLS bounds the calls per server process. RegLens's own agent starts
one server per question and sets it (the per-question budget). Without it, as for a desktop
MCP client that keeps the server across many questions, there is no process-wide cap: question
budgets belong to the agent runtime, not to a long-lived server.
REGLENS_TRACE_FILE, if set, gets one JSON line per tool call (tool, args, passage keys returned).
All tools are read-only.
"""

from __future__ import annotations

import json
import os

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from reglens.agent.tools import Toolbox, trace_entry

INSTRUCTIONS = """\
Search EU credit risk regulation (CRR incl. CRR3, RTS, EBA guidelines and Q&A, ECB guide to internal
models). Each passage starts with a citation key in brackets, e.g. [CRR Art. 178(1)]; cite those
keys exactly. Typical flow: search (snippets) -> get_passage for the full text of a truncated
passage -> follow_reference on a key passage to find the articles and definitions it relies on ->
get_article / get_definition -> get_qa for EBA interpretations of a CRR article."""

server = MCPServer("reglens", instructions=INSTRUCTIONS)
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
_box: Toolbox | None = None


def box() -> Toolbox:
    global _box
    if _box is None:
        from reglens.index import db

        cap = os.environ.get("REGLENS_MAX_TOOL_CALLS")
        applies = os.environ.get("REGLENS_APPLIES_TO") or None  # "SI" / "LSI"
        from reglens.retrieve.search import Filters

        context = json.loads(os.environ.get("REGLENS_QUERY_CONTEXT", "{}"))
        filters = Filters(**context) if context else Filters(applies_to=applies)
        _box = Toolbox(db.connect(), max_calls=int(cap) if cap else None, applies_to=applies,
                       filters=filters)
    return _box


def _call(tool: str, *args) -> str:
    """Run a Toolbox method and append it to the trace file (if any)."""
    from reglens.agent.contracts import invoke, positional

    out, values = invoke(box(), tool, positional(tool, args))
    if path := os.environ.get("REGLENS_TRACE_FILE"):
        entry = trace_entry(box().calls, tool, values, out, getattr(box(), "last_chunks", None))
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return out


@server.tool(annotations=READ_ONLY)
def search(query: str, k: int = 6, source: str | None = None) -> str:
    """Hybrid search over the corpus. `source` optionally restricts to one source by short name
    (e.g. 'CRR', 'EBA Q&A', 'ECB guide to internal models')."""
    return _call("search", query, k, source)


@server.tool(annotations=READ_ONLY)
def get_article(
    source: str, article: str, paragraph: str | None = None, offset: int = 0
) -> str:
    """Full text of an article, or one paragraph, of a regulation (e.g. source 'CRR', article
    '151', paragraph '8'; or source 'RTS materiality threshold (Reg. 2018/171)', article '1').
    Long articles come in pages; the reply gives the `offset` for the next one."""
    return _call("get_article", source, article, paragraph, offset)


@server.tool(annotations=READ_ONLY)
def get_passage(citation_key: str) -> str:
    """Full text of one passage by its citation key (e.g. 'ECB guide to internal models,
    Document releases, Document releases'); use it when a search snippet is truncated."""
    return _call("get_passage", citation_key)


@server.tool(annotations=READ_ONLY)
def follow_reference(citation_key: str) -> str:
    """List the articles, paragraphs and definitions a passage refers to, by its citation key
    (e.g. 'CRR Art. 151(8)'), plus how many EBA Q&As exist on that article."""
    return _call("follow_reference", citation_key)


@server.tool(annotations=READ_ONLY)
def get_definition(term: str) -> str:
    """A CRR definition (Art. 4(1) or Art. 142(1)), e.g. 'large corporate'."""
    return _call("get_definition", term)


@server.tool(annotations=READ_ONLY)
def get_qa(article: str, query: str | None = None, k: int = 4) -> str:
    """Final EBA Single Rulebook Q&As on a CRR article, most relevant to `query` first."""
    return _call("get_qa", article, query, k)


if __name__ == "__main__":
    server.run("stdio")
