"""Grounded answering: retrieve -> numbered context -> LLM (JSON) -> verify -> render.

The as-of statement and the legal level of each cited source are set by code from chunk
metadata, not by the model.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from reglens.answer.prompts import SYSTEM, user_prompt
from reglens.config import Config
from reglens.llm.provider import LLMProvider
from reglens.retrieve.search import Filters, Hit, search

LEVEL_LABEL = {
    "L1": "law",
    "L2": "law (RTS)",
    "L3": "EBA guideline",
    "qa": "EBA Q&A",
    "supervisory": "ECB supervisory expectation",
}


@dataclass
class Claim:
    text: str
    citations: list[str]
    kind: str
    check: str = ""  # filled by the verifier: "ok" or a problem code


@dataclass
class Answer:
    question: str
    abstained: bool
    abstain_reason: str
    answer: str
    claims: list[Claim]
    context: list[Hit]
    as_of: str
    model: str | None = None
    usage_tokens: int = 0
    errors: list[str] = field(default_factory=list)

    def cited_hits(self) -> list[Hit]:
        ids = {c for cl in self.claims for c in cl.citations}
        ids |= set(re.findall(r"\[(C\d+)\]", self.answer))
        return [h for i, h in enumerate(self.context, 1) if f"C{i}" in ids]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["context"] = [
            {"id": h.id, "ref": h.ref, "source_id": h.source_id, "score": h.score}
            for h in self.context
        ]
        return d


def format_context(hits: list[Hit]) -> str:
    """Numbered passages; the first line of each chunk text is its hierarchy prefix."""
    blocks = []
    for i, h in enumerate(hits, 1):
        level = LEVEL_LABEL.get(h.legal_level, h.legal_level)
        blocks.append(f"[C{i}] ({level}) {h.text}")
    return "\n\n".join(blocks)


def as_of_statement(hits: list[Hit], today: date) -> str:
    """'As of 28 Oct 2026; CRR consolidated version of 26 Jun 2026; ...' from chunk versions."""
    parts = [f"As of {today:%d %b %Y}"]
    seen = set()
    for h in hits:
        v = h.version or ""
        m = re.match(r"0\d{4}R\d{4}-(\d{4})(\d{2})(\d{2})$", v)
        if m and h.source_id not in seen:
            seen.add(h.source_id)
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            parts.append(f"CRR consolidated version of {d:%d %b %Y}")
    retrieved = sorted(
        {h.version for h in hits if h.version and re.match(r"\d{4}-\d{2}-\d{2}$", h.version)}
    )
    if retrieved:
        parts.append(f"other sources retrieved {date.fromisoformat(retrieved[-1]):%d %b %Y}")
    return "; ".join(parts)


def _parse_json(text: str) -> dict:
    """The model is asked for bare JSON; tolerate code fences or stray prose around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def answer_question(
    conn,
    provider: LLMProvider,
    config: Config,
    question: str,
    *,
    filters: Filters | None = None,
    today: date | None = None,
) -> Answer:
    opts = config.answer or {}
    today = today or date.today()
    hits = search(conn, question, mode="rerank", k=int(opts.get("k", 8)), filters=filters)
    as_of = as_of_statement(hits, today)

    best = hits[0].score if hits else 0.0
    if best < float(opts.get("abstain_below", 0.05)):
        return Answer(
            question,
            True,
            f"no relevant passage found (best score {best:.3f})",
            "",
            [],
            hits,
            as_of,
        )

    completion = provider.complete(
        user_prompt(question, format_context(hits)),
        purpose="answer",
        system=SYSTEM,
        tier=opts.get("tier", "dev"),
        effort=opts.get("effort"),
    )
    ans = Answer(
        question,
        False,
        "",
        "",
        [],
        hits,
        as_of,
        model=completion.model,
        usage_tokens=completion.usage.total_tokens,
    )
    try:
        data = _parse_json(completion.text)
    except (ValueError, json.JSONDecodeError) as e:
        ans.errors.append(f"unparseable model output: {e}")
        ans.answer = completion.text
        return ans
    ans.abstained = bool(data.get("abstain"))
    ans.abstain_reason = str(data.get("abstain_reason") or "")
    ans.answer = str(data.get("answer") or "")
    ans.claims = [
        Claim(
            str(c.get("text", "")), [str(x) for x in c.get("citations", [])], str(c.get("kind", ""))
        )
        for c in data.get("claims") or []
    ]
    return ans


def render(ans: Answer) -> str:
    """Markdown for the CLI / UI: answer, sources with legal level, as-of line, disclaimer."""
    if ans.abstained:
        body = f"**Not answered from the RegLens corpus.** {ans.abstain_reason}".strip()
    else:
        body = ans.answer
    lines = [body, "", f"_{ans.as_of}._", ""]
    cited = ans.cited_hits()
    if cited:
        lines.append("**Sources**")
        for i, h in enumerate(ans.context, 1):
            if h in cited:
                source = h.text.split(" › ", 1)[0]  # short source label from the prefix
                level = LEVEL_LABEL.get(h.legal_level, h.legal_level)
                lines.append(f"- [C{i}] {source} {h.ref} — {level}")
    problems = [c for c in ans.claims if c.check and c.check != "ok"]
    if problems:
        lines += ["", "**Citation check**"]
        lines += [f"- ⚠ {c.check}: {c.text}" for c in problems]
    lines += [
        "",
        "_Personal open-source project; not legal or regulatory advice. Check the official texts._",
    ]
    return "\n".join(lines)
