"""RegLens MCP server (stdio): the corpus tools for Claude or any MCP client.

Run: uv run python -m reglens.agent.mcp_server
Env: REGLENS_MAX_TOOL_CALLS (default 10) bounds the calls per server process (one agent run);
REGLENS_TRACE_FILE, if set, gets one JSON line per tool call (tool, args, passage keys returned).
All tools are read-only.
"""

from __future__ import annotations

import json
import os
import re

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from reglens.agent.tools import Toolbox

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

        _box = Toolbox(db.connect(), max_calls=int(os.environ.get("REGLENS_MAX_TOOL_CALLS", "10")))
    return _box


def _call(tool: str, *args) -> str:
    """Run a Toolbox method and append it to the trace file (if any)."""
    out = getattr(box(), tool)(*args)
    if path := os.environ.get("REGLENS_TRACE_FILE"):
        keys = re.findall(r"^\[(.+?)\] \(", out, re.M)  # passages: "[key] (level)"
        keys += re.findall(r"^- \w+: (.+)$", out, re.M)  # follow_reference targets
        entry = {"call": box().calls, "tool": tool, "args": list(args), "keys": keys}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry | {"chars": len(out)}, ensure_ascii=False) + "\n")
    return out


@server.tool(annotations=READ_ONLY)
def search(query: str, k: int = 6, source: str | None = None) -> str:
    """Hybrid search over the corpus. `source` optionally restricts to one source by short name
    (e.g. 'CRR', 'EBA Q&A', 'ECB guide to internal models')."""
    return _call("search", query, k, source)


@server.tool(annotations=READ_ONLY)
def get_article(source: str, article: str, paragraph: str | None = None) -> str:
    """Full text of an article, or one paragraph, of a regulation (e.g. source 'CRR', article
    '151', paragraph '8'; or source 'RTS materiality threshold (Reg. 2018/171)', article '1')."""
    return _call("get_article", source, article, paragraph)


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
