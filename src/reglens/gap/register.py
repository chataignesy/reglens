"""Obligation register: atomic obligations extracted from the passages in `scope.yaml`.

One LLM call per batch of passages (dev tier, Sonnet; Opus was the first choice but the local
Claude Code CLI is too old for it). Each
obligation keeps a verbatim quote, which code checks against its source passage, so every
obligation in the register is traceable to the regulation's own words. Batches are cached
per prompt version and batch content, so re-running costs nothing and widening the scope only
extracts the new passages; the register is written to
`register/obligations.jsonl` (committed: it is the reviewable output), with
`register/manifest.json` recording the source file digests, model and prompt version it was
built from. A batch's cache key covers the prompt version, model, effort and the full passage
text, so a corrected or updated source text is extracted again, never matched to an old reply.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from reglens.agent.tools import citation_key
from reglens.answer.pipeline import LEVEL_LABEL, _parse_json
from reglens.config import PROJECT_ROOT
from reglens.llm.provider import LLMProvider

SCOPE_FILE = Path(__file__).with_name("scope.yaml")
REGISTER_FILE = PROJECT_ROOT / "register" / "obligations.jsonl"
BATCH_DIR = PROJECT_ROOT / "data" / "register" / "batches"
BATCH_TOKENS = 3500  # passage text per call
CHARS_PER_TOKEN = 3.01
EXTRACT_TIER = "dev"
EXTRACT_EFFORT = "medium"
MANIFEST_FILE = PROJECT_ROOT / "register" / "manifest.json"

ACTORS = (
    "management body",
    "senior management",
    "validation function",
    "credit risk control unit",
    "internal audit",
    "model owner",
    "institution",
)
TOPICS = (
    "governance",
    "independence",
    "model-inventory",
    "validation-scope-frequency",
    "data-and-default",
    "pd",
    "lgd",
    "downturn-lgd",
    "ccf",
    "moc",
    "crm-and-scope",
    "findings",
    "reporting",
    "internal-audit",
    "model-changes",
    "documentation",
    "use-test",
    "other",
)

EXTRACT_SYSTEM = f"""\
You build an obligation register from EU credit risk regulation for a gap analysis of a bank's
IRB Model Validation Policy and the governance around it.

From the numbered passages, extract every ATOMIC obligation a bank must meet: one actor, one
action, one condition. Split compound sentences ("shall X and Y" -> two obligations).

Include obligations on the institution or its bodies and functions. When a passage tells the
competent authority to verify or assess that the institution does something, record that thing
as the institution's obligation. Skip: pure definitions, duties of supervisors or the EBA that
imply nothing for the bank, transitional dates, and descriptive or explanatory text.

For each obligation give:
- "passage": the passage number, e.g. "P3";
- "actor": one of {", ".join(ACTORS)};
- "obligation": one plain-English sentence starting with the actor, e.g. "The validation
  function shall ..."; keep numbers, thresholds and periods exactly as written;
- "quote": a VERBATIM span (at most 300 characters) copied from the passage that states it;
- "topic": one of {", ".join(TOPICS)};
- "strength": "shall" (law), "should" (guidelines) or "expects" (ECB supervisory expectation),
  following the wording of the passage;
- "validation_relevant": true if an IRB Model Validation Policy or the governance around model
  validation (approval, independence, data and default definition checks, back-testing,
  review of estimates, MoC, findings, reporting, audit, and checks that models respect the
  A-IRB scope limits and the PD/LGD/CCF input floors) should address it; false for
  obligations that only concern capital calculation mechanics or exposure treatment.

Reply with ONE JSON object and nothing else: {{"obligations": [ ... ]}}
An empty list is fine when a passage contains no obligation for the bank."""

REGISTER_VERSION = hashlib.sha256(EXTRACT_SYSTEM.encode()).hexdigest()[:8]


@dataclass
class Passage:
    chunk_id: str
    source_id: str
    ref: str
    key: str
    legal_level: str
    applies_to: str
    text: str
    source_sha256: str = ""  # raw source file the passage was parsed from


@dataclass
class Obligation:
    id: str
    key: str  # citation key of the source passage, e.g. "CRR Art. 185(b)"
    source_id: str
    ref: str
    chunk_id: str
    legal_level: str
    applies_to: str
    actor: str
    obligation: str
    quote: str
    quote_ok: bool  # the quote occurs verbatim (after normalisation) in the passage
    topic: str
    strength: str
    validation_relevant: bool = True
    legacy_ids: list[str] = field(default_factory=list)
    source_sha256: str = ""


def load_scope() -> list[dict]:
    return yaml.safe_load(SCOPE_FILE.read_text(encoding="utf-8"))


def select_passages(conn) -> list[Passage]:
    out: list[Passage] = []
    for s in load_scope():
        rows = conn.execute(
            "SELECT id, source_id, ref, title, kind, article, hierarchy, legal_level, applies_to, "
            "text, source_sha256 FROM chunks "
            "WHERE source_id = %s AND kind NOT IN ('background', 'recital')",
            (s["source"],),
        ).fetchall()
        rows.sort(key=lambda r: _natural(r[0]))  # Art. 151(2) before 151(10)
        for cid, src, ref, title, kind, article, hierarchy, level, applies, text, sha in rows:
            by_article = article in s.get("articles", [])
            by_section = any(h.startswith(tuple(s.get("sections", []))) for h in hierarchy)
            if by_article or by_section:
                key = citation_key(src, ref, title, kind)
                out.append(Passage(cid, src, ref, key, level, applies, text, sha))
    return out


def _natural(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def batches(passages: list[Passage], max_tokens: int = BATCH_TOKENS) -> list[list[Passage]]:
    """Consecutive passages of one source, up to `max_tokens` of text per batch."""
    out: list[list[Passage]] = []
    for p in passages:
        size = len(p.text) / CHARS_PER_TOKEN
        last = out[-1] if out else None
        if (
            last
            and last[0].source_id == p.source_id
            and sum(len(q.text) for q in last) / CHARS_PER_TOKEN + size <= max_tokens
        ):
            last.append(p)
        else:
            out.append([p])
    return out


def batch_id(batch: list[Passage], model: str) -> str:
    """Cache key: prompt version, model and settings, and the exact passage text sent."""
    raw = "|".join([REGISTER_VERSION, model, EXTRACT_EFFORT, batch_prompt(batch)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def batch_prompt(batch: list[Passage]) -> str:
    return "\n\n".join(
        f"[P{i}] {p.key} ({LEVEL_LABEL.get(p.legal_level, p.legal_level)})\n{p.text}"
        for i, p in enumerate(batch, 1)
    )


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).replace("‘", "'").replace("’", "'")
    s = s.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_in(quote: str, text: str) -> bool:
    q = _norm(quote).strip(" .…'\"")
    return bool(q) and q in _norm(text)


def parse_batch(batch: list[Passage], reply: str) -> list[Obligation]:
    data = _parse_json(reply)
    out = []
    for o in data.get("obligations") or []:
        m = re.fullmatch(r"P(\d+)", str(o.get("passage", "")).strip())
        if not m or not 1 <= int(m.group(1)) <= len(batch):
            continue
        p = batch[int(m.group(1)) - 1]
        quote = str(o.get("quote", ""))
        topic = str(o.get("topic", "other"))
        out.append(
            Obligation(
                id="",
                key=p.key,
                source_id=p.source_id,
                ref=p.ref,
                chunk_id=p.chunk_id,
                legal_level=p.legal_level,
                applies_to=p.applies_to,
                actor=str(o.get("actor", "institution")),
                obligation=str(o.get("obligation", "")).strip(),
                quote=quote,
                quote_ok=quote_in(quote, p.text),
                topic=topic if topic in TOPICS else "other",
                strength=str(o.get("strength", "")),
                validation_relevant=bool(o.get("validation_relevant", True)),
                source_sha256=p.source_sha256,
            )
        )
    return out


def stable_id(o: Obligation) -> str:
    """Content identity, independent of extraction order, windowing, quotes and topic labels.
    A changed requirement gets a new id; paraphrases are not guessed to be equivalent."""
    identity = [
        _norm(x) for x in (o.source_id, o.key, o.actor, o.obligation, o.strength, o.applies_to)
    ]
    return "OB-" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]


def assign_ids(obligations: list[Obligation], previous: list[Obligation] = ()) -> None:
    aliases = {stable_id(o): sorted(set(o.legacy_ids + ([o.id] if o.id else []))) for o in previous}
    for o in obligations:
        new = stable_id(o)
        old = [o.id] if o.id and o.id != new else []
        o.legacy_ids = sorted(set(o.legacy_ids + old + aliases.get(new, [])) - {new})
        o.id = new


def id_lookup(obligations: list[Obligation]) -> dict[str, Obligation]:
    out = {}
    for o in obligations:
        for key in [o.id, *o.legacy_ids]:
            if key in out and out[key].id != o.id:
                raise ValueError(f"Ambiguous obligation alias: {key}")
            out[key] = o
    return out


def extract(
    conn, provider: LLMProvider, *, model: str, limit: int | None = None, log=print
) -> tuple[list[Obligation], int]:
    """Extract (or load cached) batches; returns (obligations, new tokens)."""
    out_dir = BATCH_DIR / REGISTER_VERSION
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = batches(select_passages(conn))[:limit]
    obligations, new_tokens = [], 0
    for n, batch in enumerate(todo, 1):
        path = out_dir / f"{batch_id(batch, model)}.json"
        if path.exists():
            reply = json.loads(path.read_text(encoding="utf-8"))["reply"]
        else:
            c = provider.complete(
                batch_prompt(batch),
                purpose="register",
                system=EXTRACT_SYSTEM,
                tier=EXTRACT_TIER,
                effort=EXTRACT_EFFORT,
            )
            reply = c.text
            record = {
                "model": c.model,
                "effort": EXTRACT_EFFORT,
                "chunks": [p.chunk_id for p in batch],
                "source_sha256": sorted({p.source_sha256 for p in batch}),
                "reply": reply,
            }
            path.write_text(json.dumps(record, ensure_ascii=False))
            new_tokens += c.usage.total_tokens
            log(
                f"  [{n}/{len(todo)}] {batch[0].key} … {len(batch)} passages: "
                f"{c.usage.total_tokens:,} tokens"
            )
        try:
            obligations += parse_batch(batch, reply)
        except (ValueError, json.JSONDecodeError) as e:
            log(f"  [{n}] unparseable reply: {e}")
    previous = load_register() if REGISTER_FILE.exists() else []
    assign_ids(obligations, previous)
    # Repeated extraction of the same requirement should not create duplicate identities.
    unique: dict[str, Obligation] = {}
    for o in obligations:
        if o.id in unique:
            unique[o.id].legacy_ids = sorted(set(unique[o.id].legacy_ids + o.legacy_ids))
        else:
            unique[o.id] = o
    return list(unique.values()), new_tokens


def write_register(obligations: list[Obligation], path: Path = REGISTER_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for o in obligations:
            f.write(json.dumps(asdict(o), ensure_ascii=False) + "\n")


def write_manifest(conn, model: str, obligations: list[Obligation]) -> None:
    """What the register was built from: prompt version, model, and each source's digest."""
    sources = sorted({o.source_id for o in obligations})
    rows = conn.execute(
        "SELECT DISTINCT source_id, source_sha256, version FROM chunks WHERE source_id = ANY(%s)",
        (sources,),
    ).fetchall()
    manifest = {
        "register_version": REGISTER_VERSION,
        "model": model,
        "effort": EXTRACT_EFFORT,
        "obligations": len(obligations),
        "sources": {s: {"sha256": sha, "version": v} for s, sha, v in sorted(rows)},
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def load_register(path: Path = REGISTER_FILE) -> list[Obligation]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Obligation(**json.loads(line)) for line in lines if line.strip()]
