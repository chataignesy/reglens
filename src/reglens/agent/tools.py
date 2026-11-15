"""Read-only retrieval tools for the agent (and the MCP server), over the Postgres index.

Every passage is returned with a citation key in brackets, e.g. [CRR Art. 178(1)] or
[ECB guide to internal models, Credit risk, para. 309]; the agent cites those keys verbatim and
`resolve_key` maps them back to chunks. A `Toolbox` enforces a call budget and caps result size.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from reglens.answer.pipeline import LEVEL_LABEL
from reglens.context import METADATA
from reglens.ingest.cite import _sources, citation_key
from reglens.retrieve.search import Filters, Hit, search
from reglens.sources import Source

CRR = "crr3-consolidated"
QA = "eba-qa-credit-risk"
_COLS = (
    ("id, source_id, ref, title, text, legal_level, version, kind, article, paragraph, point, cite")
    + ", "
    + ", ".join(METADATA)
    + ", hierarchy"
)


@dataclass
class Row:
    id: str
    source_id: str
    ref: str
    title: str | None
    text: str
    legal_level: str
    version: str | None
    kind: str
    article: str | None
    paragraph: str | None
    point: str | None
    cite: str = ""  # stored citation key (unique per logical unit)
    published_on: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None
    application_from: str | None = None
    application_until: str | None = None
    temporal_verified: bool = False
    applicability: dict[str, list[str]] = field(default_factory=dict)
    hierarchy: list[str] = field(default_factory=list)

    def hit(self, score: float = 0.0) -> Hit:
        return Hit(
            self.id,
            self.source_id,
            self.ref,
            self.title,
            self.text,
            self.legal_level,
            self.version,
            score,
            hierarchy=self.hierarchy,
            **{
                k: str(getattr(self, k))
                if k in METADATA[:5] and getattr(self, k) is not None
                else getattr(self, k)
                for k in METADATA
            },
        )


def definition_rows(conn, term: str) -> list[Row]:
    """Exact defined terms, with a bounded plural fallback; no fuzzy legal classification."""
    value = term.strip()
    if not re.fullmatch(r"[\w -]{2,80}", value):
        return []
    candidates = [value]
    if value.endswith("ies"):
        candidates.append(value[:-3] + "y")
    elif value.endswith("s") and not value.endswith("ss"):
        candidates.append(value[:-1])
    where = "source_id = %s AND article IN ('4', '142') AND point IS NOT NULL AND body ILIKE %s"
    for candidate in candidates:
        rows = _rows(conn, where, [CRR, f"‘{candidate}’%"], limit=3)
        if not rows:
            rows = _rows(conn, where, [CRR, f"%‘{candidate}’%means%"], limit=3)
        if rows:
            return rows
    return []


def source_by_name(name: str, conn=None) -> Source | None:
    """Accept a source id ('crr3-consolidated') or its short label ('CRR'), case-insensitive."""
    n = name.strip().lower()
    from reglens.sources import load_sources

    for s in load_sources(conn=conn):
        if n in (s.id.lower(), s.label().lower()) or s.label().lower().startswith(n + " "):
            return s
    return None


def key_of(r: Row | Hit) -> str:
    if getattr(r, "cite", ""):
        return r.cite
    kind = getattr(r, "kind", None) or ("paragraph" if r.ref.startswith("para.") else "article")
    return citation_key(r.source_id, r.ref, r.title, kind)


def _rows(conn, where: str, params: list, limit: int = 50, offset: int = 0) -> list[Row]:
    sql = f"SELECT {_COLS} FROM chunks WHERE {where} ORDER BY id LIMIT %s OFFSET %s"
    return [Row(*r) for r in conn.execute(sql, [*params, limit, offset]).fetchall()]


def _count(conn, where: str, params: list) -> int:
    return conn.execute(f"SELECT count(*) FROM chunks WHERE {where}", params).fetchone()[0]


def _one_unit(rows: list[Row]) -> list[Row]:
    """Rows of a single logical unit, or [] when a loose key matches several (ambiguous)."""
    units = {(r.kind, r.article, r.paragraph or None, r.point or None, r.title) for r in rows}
    return rows if len(units) <= 1 else []


def resolve_key(conn, key: str) -> list[Row]:
    """Chunks a citation key refers to (all window parts and continuations). Empty if unknown
    or ambiguous. Exact stored keys first; a loose older-style key must name one unit."""
    key = key.strip().strip("[]").strip()
    rows = _rows(conn, "cite = %s", [key])
    if rows:
        return rows
    for s in sorted(_sources().values(), key=lambda s: -len(s.label())):
        label = s.label()
        if not key.startswith(label):
            continue
        rest = key[len(label) :].lstrip(", ").strip()
        part = None
        if s.parts and rest.count(",") >= 1:
            part, rest = (x.strip() for x in rest.rsplit(",", 1))
        rows = _rows(conn, "source_id = %s AND ref = ANY(%s)", [s.id, [rest, f"Q&A {rest}"]])
        if part is not None:
            rows = [r for r in rows if (r.title or "") == part]
        if rows:
            return _one_unit(rows)
    return []


def _format(rows: list[Row], max_chars: int) -> str:
    out = []
    for r in rows:
        level = LEVEL_LABEL.get(r.legal_level, r.legal_level)
        key = key_of(r)
        body = r.text
        if len(body) > max_chars:  # search snippets: the full text is one get_passage call away
            body = body[:max_chars] + f" …[truncated; get_passage('{key}') for the full text]"
        meta = {k: str(getattr(r, k)) for k in METADATA if getattr(r, k)}
        out.append(
            f"[{key}] ({level})\nMetadata: {meta}; temporal verified: {r.temporal_verified}\n{body}"
        )
    return "\n\n".join(out) if out else "No passages found."


def trace_entry(call: int, tool: str, args: list, out: str, chunks: dict | None = None) -> dict:
    """One tool-call record. `keys`: passages whose text the tool returned, the only ones the
    agent may cite; `refs`: follow_reference targets, pointers without text; `chunks`: chunk id
    -> characters of its text actually delivered (second review S1: coverage per window)."""
    keys = re.findall(r"^\[(.+?)\] \(", out, re.M)  # passages: "[key] (level)"
    refs = re.findall(r"^- \w+: (.+)$", out, re.M)
    cut = re.findall(r"…\[truncated; get_passage\('(.+?)'\) for the full text\]", out)
    entry = {"call": call, "tool": tool, "args": args, "keys": keys, "chars": len(out)}
    entry |= {"chunks": dict(chunks)} if chunks is not None else {}
    return entry | ({"refs": refs} if refs else {}) | ({"truncated": cut} if cut else {})


def delivered_chars(trace: list[dict]) -> dict[str, int] | None:
    """Chunk id -> most characters of it any tool call delivered. None for an old trace
    without per-chunk records (then only key-level checks are possible)."""
    if not any("chunks" in t for t in trace):
        return None
    got: dict[str, int] = {}
    for t in trace:
        for cid, n in (t.get("chunks") or {}).items():
            got[cid] = max(got.get(cid, 0), int(n))
    return got


def coverage(rows: list[Row], got: dict[str, int]) -> str:
    """How much of one logical unit (all its windows) was delivered: none / partial / full."""
    seen = [r for r in rows if got.get(r.id, 0) > 0]
    if not seen:
        return "none"
    full = all(got.get(r.id, 0) >= len(r.text) for r in rows)
    return "full" if full else "partial"


def partial_reads(trace: list[dict], conn=None) -> set[str]:
    """Keys the agent never read in full (review R1). With `conn` and a trace that records
    chunks, a unit counts as read only when every one of its windows was delivered whole
    (second review S1); otherwise a key is partial if it was only ever seen truncated."""
    got = delivered_chars(trace) if conn is not None else None
    if got is not None:
        keys = {k for t in trace for k in t.get("keys", [])}
        return {k for k in keys if coverage(resolve_key(conn, k), got) == "partial"}
    full = {k for t in trace for k in t.get("keys", []) if k not in t.get("truncated", [])}
    return {k for t in trace for k in t.get("truncated", [])} - full


class Toolbox:
    """The agent's tools. Stateful only for the call budget.

    `search` and `get_qa` return snippets (`snippet_chars` per passage) so the agent keeps
    reading instead of treating long previews as complete; `get_article`, `get_definition` and
    `get_passage` return full passages (chunks are at most ~4,000 chars).
    """

    def __init__(
        self,
        conn,
        *,
        max_calls: int | None = 10,
        snippet_chars: int = 2000,
        passage_chars: int = 4000,
        result_chars: int = 14000,
        applies_to: str | None = None,
        filters: Filters | None = None,
    ):
        self.conn = conn
        self.applies_to = applies_to  # "SI" / "LSI": search only texts that apply (or apply to all)
        self.filters = filters or Filters(applies_to=applies_to)
        self.max_calls = max_calls
        self.snippet_chars = snippet_chars
        self.passage_chars = passage_chars
        self.result_chars = result_chars
        self.calls = 0
        self.seen: dict[str, Row] = {}  # citation key -> passage actually returned
        self.last_shown = 0
        self.last_chunks: dict[str, int] = {}  # chunk id -> chars delivered by the last call

    def _budget(self) -> str | None:
        """None while calls remain (or without a cap: `max_calls=None`), else the stop note."""
        self.calls += 1
        self.last_chunks = {}
        if self.max_calls is not None and self.calls > self.max_calls:
            return (
                f"Tool budget exhausted ({self.max_calls} calls). Answer now with the "
                "passages you already have, and say what is missing."
            )
        return None

    def _eligible(self, rows: list[Row]) -> list[Row]:
        if self.conn is None or not rows:
            return rows
        from dataclasses import replace

        where, params = replace(self.filters, default_scope=False).sql(self.conn)
        ids = {
            r[0]
            for r in self.conn.execute(
                "SELECT id FROM chunks WHERE id=ANY(%s)" + where, [[r.id for r in rows], *params]
            ).fetchall()
        }
        return [r for r in rows if r.id in ids]

    def _out(self, rows: list[Row], note: str = "", *, snippets: bool = False) -> str:
        """Whole passages up to `result_chars`; a passage is never cut by the size limit, and
        what is left out is said. Only passages actually returned count as delivered (`seen`)."""
        rows = self._eligible(rows)
        cap = self.snippet_chars if snippets else self.passage_chars
        head = note + "\n\n" if note else ""
        blocks: list[str] = []
        used = len(head)
        for r in rows:
            block = _format([r], cap)
            if blocks and used + len(block) + 2 > self.result_chars:
                break
            blocks.append(block)
            used += len(block) + 2
            self.seen[key_of(r)] = r
            n = min(len(r.text), cap)
            self.last_chunks[r.id] = max(self.last_chunks.get(r.id, 0), n)
        self.last_shown = len(blocks)
        text = head + ("\n\n".join(blocks) if blocks else "No passages found.")
        if len(blocks) < len(rows):
            text += f"\n\n[Size limit: {len(rows) - len(blocks)} more passage(s) not shown.]"
        return text

    def search(self, query: str, k: int = 6, source: str | None = None) -> str:
        """Hybrid search (BM25 + embeddings + reranker) over the corpus."""
        if msg := self._budget():
            return msg
        from dataclasses import replace

        filters = self.filters
        if source:
            s = source_by_name(source, self.conn)
            if not s:
                return f"Unknown source '{source}'."
            filters = replace(self.filters, source_ids=[s.id])
        hits = search(self.conn, query, mode="rerank", k=min(int(k), 8), filters=filters)
        ids = [h.id for h in hits]
        rows = {r.id: r for r in _rows(self.conn, "id = ANY(%s)", [ids])}
        return self._out([rows[i] for i in ids if i in rows], snippets=True)

    def get_passage(self, citation_key_: str) -> str:
        """Full text of one passage (all its parts), by the citation key shown in brackets."""
        if msg := self._budget():
            return msg
        rows = resolve_key(self.conn, citation_key_)
        if not rows:
            return (
                f"Unknown citation key '{citation_key_}'. Use a key exactly as shown in brackets."
            )
        from reglens.answer.amendments import parent_units

        seen = {r.id for r in rows}
        for _, group in parent_units(self.conn, [r.hit() for r in rows], self.filters):
            rows += [r for r in group if r.id not in seen]
            seen.update(r.id for r in group)
        return self._out(rows)

    def get_article(
        self, source: str, article: str, paragraph: str | None = None, offset: int = 0
    ) -> str:
        """Full text of an article (or one paragraph) of a regulation, by number. Long
        articles come in pages: the reply says which passages it holds and how to continue."""
        if msg := self._budget():
            return msg
        s = source_by_name(source, self.conn)
        if not s:
            return f"Unknown source '{source}'."
        art = str(article).strip().removeprefix("Art.").removeprefix("Article").strip()
        where, params = "source_id = %s AND article = %s AND kind = 'article'", [s.id, art]
        from dataclasses import replace

        extra, values = replace(self.filters, default_scope=False).sql(self.conn)
        where += extra
        params.extend(values)
        para = str(paragraph).strip("() ") if paragraph else None
        if para:
            where += " AND paragraph = %s"
            params.append(para)
        what = f"{s.label()} Art. {art}" + (f"({para})" if para else "")
        offset = max(int(offset or 0), 0)
        total = _count(self.conn, where, params)
        rows = _rows(self.conn, where, params, limit=40, offset=offset)
        if not rows:
            where_ = f" at offset {offset} of {total}." if total else "."
            return f"No passages for {what}{where_}"
        from reglens.answer.research import incoming_exceptions

        candidates = incoming_exceptions(self.conn, s.id, [art], self.filters)
        keys = list(dict.fromkeys(key_of(r) for r in candidates))[:4]
        note = ""
        if keys:
            note = (
                "Possible exceptions referring back to this rule (pointers only; "
                "read the passage and check its conditions before concluding):\n"
                + "\n".join(f"- candidate: {key}" for key in keys)
            )[:1000]
        text = self._out(rows, note)
        end = offset + self.last_shown
        if offset or end < total:
            more = (
                f" Incomplete: call get_article('{source}', '{art}'"
                + (f", '{para}'" if para else "")
                + f", offset={end}) for the rest."
                if end < total
                else " This is the last page."
            )
            text = f"[{what}: passages {offset + 1}-{end} of {total}.{more}]\n\n" + text
        return text

    def follow_reference(self, citation_key_: str) -> str:
        """Articles, paragraphs and Art. 4 definitions that a passage refers to."""
        if msg := self._budget():
            return msg
        rows = resolve_key(self.conn, citation_key_)
        if not rows:
            return (
                f"Unknown citation key '{citation_key_}'. Use a key exactly as shown in brackets."
            )
        edges = self.conn.execute(
            "SELECT DISTINCT kind, target_source, target_article, target_paragraph, target_point "
            "FROM edges WHERE src = ANY(%s) ORDER BY kind, target_article",
            ([r.id for r in rows],),
        ).fetchall()
        lines = []
        for kind, ts, ta, tp, tpt in edges[:40]:
            label = _sources()[ts].label() if ts in _sources() else ts
            ref = f"Art. {ta}" + (f"({tp})" if tp else "") + (tpt or "")
            lines.append(f"- {kind}: {label} {ref}")
        n_qa = (
            self.conn.execute(
                "SELECT count(*) FROM chunks WHERE source_id = %s AND article = %s",
                (QA, rows[0].article),
            ).fetchone()[0]
            if rows[0].source_id == CRR and rows[0].article
            else 0
        )
        hint = f"\n{n_qa} EBA Q&As concern this article (use get_qa)." if n_qa else ""
        body = "\n".join(lines) if lines else "No outgoing references."
        from reglens.answer.research import incoming_exceptions

        incoming = incoming_exceptions(
            self.conn, rows[0].source_id,
            list(dict.fromkeys(r.article for r in rows if r.article)), self.filters,
        )
        candidates = list(dict.fromkeys(key_of(r) for r in incoming))[:4]
        if candidates:
            body += "\nPossible exceptions referring back to this rule (check applicability):\n"
            body += "\n".join(f"- candidate: {key}" for key in candidates)
        return (
            f"References from [{key_of(rows[0])}]:\n{body}{hint}\n"
            "Use get_article / get_definition to read them."
        )[: self.result_chars]

    def get_definition(self, term: str) -> str:
        """A CRR definition (Art. 4(1), or Art. 142(1) for IRB terms such as 'large corporate')."""
        if msg := self._budget():
            return msg
        rows = definition_rows(self.conn, term)
        if not rows:
            return f"No CRR definition found for '{term}'."
        quals: list[Row] = []  # Art. 142(1): "For the purposes of … point (5a) …"
        for r in rows:
            if r.paragraph and r.point:
                quals += _rows(
                    self.conn,
                    "source_id = %s AND article = %s AND paragraph = %s AND point IS NULL "
                    "AND kind = 'article' AND body ILIKE %s",
                    [CRR, r.article, r.paragraph, f"%point {r.point}%"],
                    limit=3,
                )
        ids = {r.id for r in rows}
        # A qualifier may match only one window of its enclosing paragraph. Its citation
        # names the whole unit, so deliver the other windows too (within the usual cap).
        for q in quals:
            for full in resolve_key(self.conn, key_of(q)) or [q]:
                if full.id not in ids:
                    rows.append(full)
                    ids.add(full.id)
        return self._out(rows)

    def get_qa(self, article: str, query: str | None = None, k: int = 4) -> str:
        """Final EBA Q&As about a CRR article (most relevant first if a query is given)."""
        if msg := self._budget():
            return msg
        art = str(article).strip().removeprefix("Art.").removeprefix("Article").strip()
        art = re.match(r"\d+[a-z]?", art).group() if re.match(r"\d+[a-z]?", art) else art
        rows = _rows(self.conn, "source_id = %s AND article = %s", [QA, art], limit=60)
        if not rows:
            return f"No EBA Q&A found for CRR Art. {art}."
        if query and len(rows) > k:
            from reglens.index.embed import rerank
            from reglens.index.generations import metadata

            scores = rerank(
                query, [r.text for r in rows], identity=metadata(self.conn).get("models") or None
            )
            rows = [r for _, r in sorted(zip(scores, rows, strict=True), key=lambda x: -x[0])]
        note = f"{len(rows)} Q&As on CRR Art. {art}."
        return self._out(rows[: min(int(k), 6)], note=note, snippets=True)
