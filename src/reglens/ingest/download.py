"""Download EUR-Lex documents through the official CELLAR API of the Publications Office.

The eur-lex.europa.eu website sits behind a bot challenge; CELLAR is the intended
machine-access route. Files go to data/raw/<source id>/; download records (resolved
version, URL, date, sha256) go to sources.lock.json, which is committed.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import date

from reglens.config import PROJECT_ROOT
from reglens.sources import Source

CELLAR = "http://publications.europa.eu/resource/celex/"
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
USER_AGENT = "RegLens/0.1 (open-source research project)"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
LOCK_FILE = PROJECT_ROOT / "sources.lock.json"


def _get(url: str, *, accept: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "eng"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def consolidated_versions(base_celex: str) -> list[str]:
    """All consolidated CELEX numbers for a base act, e.g. 02013R0575-20260626, newest first."""
    query = (
        "PREFIX cdm: <http://publications.europa.eu/ontology/cdm#> "
        "SELECT DISTINCT ?celex WHERE { ?w cdm:resource_legal_id_celex ?celex . "
        f'FILTER(STRSTARTS(STR(?celex), "{base_celex}-")) }} ORDER BY DESC(?celex)'
    )
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "text/csv"})
    lines = _get(url, accept="text/csv").decode("utf-8").splitlines()[1:]
    return [line.strip().strip('"') for line in lines if line.strip()]


def pick_version(versions: list[str], as_of: date) -> str:
    """Latest consolidated version whose date is on or before `as_of`."""
    in_force = [v for v in versions if date.fromisoformat(_version_date(v)) <= as_of]
    if not in_force:
        raise ValueError(f"No consolidated version on or before {as_of}: {versions[:3]}")
    return max(in_force, key=_version_date)


def _version_date(celex: str) -> str:
    d = celex.rsplit("-", 1)[1]
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def resolve_celex(source: Source, as_of: date) -> str:
    if not source.celex:
        raise ValueError(f"{source.id}: no CELEX number")
    if source.consolidated:
        return pick_version(consolidated_versions(source.celex), as_of)
    return source.celex


def load_lock() -> dict:
    if not LOCK_FILE.exists():
        return {}
    return json.loads(LOCK_FILE.read_text(encoding="utf-8"))


def save_lock(lock: dict) -> None:
    LOCK_FILE.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def download(source: Source, *, as_of: date, force: bool = False) -> dict:
    """Fetch one source as XHTML; returns its lock record. Skips if already downloaded."""
    celex = resolve_celex(source, as_of)
    path = RAW_DIR / source.id / f"{celex}.xhtml"
    lock = load_lock()
    record = lock.get(source.id)
    if not force and record and record["celex"] == celex and path.exists():
        return record

    url = CELLAR + celex
    body = _get(url, accept="application/xhtml+xml, text/html;q=0.9")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)

    record = {
        "celex": celex,
        "url": url,
        "as_of": as_of.isoformat(),
        "retrieved": date.today().isoformat(),
        "file": path.relative_to(PROJECT_ROOT).as_posix(),
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    lock[source.id] = record
    save_lock(lock)
    return record
