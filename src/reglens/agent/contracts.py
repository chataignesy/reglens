"""Shared read-only tool contract for SDK and MCP transports."""

from __future__ import annotations

from reglens.agent.tools import Toolbox
from reglens.cancel import Cancelled

_STR = {"type": "string"}

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "search",
        "description": (
            "Hybrid search (keywords + embeddings + reranker) over EU credit risk regulation. "
            "Returns passage snippets, each starting with its citation key in brackets. `source` "
            "optionally restricts to one source by short name (e.g. 'CRR', 'EBA Q&A', 'ECB guide "
            "to internal models')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": _STR,
                "k": {"type": "integer", "description": "passages to return (max 8)"},
                "source": _STR,
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_article",
        "description": (
            "Full text of an article, or one paragraph, of a regulation (e.g. source 'CRR', "
            "article '151', paragraph '8'; or source 'RTS materiality threshold (Reg. 2018/171)', "
            "article '1'). Long articles come in pages; the reply gives the offset for the next."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source": _STR,
                "article": _STR,
                "paragraph": _STR,
                "offset": {"type": "integer"},
            },
            "required": ["source", "article"],
        },
    },
    {
        "name": "get_passage",
        "description": (
            "Full text of one passage by its citation key, exactly as shown in brackets. Use it "
            "when a search snippet is marked truncated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"citation_key": _STR},
            "required": ["citation_key"],
        },
    },
    {
        "name": "follow_reference",
        "description": (
            "List the articles, paragraphs and definitions a passage refers to, by its citation "
            "key (e.g. 'CRR Art. 151(8)'), plus how many EBA Q&As exist on that article."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"citation_key": _STR},
            "required": ["citation_key"],
        },
    },
    {
        "name": "get_definition",
        "description": "A CRR definition (Art. 4(1) or Art. 142(1)), e.g. 'large corporate'.",
        "input_schema": {
            "type": "object",
            "properties": {"term": _STR},
            "required": ["term"],
        },
    },
    {
        "name": "get_qa",
        "description": (
            "Final EBA Single Rulebook Q&As on a CRR article, most relevant to `query` first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"article": _STR, "query": _STR, "k": {"type": "integer"}},
            "required": ["article"],
        },
    },
]

# The same bounds are advertised to the SDK and enforced for both transports below.
for tool in TOOL_SCHEMAS:
    schema = tool["input_schema"]
    schema["additionalProperties"] = False
    for name, prop in schema["properties"].items():
        if name == "k":
            prop.update(minimum=1, maximum=8)
        elif name == "offset":
            prop["minimum"] = 0

# Toolbox method arguments in call order, with defaults for optional ones.
_ARGS: dict[str, list[tuple[str, object]]] = {
    "search": [("query", ""), ("k", 6), ("source", None)],
    "get_article": [("source", ""), ("article", ""), ("paragraph", None), ("offset", 0)],
    "get_passage": [("citation_key", "")],
    "follow_reference": [("citation_key", "")],
    "get_definition": [("term", "")],
    "get_qa": [("article", ""), ("query", None), ("k", 4)],
}


def invoke(box: Toolbox, name: str, args: dict) -> tuple[str, list]:
    box.last_chunks = {}
    before = box.calls
    if name not in _ARGS:
        limit = box._budget()
        return limit or f"Unknown tool '{name}'.", []
    schema = next(s["input_schema"] for s in TOOL_SCHEMAS if s["name"] == name)
    values = [args.get(a, default) for a, default in _ARGS[name]]
    try:
        if set(args) - set(schema["properties"]):
            raise ValueError("Unknown argument")
        for key in schema["required"]:
            if key not in args:
                raise ValueError(f"Missing {key}")
        for (key, default), value in zip(_ARGS[name], values, strict=True):
            if value is None and default is None:
                continue
            expected = schema["properties"][key]["type"]
            if expected == "integer":
                if type(value) is not int or value < (0 if key == "offset" else 1):
                    raise ValueError(f"{key} must be a nonnegative offset or positive count")
                if key == "k" and value > 8:
                    raise ValueError("k must be between 1 and 8")
            elif not isinstance(value, str) or len(value) > 20000:
                raise ValueError(f"{key} must be a string of at most 20000 characters")
        return getattr(box, name)(*values), values
    except Cancelled:
        raise
    except Exception as exc:
        if box.calls == before:
            if limit := box._budget():
                return limit, values
        return f"Tool error: {exc}", values


def positional(name: str, args: tuple) -> dict:
    if name not in _ARGS or len(args) > len(_ARGS[name]):
        raise ValueError("Invalid tool call")
    return {key: value for (key, _), value in zip(_ARGS[name], args, strict=False)}
