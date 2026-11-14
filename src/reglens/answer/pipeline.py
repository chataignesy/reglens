"""Grounded answering: retrieve -> numbered context -> LLM (JSON) -> verify -> render.

The as-of statement and the legal level of each cited source are set by code from chunk
metadata, not by the model.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date

from reglens.answer.prompts import SYSTEM, user_prompt
from reglens.config import Config
from reglens.llm.provider import LLMError, LLMProvider
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
    trace: list[dict] = field(default_factory=list)  # agent tool calls (empty for single-pass)
    missing_info: bool = False  # the passages lacked information needed for a complete answer
    research_needed: bool | None = None  # None: legacy output; False: no useful further lookup
    missing_requirements: list[str] = field(default_factory=list)
    # The model's reply broke the answer contract (answer/schema.py) even after a retry: no
    # answer is shown; `raw_output` keeps the reply for diagnosis, clearly labelled unverified.
    unverified: bool = False
    raw_output: str = ""
    # agent answers: context passages (C#) cited after reading only a truncated snippet
    partial_cids: list[str] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    corpus_generation: str = "legacy"
    source_registry: dict | None = None
    research: dict = field(default_factory=dict)
    semantic_review: dict = field(default_factory=lambda: {"status": "not_run"})
    usage_unknown_calls: int = 0
    retryable_error: bool = False  # provider interruption; safe to retry on a later eval run
    answer_requirements: list[dict] = field(default_factory=list)

    def cited_hits(self) -> list[Hit]:
        ids = {c for cl in self.claims for c in cl.citations}
        ids |= set(re.findall(r"\[(C\d+)\]", self.answer))
        return [h for i, h in enumerate(self.context, 1) if f"C{i}" in ids]

    def to_dict(self) -> dict:
        import hashlib

        d = asdict(self)
        d["evidence"] = [
            {
                "id": h.id,
                "generation": self.corpus_generation,
                "sha256": hashlib.sha256(h.text.encode()).hexdigest(),
                "text": h.text,
            }
            for h in self.context
        ]
        d["context"] = [{k: v for k, v in asdict(h).items() if k != "text"} for h in self.context]
        return d


Progress = Callable[[dict], None]


def _no_progress(event: dict) -> None:
    return None


def format_context(hits: list[Hit]) -> str:
    """Numbered passages; the first line of each chunk text is its hierarchy prefix."""
    blocks = []
    for i, h in enumerate(hits, 1):
        level = LEVEL_LABEL.get(h.legal_level, h.legal_level)
        from reglens.context import METADATA

        dates = {k: getattr(h, k) for k in METADATA if getattr(h, k)}
        blocks.append(
            f"[C{i}] ({level}; context metadata: {dates}; "
            f"temporal verified: {h.temporal_verified}) {h.text}"
        )
    return "\n\n".join(blocks)


def as_of_statement(hits: list[Hit], today: date) -> str:
    """'Answered 28 Oct 2026 from: CRR consolidated version of 26 Jun 2026; ...'.

    The date the answer was generated is kept apart from the versions of the sources it used:
    the corpus is a snapshot (consolidated text, download dates), not a legal point-in-time
    model, so the answer is not "as of" today's law, only as of those versions.
    """
    parts = [f"Answered {today:%d %b %Y} from"]
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
        parts.append(f"other sources as downloaded {date.fromisoformat(retrieved[-1]):%d %b %Y}")
    if len(parts) == 1:
        return f"Answered {today:%d %b %Y}"
    return parts[0] + ": " + "; ".join(parts[1:])


def _parse_json(text: str) -> dict:
    """The model is asked for bare JSON; tolerate code fences or stray prose around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    raw = text[start : end + 1]
    try:
        return json.loads(raw, strict=False)  # strict=False: raw newlines/tabs inside strings
    except json.JSONDecodeError:
        return json.loads(_escape_inner_quotes(raw), strict=False)


def _escape_inner_quotes(raw: str) -> str:
    """Escape quotes the model left unescaped inside strings (e.g. 'read your "past due" as'):
    inside a string, a quote ends it only if followed by , : } ] or the end."""
    out, in_str, i = [], False, 0
    while i < len(raw):
        ch = raw[i]
        if in_str and ch == "\\":
            out.append(raw[i : i + 2])
            i += 2
            continue
        if ch == '"':
            if not in_str:
                in_str = True
            elif (rest := raw[i + 1 :].lstrip()) == "" or rest[0] in ",:}]":
                in_str = False
            else:
                ch = '\\"'
        out.append(ch)
        i += 1
    return "".join(out)


def answer_question(
    conn,
    provider: LLMProvider,
    config: Config,
    question: str,
    *,
    filters: Filters | None = None,
    today: date | None = None,
    progress: Progress | None = None,
) -> Answer:
    """`progress`, if given, receives stage events (dicts) as the answer is produced."""
    opts = config.answer or {}
    today = today or date.today()
    emit = progress or _no_progress
    from reglens.answer.scope import refusal_reason

    if reason := refusal_reason(question):
        return Answer(question, True, reason, "", [], [], as_of_statement([], today))
    hits = search(conn, question, mode="rerank", k=int(opts.get("k", 8)), filters=filters)
    from reglens.answer.context_plan import expand_context

    hits = expand_context(conn, question, hits, filters)
    emit({"stage": "retrieved", "passages": len(hits), "refs": [h.ref for h in hits[:3]]})
    as_of = as_of_statement(hits, today)

    from reglens.context import coverage
    from reglens.index.generations import current

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
            coverage=coverage(hits, filters),
            corpus_generation=current(conn),
        )

    from reglens.answer.schema import parse_reply, retry_note

    emit({"stage": "drafting"})
    from reglens.context import coverage, instruction
    from reglens.index.generations import current

    prompt = user_prompt(question + instruction(filters), format_context(hits))
    ans = Answer(question, False, "", "", [], hits, as_of)
    ans.coverage = coverage(hits, filters)
    from reglens.sources import load_sources

    ans.source_registry = {s.id: asdict(s) for s in load_sources(conn=conn)}
    ans.corpus_generation = current(conn)
    found: list[str] = []
    next_prompt, purpose = prompt, "answer"
    from reglens.answer.research import guard

    for attempt in range(2):  # one shared second draft for contract repair or delivered omissions
        try:
            completion = provider.complete(
                next_prompt,
                purpose=purpose,
                system=SYSTEM,
                tier=opts.get("tier", "dev"),
                effort=opts.get("effort"),
            )
        except LLMError as exc:
            ans.usage_tokens += exc.tokens or 0
            ans.usage_unknown_calls += int(not exc.usage_known)
            ans.unverified = True
            ans.errors.append(str(exc))
            ans.retryable_error = exc.retryable
            return ans
        ans.model = completion.model
        ans.usage_tokens += completion.usage.total_tokens
        ans.usage_unknown_calls += int(not completion.usage_known)
        data, found = parse_reply(completion.text)
        if found:
            emit({"stage": "invalid_reply", "problems": found, "retry": attempt == 0})
            next_prompt, purpose = prompt + retry_note(found), "answer_retry"
            continue
        gaps = guard(question, data, hits, conn=conn, filters=filters)
        review_prefix = "Review requested list coverage"
        if (attempt == 0 and gaps
                and all(g.startswith(review_prefix) for g in data.get("missing_requirements", []))):
            ans.trace.append({"tool": "answer_completion", "requirements": gaps,
                              "basis": "required facts already delivered; no new retrieval"})
            emit({"stage": "completing", "reason": "Required facts are already in the context"})
            next_prompt = (
                prompt + "\n\nPrevious draft:\n" + completion.text
                + "\n\nRevise the answer using ONLY the context already supplied. "
                "Cover these required source items explicitly in the answer, with citations: "
                + "; ".join(gaps)
                + ". Do not research or introduce optional background. Return the final JSON."
            )
            purpose = "answer_completion"
            continue
        break
    if found:
        ans.unverified, ans.raw_output = True, completion.text
        ans.errors.append("invalid model output after one retry: " + "; ".join(found))
        return ans
    if gaps:
        ans.trace.append({"tool": "research_guard", "gaps": gaps})
    ans.abstained = bool(data.get("abstain"))
    ans.abstain_reason = str(data.get("abstain_reason") or "")
    ans.missing_info = bool(data.get("missing_info"))
    ans.research_needed = data.get("research_needed")
    ans.missing_requirements = data.get("missing_requirements", [])
    ans.answer_requirements = data.get("answer_requirements", [])
    ans.answer = str(data.get("answer") or "")
    from reglens.answer.research import report

    ans.research = report(data, {f"C{i}" for i in range(1, len(hits) + 1)})
    ans.claims = [
        Claim(
            str(c.get("text", "")), [str(x) for x in c.get("citations", [])], str(c.get("kind", ""))
        )
        for c in data.get("claims") or []
    ]
    return ans


def render(ans: Answer) -> str:
    """Markdown for the CLI / UI: answer, sources with legal level, as-of line, disclaimer."""
    if ans.unverified:
        body = "**No verified answer.** Output or evidence checks did not pass. " + "; ".join(
            ans.errors
        )
    elif ans.abstained:
        body = f"**Not answered from the RegLens corpus.** {ans.abstain_reason}".strip()
    else:
        body = ans.answer
    lines = [body, "", f"_{ans.as_of}._", ""]
    if "unknown" in (ans.coverage.get("temporal"), ans.coverage.get("applicability")):
        lines += ["Requested date/applicability is not verified for every source.", ""]
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
        lines += ["", "**Mechanical citation checks** (citation, numbers, legal level)"]
        lines += [f"- ⚠ {c.check}: {c.text}" for c in problems]
    if ans.usage_unknown_calls:
        lines += ["", f"Known usage: at least {ans.usage_tokens:,} tokens; "
                  f"{ans.usage_unknown_calls} call(s) reported no complete usage."]
    lines += [
        "",
        "_Personal open-source project; not legal or regulatory advice. Check the official texts._",
    ]
    return "\n".join(lines)
