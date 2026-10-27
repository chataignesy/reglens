"""EBA Single Rulebook Q&A: polite crawler + parser for final credit-risk Q&As.

Respects the site's robots.txt (`Crawl-delay: 10`, `/search` disallowed — we only use the
public listing and Q&A pages). Every page is cached under data/raw/eba-qa-credit-risk/, so
re-runs are free and an interrupted crawl resumes where it stopped.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from reglens.config import PROJECT_ROOT
from reglens.ingest.download import USER_AGENT, _get
from reglens.ingest.eurlex import Unit

BASE = "https://www.eba.europa.eu"
RAW = PROJECT_ROOT / "data" / "raw" / "eba-qa-credit-risk"
CRAWL_DELAY_S = 10
_ID = re.compile(r"/single-rule-book-qa/qna/view/publicId/(\d{4}_\d+)")


@dataclass
class QA:
    id: str
    legal_act: str
    topic: str
    article: str
    paragraph: str
    subject: str
    question: str
    background: str
    answer: str
    status: str
    published: str
    url: str


class _Polite:
    """Fetch with a fixed delay between network requests; cache hits are free."""

    def __init__(self, delay_s: int = CRAWL_DELAY_S):
        self.delay_s = delay_s
        self.last = 0.0
        self.fetched = 0

    def get(self, url: str, cache: Path) -> str:
        if cache.exists():
            return cache.read_text(encoding="utf-8")
        wait = self.delay_s - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        html = _get(url, accept="text/html").decode("utf-8", errors="replace")
        self.last = time.time()
        self.fetched += 1
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(html, encoding="utf-8")
        return html


def _field(soup: BeautifulSoup, name: str) -> str:
    el = soup.find(class_=f"field--name-qa-{name}")
    if not el:
        return ""
    label = el.find(class_="field__label")
    if label:
        label.decompose()
    return re.sub(r"[ \t\xa0]+", " ", el.get_text("\n")).strip()


def parse_qa(html: str, url: str) -> QA:
    s = BeautifulSoup(html, "lxml")
    return QA(
        id=_field(s, "question-id"),
        # legal act and topic are fixed by the listing filter (CRR, Credit risk)
        legal_act=_field(s, "legal-act") or "Regulation (EU) No 575/2013 (CRR)",
        topic=_field(s, "legal-act-topic") or "Credit risk",
        article=_field(s, "legal-article"),
        paragraph=_field(s, "article-paragraph"),
        subject=_field(s, "subject-matter"),
        question=_field(s, "question"),
        background=_field(s, "question-background"),
        answer=_field(s, "final-answer"),
        status=_field(s, "status"),
        published=_field(s, "final-publishing-date"),
        url=url,
    )


def crawl(listing_url: str, *, max_pages: int = 50, log=print) -> list[QA]:
    """Walk the filtered listing, fetch every Q&A page, keep final answered Q&As."""
    http = _Polite()
    ids: list[str] = []
    for page in range(max_pages):
        sep = "&" if "?" in listing_url else "?"
        html = http.get(f"{listing_url}{sep}page={page}", RAW / "pages" / f"page-{page:03d}.html")
        new = [i for i in dict.fromkeys(_ID.findall(html)) if i not in ids]
        if not new:
            break
        ids += new
        log(f"listing page {page}: {len(ids)} Q&As so far")
    out: list[QA] = []
    for n, qid in enumerate(ids, 1):
        url = f"{BASE}/single-rule-book-qa/qna/view/publicId/{qid}"
        qa = parse_qa(http.get(url, RAW / "qa" / f"{qid}.html"), url)
        if qa.status.lower().startswith("final") and qa.answer:
            out.append(qa)
        if n % 25 == 0:
            log(f"Q&A pages: {n}/{len(ids)} ({http.fetched} fetched, {len(out)} final)")
    (RAW / "qa.jsonl").write_text(
        "".join(json.dumps(asdict(q), ensure_ascii=False) + "\n" for q in out), encoding="utf-8"
    )
    log(f"done: {len(out)} final Q&As of {len(ids)} listed; {http.fetched} network requests")
    return out


def load_qas(path: Path | None = None) -> list[QA]:
    path = path or RAW / "qa.jsonl"
    return [QA(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()]


def _article_number(qa: QA) -> str | None:
    m = re.match(r"^\s*(\d{1,3}[a-z]?)\b", qa.article)
    return m.group(1) if m else None


def qa_units(qas: list[QA]) -> list[Unit]:
    """One unit per Q&A; `article` holds the CRR article it concerns (for get_qa / edges)."""
    units = []
    for q in qas:
        art = _article_number(q)
        where = f"CRR Art. {q.article}" if art else (q.article or "")
        parts = [
            f"Subject: {q.subject}",
            f"Question: {q.question}",
            f"Background: {q.background}" if q.background else "",
            f"Answer: {q.answer}",
            f"(Final Q&A {q.id}, published {q.published})" if q.published else f"(Q&A {q.id})",
        ]
        units.append(
            Unit(
                kind="qa",
                article=art,
                paragraph=q.id,
                point=None,
                hierarchy=[("", where), ("", q.topic)] if where else [("", q.topic)],
                title=q.subject,
                text="\n".join(p for p in parts if p),
            )
        )
    return units


__all__ = ["QA", "crawl", "load_qas", "parse_qa", "qa_units", "USER_AGENT"]
