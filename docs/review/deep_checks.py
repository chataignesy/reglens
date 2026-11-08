"""Offline review probes; no model calls or database writes.

Run from the repository root: .venv/Scripts/python.exe docs/review/deep_checks.py
Outputs JSON evidence to stdout. `observed` records current behaviour, not desired behaviour.
"""

import json
import tempfile
from collections import defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reglens.agent import tools
from reglens.agent.tools import Row, Toolbox, citation_key
from reglens.cli import _cmd_judge
from reglens.config import load_config
from reglens.eval.answers import ANSWER_DIR, answer_version, citation_recall
from reglens.eval.golden import Citation, GoldenItem, load_golden
from reglens.eval.route import cached_routes
from reglens.ingest import pdf
from reglens.ingest.chunks import load_chunks
from reglens.ingest.eurlex import parse_xhtml
from reglens.ingest.xrefs import reference_edges
from reglens.llm.provider import ClaudeCLIProvider, LLMError


def main():
    out = {}
    chunks = load_chunks()

    # Change the actual PDF bytes, retaining source identity and conversion cache.
    with tempfile.TemporaryDirectory(prefix="reglens-review-") as tmp:
        root = Path(tmp)
        source = root / "source.pdf"
        (root / "sample.md").write_text("OLD converted regulation", encoding="utf-8")
        source.write_bytes(b"%PDF new regulatory text")
        with patch.object(pdf, "DOCLING_DIR", root):
            out["pdf_refresh"] = {"observed": pdf.pdf_to_markdown("sample", source)}
        xhtml = root / "law.xhtml"
        xhtml.write_text(
            """<div class="eli-subdivision" id="art_142">
          <div><span class="no-parag">1.</span>Definitions apply:
            <div class="grid-container"><div class="grid-list-column-1">(5a)</div>
            <div class="grid-list-column-2">large corporate means a company</div></div>
          </div><p>For the purposes of point (5a), use the audited figures.</p></div>""",
            encoding="utf-8",
        )
        units = parse_xhtml(xhtml, split_tokens=1)
        out["paragraph_continuation"] = {
            "expected_paragraph": "1",
            "observed_tail_paragraph": units[-1].paragraph,
        }

    # Use real processed data, but emulate SQL ordering/limits without a live database.
    def row(c):
        return Row(
            c.id,
            c.source_id,
            c.ref,
            c.title,
            c.text,
            c.legal_level,
            c.version,
            c.kind,
            c.article,
            c.paragraph,
            c.point,
        )

    def rows(_conn, _where, params, limit=50):
        found = [c for c in chunks if c.source_id == params[0] and c.article == params[1]]
        return [row(c) for c in sorted(found, key=lambda c: c.id)[:limit]]

    with patch.object(tools, "_rows", rows):
        result = Toolbox(None).get_article("CRR", "124")
        actual = [c for c in chunks if c.source_id == tools.CRR and c.article == "124"]
        out["article_truncation"] = {
            "available_chunks": len(actual),
            "available_chars": sum(len(c.text) for c in actual),
            "returned_chars": len(result),
            "truncation_disclosed": "truncated" in result,
            "end": result[-100:],
        }
        result = Toolbox(None).get_article("CRR", "4")
        out["article_row_limit"] = {
            "available_chunks": sum(c.source_id == tools.CRR and c.article == "4" for c in chunks),
            "query_limit": 40,
            "truncation_disclosed": "truncated" in result,
        }

    groups = defaultdict(list)
    for c in chunks:
        groups[citation_key(c.source_id, c.ref, c.title, c.kind)].append(c)
    key = "ECB validation reporting instructions para. 1"
    matches = groups[key]
    out["citation_collision"] = {
        "key": key,
        "chunks": len(matches),
        "numbering_blocks": sorted({c.article for c in matches}),
        "examples": [
            {"id": c.id, "prefix": c.prefix, "body_start": c.body[:95]} for c in matches[:3]
        ],
    }

    # Explicit reference to another paragraph in the SAME article is a useful graph edge.
    template = next(c for c in chunks if c.source_id == tools.CRR and c.article == "178")
    probe = replace(template, paragraph="1", body="The conditions in Article 178(3) shall apply.")
    out["same_article_reference"] = {
        "input": probe.body,
        "observed_edges": [asdict(e) for e in reference_edges(probe)],
    }

    # A paragraph range denotes multiple required paragraphs, not alternatives.
    item = GoldenItem(
        "review",
        "q",
        "factual",
        "a",
        [Citation("eba-gl-dod", "paras. 71-73")],
        "all",
        "t",
        "easy",
        "review",
        "verified",
    )
    record = {
        "context": [{"source_id": "eba-gl-dod", "ref": "para. 71"}],
        "claims": [{"citations": ["C1"]}],
    }
    out["range_recall"] = {
        "expected": "paras. 71-73",
        "cited": "para. 71",
        "observed": citation_recall(item, record),
    }
    item = replace(
        item, expected_citations=[Citation("ecb-guide-internal-models", "Foreword, para. 1")]
    )
    record["context"] = [
        {"source_id": "ecb-guide-internal-models", "ref": "para. 1", "title": "Credit risk"}
    ]
    out["wrong_part_recall"] = {
        "expected": "Foreword, para. 1",
        "cited_part": "Credit risk",
        "observed": citation_recall(item, record),
    }

    # Generic MCP clients keep the server alive across questions.
    box = Toolbox(None)
    for _ in range(10):
        box._budget()
    out["mcp_session_lifetime"] = {"first_call_next_question": box._budget()}

    # Intercept the CLI judge's selector, never calling a provider.
    selected = {}
    args = SimpleNamespace(
        config=None,
        agent=True,
        set="all",
        type=None,
        id=None,
        limit=None,
        repeat=None,
        tokens_per_call=2000,
        yes=False,
    )

    def plan(items):
        selected["namespace"] = __import__(
            "reglens.eval.judge", fromlist=["ANSWER_VERSION"]
        ).ANSWER_VERSION
        return {"needs_call": [], "deterministic": [], "cached": [], "no_answer": []}

    with patch("reglens.eval.judge.plan", side_effect=plan), patch("builtins.print"):
        _cmd_judge(args)
    all_items = [i for i in load_golden() if i.status == "verified"]
    routes = cached_routes()
    stayed_single = []
    for i in all_items:
        path = ANSWER_DIR / answer_version(False) / f"{i.id}.json"
        if routes.get(i.id) != "agent" and path.exists():
            if not json.loads(path.read_text(encoding="utf-8")).get("missing_info"):
                stayed_single.append(i.id)
    selected["cached_records"] = len(list((ANSWER_DIR / selected["namespace"]).glob("*.json")))
    selected["golden_items"] = len(all_items)
    selected["routed_single_records_absent_from_selected_namespace"] = sum(
        not (ANSWER_DIR / selected["namespace"] / f"{i}.json").exists() for i in stayed_single
    )
    out["routed_judge_selection"] = selected

    # Definition-only tool output omits a separately chunked qualification.
    tail = next(
        c
        for c in chunks
        if c.source_id == tools.CRR
        and c.article == "142"
        and c.paragraph is None
        and "first subparagraph, point (5a)" in c.body
    )
    out["definition_qualification"] = {
        "id": tail.id,
        "paragraph": tail.paragraph,
        "body_start": tail.body[:180],
        "get_definition_excludes": tail.point is None,
    }
    ledger = SimpleNamespace(record=lambda *a, **k: calls.append(k))
    calls = []

    def failed_run(*args, **kwargs):
        return SimpleNamespace(
            stdout=json.dumps(
                {
                    "is_error": True,
                    "subtype": "error_max_budget_usd",
                    "usage": {"input_tokens": 1000, "output_tokens": 100},
                }
            ),
            returncode=1,
            stderr="",
        )

    provider = ClaudeCLIProvider(load_config(), ledger=ledger, runner=failed_run)
    try:
        provider.complete("offline probe", purpose="agent")
    except LLMError:
        pass
    out["failed_cli_usage"] = {"reported_tokens": 1100, "ledger_records": len(calls)}
    # All checks are structural observations; do not log long raw legal documents.
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
