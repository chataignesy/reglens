"""Command line: usage, estimate, download, tokens, calibrate."""

from __future__ import annotations

import argparse
from datetime import date

from reglens.config import PROJECT_ROOT, load_config
from reglens.llm.ledger import Ledger, Usage
from reglens.sources import load_sources


def _eur_label(billing: str) -> str:
    return "API-eq EUR" if billing == "subscription" else "EUR"


def _cmd_usage(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    ledger = Ledger(cfg)
    rows = ledger.summary(by=args.by)
    budget = cfg.budget
    eur = _eur_label(cfg.billing)

    print(
        f"{args.by:<24}{'calls':>7}{'input':>13}{'cached':>13}{'output':>11}{'total':>13}{eur:>12}"
    )
    for key in sorted(rows, key=str):
        r = rows[key]
        print(
            f"{str(key):<24}{r['calls']:>7}{r['input_tokens']:>13,}{r['cached_tokens']:>13,}"
            f"{r['output_tokens']:>11,}{r['total_tokens']:>13,}{r['cost_eur']:>12.2f}"
        )

    total = ledger.total_eur()
    phase = budget.current_phase
    phase_row = ledger.summary(by="phase").get(phase, {})
    phase_spent = phase_row.get("cost_eur", 0.0)
    phase_budget = budget.phases_eur.get(phase, 0.0)
    print()
    print(
        f"Total tokens: {ledger.total_tokens():,}  (phase {phase}: "
        f"{int(phase_row.get('total_tokens', 0)):,})"
    )
    print(
        f"{eur}: {total:.2f} of target {budget.target_eur:.0f}"
        f" (ceiling {budget.ceiling_eur:.0f}); phase {phase}: {phase_spent:.2f}"
        f" of {phase_budget:.0f}"
    )
    if cfg.billing == "subscription":
        print("Billing: subscription — EUR is API-equivalent, for comparison only.")
    if total > budget.ceiling_eur:
        print("!! Over the ceiling — stop and review before more runs.")
    elif total > budget.target_eur or phase_spent > phase_budget:
        print("! Over budget target — review before more runs.")


def _cmd_estimate(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    model = args.model or cfg.model(args.tier)
    usage = Usage(input_tokens=args.input, output_tokens=args.output)
    tokens = usage.total_tokens * args.calls
    per_call = Ledger(cfg).estimate_eur(model, usage, batch=args.batch)
    print(f"{model}: {usage.total_tokens:,} tokens per call x {args.calls} = {tokens:,} tokens")
    if per_call is not None:
        print(f"{_eur_label(cfg.billing)}: {per_call * args.calls:.2f}")

    if cfg.billing == "subscription":
        over = tokens > cfg.budget.approval_threshold_tokens
        limit = f"{cfg.budget.approval_threshold_tokens:,} tokens"
    else:
        over = per_call is not None and per_call * args.calls > cfg.budget.approval_threshold_eur
        limit = f"EUR {cfg.budget.approval_threshold_eur:.0f}"
    if over:
        print(f"Above {limit} — needs approval before running.")


def _cmd_download(args: argparse.Namespace) -> None:
    from reglens.ingest.download import download, downloadable

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    all_sources = load_sources()
    wanted = set(args.source or [s.id for s in all_sources])
    sources = [s for s in all_sources if downloadable(s) and s.id in wanted]
    for s in sources:
        if s.format == "eba-qa":  # polite crawl (10 s between requests), cached and resumable
            from reglens.ingest.download import record_file
            from reglens.ingest.eba_qa import RAW, crawl

            crawl(s.url, log=lambda m: print(f"  {m}", flush=True))
            r = record_file(s, RAW / "qa.jsonl", url=s.url, as_of=as_of)
        else:
            r = download(s, as_of=as_of, force=args.force)
        version = r["celex"] or s.format
        print(f"{s.id:<26}{version:<22}{r['bytes']:>12,} bytes  {r['retrieved']}")
    skipped = [s.id for s in all_sources if not downloadable(s)]
    if skipped and not args.source:
        print(f"\nNo URL yet (not downloaded): {', '.join(skipped)}")


def _cmd_tokens(args: argparse.Namespace) -> None:
    from reglens.ingest.download import load_lock
    from reglens.ingest.tokens import estimate_tokens, file_text

    cfg = load_config(args.config)
    lock = load_lock()
    total = 0
    print(f"{'source':<26}{'version':<22}{'chars':>12}{'~tokens':>11}")
    for sid, rec in sorted(lock.items()):
        path = PROJECT_ROOT / rec["file"]
        text = path.read_text(encoding="utf-8") if path.suffix == ".jsonl" else file_text(path)
        n = estimate_tokens(text, cfg.chars_per_token)
        total += n
        print(f"{sid:<26}{rec['celex'] or '-':<22}{len(text):>12,}{n:>11,}")
    print(
        f"\nTotal ~{total:,} tokens (full documents; MVP scope is a subset) "
        f"at {cfg.chars_per_token:.2f} chars/token"
    )


def _cmd_calibrate(args: argparse.Namespace) -> None:
    from reglens.ingest.download import load_lock
    from reglens.ingest.tokens import calibrate, file_text
    from reglens.llm.provider import get_provider

    cfg = load_config(args.config)
    lock = load_lock()
    if not lock:
        raise SystemExit("Nothing downloaded yet — run `reglens download` first.")
    rec = lock[args.source] if args.source else next(iter(lock.values()))
    text = file_text(PROJECT_ROOT / rec["file"])
    sample = text[len(text) // 3 : len(text) // 3 + args.chars]
    ratio = calibrate(get_provider(cfg), sample, tier=args.tier)
    model = cfg.model(args.tier)
    print(f"{rec['celex']}: {ratio:.3f} chars/token on {len(sample):,} chars ({model})")
    print("Set tokens.chars_per_token in config.yaml to this value.")


def _cmd_parse(args: argparse.Namespace) -> None:
    from reglens.ingest.chunks import build_chunks, write_chunks
    from reglens.ingest.download import load_lock
    from reglens.ingest.eurlex import parse_xhtml

    cfg = load_config(args.config)
    lock = load_lock()
    print(f"{'source':<26}{'units':>7}{'chunks':>8}{'~tokens':>10}{'max':>7}")
    for s in load_sources():
        rec = lock.get(s.id)
        if not rec or (args.source and s.id not in args.source):
            continue
        path = PROJECT_ROOT / rec["file"]
        if s.format == "eba-qa":
            from reglens.ingest.eba_qa import load_qas, qa_units

            units = qa_units(load_qas(path))
        elif path.suffix == ".xhtml":
            base = s.celex if s.celex and s.celex.startswith("3") else None
            base = base or ("3" + s.celex[1:] if s.consolidated and s.celex else None)
            units = parse_xhtml(path, base_celex=base, chars_per_token=cfg.chars_per_token)
        else:
            from reglens.ingest.pdf import parse_markdown, pdf_to_markdown

            md = pdf_to_markdown(s.id, path)  # cached Docling output
            units = parse_markdown(md, parts=s.parts, blocks_include=s.blocks)
        chunks = build_chunks(
            s, units, version=rec["celex"] or rec["retrieved"], chars_per_token=cfg.chars_per_token
        )
        write_chunks(s.id, chunks)
        toks = [len(c.text) / cfg.chars_per_token for c in chunks]
        print(f"{s.id:<26}{len(units):>7}{len(chunks):>8}{int(sum(toks)):>10,}{int(max(toks)):>7}")


def _cmd_index(args: argparse.Namespace) -> None:
    from reglens.index import db
    from reglens.ingest.chunks import load_chunks
    from reglens.ingest.xrefs import build_edges, write_edges

    chunks = load_chunks()
    conn = db.connect()
    db.init_schema(conn)
    n = db.upsert_chunks(conn, chunks)
    for sid in {c.source_id for c in chunks}:
        db.delete_missing(conn, sid, {c.id for c in chunks if c.source_id == sid})
    edges = build_edges(chunks)
    write_edges(edges)
    db.replace_edges(conn, edges)
    print(f"{n} chunks upserted, {len(edges)} edges")
    if args.no_embed:
        return

    from reglens.index.embed import embed

    have = db.existing_hashes(conn)
    todo = [c for c in chunks if not have.get(c.id, ("", False))[1]]
    print(f"embedding {len(todo)} chunks (local BGE-M3, no token cost)")
    batch = 256
    for i in range(0, len(todo), batch):
        part = todo[i : i + batch]
        vectors = embed([c.text for c in part])
        db.set_embeddings(conn, list(zip([c.id for c in part], vectors, strict=True)))
        print(f"  {min(i + batch, len(todo))}/{len(todo)}", flush=True)


def _cmd_search(args: argparse.Namespace) -> None:
    from reglens.index import db
    from reglens.retrieve.search import Filters, search

    hits = search(
        db.connect(),
        args.query,
        mode=args.mode,
        k=args.k,
        filters=Filters(source_ids=args.source, applies_to=args.applies_to),
    )
    for i, h in enumerate(hits, 1):
        print(f"{i:>2}. {h.score:7.3f}  {h.source_id}  {h.ref}  {(h.title or '')[:60]}")


def _cmd_eval_retrieval(args: argparse.Namespace) -> None:
    from reglens.eval.golden import load_golden
    from reglens.eval.retrieval import evaluate, save
    from reglens.index import db

    conn = db.connect()
    indexed = {r[0] for r in conn.execute("SELECT DISTINCT source_id FROM chunks").fetchall()}
    items = load_golden()
    results = [evaluate(conn, items, mode=m, k=10, indexed=indexed) for m in args.modes]
    print(f"{'mode':<8}{'items':>6}{'recall@5':>10}{'recall@10':>11}{'hit@10':>8}{'mrr@10':>8}")
    for r in results:
        print(
            f"{r['mode']:<8}{r['items']:>6}{r['recall@5']:>10}{r['recall@10']:>11}"
            f"{r['hit@10']:>8}{r['mrr@10']:>8}"
        )
    if results and results[0]["skipped_not_evaluable"]:
        print(
            "not evaluable (no indexed source/ref): "
            + ", ".join(results[0]["skipped_not_evaluable"])
        )
    print(f"details: {save(results)}")


def _cmd_golden(args: argparse.Namespace) -> None:
    from collections import Counter

    from reglens.eval.golden import load_golden

    items = load_golden()
    print(f"{len(items)} items valid")
    for name, key in [("type", "type"), ("status", "status"), ("topic", "topic")]:
        counts = Counter(getattr(i, key) for i in items)
        print(f"  {name:<8}" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="reglens")
    parser.add_argument("--config", help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    usage = sub.add_parser("usage", aliases=["cost"], help="summarise token usage from the ledger")
    usage.add_argument("--by", choices=["phase", "model", "purpose"], default="phase")
    usage.set_defaults(func=_cmd_usage)

    est = sub.add_parser("estimate", help="estimate tokens (and API-eq cost) of a planned run")
    est.add_argument("--tier", choices=["bulk", "dev", "milestone"])
    est.add_argument("--model", help="explicit model ID (overrides --tier)")
    est.add_argument("--input", type=int, required=True, help="input tokens per call")
    est.add_argument("--output", type=int, required=True, help="output tokens per call")
    est.add_argument("--calls", type=int, default=1)
    est.add_argument("--batch", action="store_true", help="apply Batch API discount")
    est.set_defaults(func=_cmd_estimate)

    dl = sub.add_parser("download", help="download sources (EUR-Lex via CELLAR, others by URL)")
    dl.add_argument("--source", nargs="*", help="source ids (default: all with a CELEX number)")
    dl.add_argument("--as-of", help="YYYY-MM-DD; consolidated version in force on this date")
    dl.add_argument("--force", action="store_true", help="re-download even if present")
    dl.set_defaults(func=_cmd_download)

    tok = sub.add_parser("tokens", help="estimate tokens of downloaded documents (no LLM calls)")
    tok.set_defaults(func=_cmd_tokens)

    cal = sub.add_parser("calibrate", help="measure chars/token with two small LLM calls")
    cal.add_argument("--source", help="source id to sample from")
    cal.add_argument("--chars", type=int, default=8000, help="sample size in characters")
    cal.add_argument("--tier", choices=["bulk", "dev", "milestone"], default="bulk")
    cal.set_defaults(func=_cmd_calibrate)

    prs = sub.add_parser("parse", help="parse downloaded sources into chunks (no LLM calls)")
    prs.add_argument("--source", nargs="*", help="source ids (default: all downloaded)")
    prs.set_defaults(func=_cmd_parse)

    idx = sub.add_parser("index", help="load chunks + edges into Postgres and embed new chunks")
    idx.add_argument("--no-embed", action="store_true", help="skip embedding")
    idx.set_defaults(func=_cmd_index)

    srch = sub.add_parser("search", help="search the index (no LLM calls)")
    srch.add_argument("query")
    srch.add_argument("--mode", choices=["bm25", "dense", "hybrid", "rerank"], default="rerank")
    srch.add_argument("--k", type=int, default=10)
    srch.add_argument("--source", nargs="*")
    srch.add_argument("--applies-to", choices=["SI", "LSI"])
    srch.set_defaults(func=_cmd_search)

    evr = sub.add_parser(
        "eval-retrieval", help="retrieval metrics on the golden set (no LLM calls)"
    )
    evr.add_argument("--modes", nargs="*", default=["bm25", "dense", "hybrid", "rerank"])
    evr.set_defaults(func=_cmd_eval_retrieval)

    gold = sub.add_parser("golden", help="validate the golden eval set and show its mix")
    gold.set_defaults(func=_cmd_golden)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
