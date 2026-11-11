"""Command line: usage, estimate, download, tokens, calibrate."""

from __future__ import annotations

import argparse
from datetime import date, datetime

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
    from reglens.ingest.pdf import file_sha256

    cfg = load_config(args.config)
    lock = load_lock()
    failed: list[str] = []
    print(f"{'source':<26}{'units':>7}{'chunks':>8}{'~tokens':>10}{'max':>7}")
    for s in load_sources():
        rec = lock.get(s.id)
        if not rec or (args.source and s.id not in args.source):
            continue
        path = PROJECT_ROOT / rec["file"]
        digest = file_sha256(path)
        if digest != rec.get("sha256"):  # text must come from the locked, recorded download
            print(f"{s.id:<26}SKIPPED: file does not match sources.lock.json (re-download)")
            failed.append(s.id)
            continue
        if s.format == "eba-qa":
            from reglens.ingest.eba_qa import load_qas, qa_units

            units = qa_units(load_qas(path))
        elif path.suffix == ".xhtml":
            base = s.celex if s.celex and s.celex.startswith("3") else None
            base = base or ("3" + s.celex[1:] if s.consolidated and s.celex else None)
            units = parse_xhtml(path, base_celex=base, chars_per_token=cfg.chars_per_token)
        else:
            from reglens.ingest.pdf import parse_markdown, pdf_to_markdown

            md = pdf_to_markdown(s.id, path, force=args.force)  # cached per PDF digest
            units = parse_markdown(md, parts=s.parts, blocks_include=s.blocks)
        chunks = build_chunks(
            s,
            units,
            version=rec["celex"] or rec["retrieved"],
            chars_per_token=cfg.chars_per_token,
            source_sha256=digest,
        )
        write_chunks(s.id, chunks)
        toks = [len(c.text) / cfg.chars_per_token for c in chunks]
        print(f"{s.id:<26}{len(units):>7}{len(chunks):>8}{int(sum(toks)):>10,}{int(max(toks)):>7}")
    if failed:
        raise SystemExit(f"not parsed (raw file differs from the lock): {', '.join(failed)}")


def _cmd_index(args: argparse.Namespace) -> None:
    from reglens.index import db, generations
    from reglens.index.embed import model_identity
    from reglens.ingest.chunks import load_chunks
    from reglens.ingest.xrefs import build_edges

    chunks = load_chunks()
    conn = db.connect()
    gid = generations.begin(conn, model_identity())
    n = db.upsert_chunks(conn, chunks)
    edges = build_edges(chunks)
    db.replace_edges(conn, edges)
    reused = generations.reuse_vectors(conn)
    print(f"Generation {gid}: {n} chunks, {len(edges)} edges, {reused} vectors reused")
    if args.no_embed:
        print("Staged only; not published. Active readers are unchanged.")
        conn.close()
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
    print("Published:", generations.publish(conn, gid))
    conn.close()


def _cmd_corpus(args: argparse.Namespace) -> None:
    from reglens.index import db, generations

    with db.connect() as conn:
        generations.install(conn)
        if args.publish:
            print(generations.publish(conn, args.publish, expected_head=generations.active(conn)))
        elif args.rollback:
            row = conn.execute("SELECT state FROM public.corpus_generations WHERE id=%s",
                               (args.rollback,)).fetchone()
            if not row or row[0] != "ready":
                raise SystemExit("Rollback target must be a previously published snapshot")
            print(generations.publish(conn, args.rollback, expected_head=generations.active(conn)))
        else:
            import json

            print(json.dumps(generations.list_generations(conn), indent=2))


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


def _cmd_ask(args: argparse.Namespace) -> None:
    import json

    from reglens.answer.pipeline import answer_question, render
    from reglens.answer.verify import check_answer
    from reglens.index import db
    from reglens.llm.provider import get_provider

    cfg = load_config(args.config)
    if args.route:
        from reglens.answer.route import answer_routed

        ans = answer_routed(db.connect(), get_provider(cfg), cfg, args.question)
    elif args.agent:
        from reglens.agent.run import answer_agentic

        ans = answer_agentic(db.connect(), get_provider(cfg), cfg, args.question)
    else:
        ans = answer_question(db.connect(), get_provider(cfg), cfg, args.question)
    summary = check_answer(ans)
    if args.json:
        print(json.dumps(ans.to_dict() | {"check": summary}, indent=2, ensure_ascii=False))
        return
    print(render(ans))
    if ans.usage_tokens:
        print(f"\n[{ans.model}, {ans.usage_tokens:,} tokens; citation check {summary}]")


def _golden_items(args: argparse.Namespace) -> list:
    from reglens.eval.golden import GOLDEN_DIR, load_golden

    paths = [GOLDEN_DIR / f"{args.set}.jsonl"] if args.set != "all" else None
    items = [i for i in load_golden(paths) if i.status == "verified"]
    if getattr(args, "type", None):
        items = [i for i in items if i.type == args.type]
    if getattr(args, "id", None):
        ids = set(args.id.split(","))
        items = [i for i in items if i.id in ids]
    return items[: getattr(args, "limit", None) or None]


def _set_repeat(args: argparse.Namespace) -> None:
    if getattr(args, "repeat", None):
        import os

        os.environ["REGLENS_REPEAT"] = str(args.repeat)


def _cmd_eval_answers(args: argparse.Namespace) -> None:
    _set_repeat(args)
    from reglens.eval.answers import ANSWER_DIR, answer_version, artifact_name, run
    from reglens.index import db

    cfg = load_config(args.config)
    conn = db.connect()  # the corpus generation is part of the cache identity
    items = _golden_items(args)
    routes = None
    if args.route:
        from reglens.eval.route import cached_routes

        routes = cached_routes(items)
        if missing := [i.id for i in items if i.id not in routes]:
            print(f"No current route for {', '.join(missing)}: run `reglens eval-route` first.")
            return

    def mode(item) -> bool:
        return routes[item.id]["route"] == "agent" if routes is not None else args.agent

    dirs = {m: ANSWER_DIR / answer_version(cfg, conn, bool(m)) for m in (0, 1)}
    todo = [i for i in items if not (dirs[mode(i)] / artifact_name(i)).exists()]
    per_call = args.tokens_per_call
    est = len(todo) * per_call
    if routes is not None:
        n_agent = sum(mode(i) for i in todo)
        est = n_agent * args.agent_tokens_per_call + (len(todo) - n_agent) * per_call
        print(f"routed: {n_agent} new agent calls, {len(todo) - n_agent} new single-pass calls")
    model = cfg.model((cfg.answer or {}).get("tier", "dev"))
    print(
        f"{len(items)} items ({len(items) - len(todo)} cached), {len(todo)} new LLM calls on "
        f"{model}: ~{est:,} tokens (at ~{per_call:,}/call)"
    )
    if est > cfg.budget.approval_threshold_tokens:
        print(f"Above {cfg.budget.approval_threshold_tokens:,} tokens — needs explicit approval.")
    if not args.yes:
        print("Dry run. Re-run with --yes to call the model.")
        return

    from reglens.llm.provider import get_provider

    s = run(
        conn,
        get_provider(cfg),
        cfg,
        items,
        log=lambda m: print(m, flush=True),
        agent=args.agent,
        routes=routes,
        label=args.set,
    )
    print(
        f"\nrun {s['run_id']}\n"
        f"scope compliance {s['scope_compliance']}  "
        f"abstain on out-of-scope {s['abstain_on_out_of_scope']}  "
        f"answered in-scope {s['answered_in_scope']}  citation recall {s['citation_recall']}  "
        f"mechanical checks passed {s['check_pass_rate']}  avg tokens {s['avg_tokens']:,}  "
        f"new tokens {s['new_tokens_this_run']:,}"
    )
    misses = [r for r in s["per_item"] if not r["abstain_correct"]]
    for r in misses:
        print(f"  abstention wrong: {r['id']} ({r['type']}, abstained={r['abstained']})")
    if s["errors"]:
        print(f"  with errors: {', '.join(s['errors'])}")
    if s["reports_incomplete"]:
        print(f"  answers reporting missing information: {', '.join(s['reports_incomplete'])}")
    print(f"manifest: {s['file']}  (grade it with: reglens judge --run {s['run_id']})")


def _cmd_eval_route(args: argparse.Namespace) -> None:
    from reglens.eval.route import cached_routes, run

    cfg = load_config(args.config)
    items = _golden_items(args)
    cached = cached_routes(items)
    todo = [i for i in items if i.id not in cached]
    est = len(todo) * args.tokens_per_call
    print(
        f"{len(items)} items ({len(items) - len(todo)} cached), {len(todo)} router calls on "
        f"{cfg.model('bulk')}: ~{est:,} tokens (at ~{args.tokens_per_call:,}/call)"
    )
    if not args.yes:
        print("Dry run. Re-run with --yes to call the model.")
        return

    from reglens.llm.provider import get_provider

    s = run(get_provider(cfg), items, log=lambda m: print(m, flush=True))
    print(
        f"\naccuracy {s['accuracy']}  agent recall {s['agent_recall']}  "
        f"agent precision {s['agent_precision']}  confusion {s['confusion']}  "
        f"new tokens {s['new_tokens_this_run']:,}"
    )
    for m in s["misrouted"]:
        print(f"  misrouted: {m['id']} ({m['type']}) -> {m['route']}: {m['reason']}")
    print(f"details: {s['path']}")


def _cmd_register(args: argparse.Namespace) -> None:
    from collections import Counter

    from reglens.gap import register as reg
    from reglens.index import db

    if args.migrate_ids:
        items = reg.load_register()
        reg.assign_ids(items)
        reg.write_register(items)
        import json

        manifest = (json.loads(reg.MANIFEST_FILE.read_text(encoding="utf-8"))
                    if reg.MANIFEST_FILE.exists() else {})
        manifest["id_scheme"] = "content-sha256-v1"
        reg.MANIFEST_FILE.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Migrated {len(items)} obligations to stable ids; legacy aliases retained")
        return
    cfg = load_config(args.config)
    conn = db.connect()
    todo = reg.batches(reg.select_passages(conn))[: args.limit]
    model = cfg.model(reg.EXTRACT_TIER)
    cached = {p.stem for p in (reg.BATCH_DIR / reg.REGISTER_VERSION).glob("*.json")}
    new = [b for b in todo if reg.batch_id(b, model) not in cached]
    text = sum(len(p.text) for b in new for p in b) / reg.CHARS_PER_TOKEN
    est = int(text + len(new) * args.overhead_tokens)
    print(
        f"{sum(len(b) for b in todo)} passages in {len(todo)} batches ({len(todo) - len(new)} "
        f"cached); {len(new)} calls on {cfg.model(reg.EXTRACT_TIER)}: ~{est:,} tokens "
        f"(passage text + ~{args.overhead_tokens:,}/call for prompt, output and thinking)"
    )
    if est > cfg.budget.approval_threshold_tokens:
        print(f"Above {cfg.budget.approval_threshold_tokens:,} tokens — needs explicit approval.")
    if not args.yes:
        print("Dry run. Re-run with --yes to call the model.")
        return

    from reglens.llm.provider import get_provider

    obligations, tokens = reg.extract(
        conn, get_provider(cfg), model=model, limit=args.limit, log=lambda m: print(m, flush=True)
    )
    path = reg.REGISTER_FILE if args.limit is None else reg.BATCH_DIR / "sample.jsonl"
    reg.write_register(obligations, path)
    if args.limit is None:
        reg.write_manifest(conn, model, obligations)
    bad = [o.id for o in obligations if not o.quote_ok]
    print(f"\n{len(obligations)} obligations, new tokens {tokens:,}; written to {path}")
    print("by source:", dict(Counter(o.source_id for o in obligations)))
    print("by topic:", dict(Counter(o.topic for o in obligations).most_common()))
    print(f"quotes not found verbatim: {len(bad)} {bad[:10]}")


def _cmd_gap(args: argparse.Namespace) -> None:
    from pathlib import Path

    from reglens.gap import match as m
    from reglens.gap.evaluate import evaluate, save
    from reglens.gap.gaps import POLICY_FILE, load_gaps
    from reglens.gap.policy import load_policy
    from reglens.gap.register import load_register

    cfg = load_config(args.config)
    obligations = load_register()
    clauses = load_policy(Path(args.policy) if args.policy else POLICY_FILE)
    if args.rescore:
        _rescore_gap_run(args.rescore, obligations, clauses)
        return
    todo = m.batches(obligations)[: args.limit]
    cached = {p.stem for p in (m.MATCH_DIR / m.MATCH_VERSION).glob("*.json")}
    model = cfg.model(m.MATCH_TIER)
    new = [b for b in todo if m.batch_id(b, m.system_prompt(m.select_clauses(b, clauses)[0]),
                                       model) not in cached]
    est = len(new) * args.tokens_per_call
    print(
        f"{len(clauses)} policy clauses; {sum(len(b) for b in todo)} obligations in {len(todo)} "
        f"batches ({len(todo) - len(new)} cached); {len(new)} calls on "
        f"{cfg.model(m.MATCH_TIER)}: ~{est:,} tokens (at ~{args.tokens_per_call:,}/call)"
    )
    if est > cfg.budget.approval_threshold_tokens:
        print(f"Above {cfg.budget.approval_threshold_tokens:,} tokens — needs explicit approval.")
    if not args.yes:
        print("Dry run. Re-run with --yes to call the model.")
        return

    from reglens.llm.provider import get_provider

    verdicts, tokens = m.match(
        get_provider(cfg), obligations, clauses, limit=args.limit,
        log=lambda s: print(s, flush=True),
    )
    s = evaluate(load_gaps(obligations), verdicts)
    js, cs = save(s, m.to_rows(verdicts, obligations))
    print(
        f"\nplanted-gap recall {s['recall']} ({s['gaps_assessed']} of {s['gaps']} gaps assessed)"
        f"  type accuracy {s['type_accuracy']}  by type {s['by_type']}"
    )
    print(f"statuses {s['statuses']}  other findings {s['other_findings']}  "
          f"quotes not verbatim {s['quotes_not_verbatim']}  new tokens {tokens:,}")
    for r in s["per_gap"]:
        if r["assessed"] and not r["found"]:
            print(f"  missed {r['id']} ({r['type']}): {r['statuses']}")
    print(f"details: {js}\ncoverage matrix: {cs}")


def _rescore_gap_run(run_id: str, obligations, clauses) -> None:
    """Re-validate a saved run's verdicts under the current rules; rewrites it (no LLM)."""
    import json

    from reglens.gap import match as m
    from reglens.gap.evaluate import evaluate, find_run
    from reglens.gap.gaps import load_gaps
    from reglens.gap.register import id_lookup

    run = find_run(None if run_id == "latest" else run_id)
    if run is None:
        raise SystemExit(f"no gap run '{run_id}'")
    data = json.loads(run["path"].read_text(encoding="utf-8"))
    lookup = id_lookup(obligations)
    by_id = {lookup[r["obligation_id"]].id: r for r in data["rows"]}
    verdicts = m.rescore(data["rows"], clauses)
    for v in verdicts:
        v.obligation_id = lookup[v.obligation_id].id
    rows = m.to_rows(verdicts, obligations)
    for r in rows:  # keep any reviewer columns already filled in
        old = by_id.get(r["obligation_id"], {})
        r["reviewer_status"] = old.get("reviewer_status", "")
        r["reviewer_comment"] = old.get("reviewer_comment", "")
    before = {k: data.get(k) for k in ("recall", "statuses", "quotes_not_verbatim")}
    s = evaluate(load_gaps(obligations), verdicts)
    out = s | {"rows": rows, "rescored": f"{datetime.now():%Y-%m-%d}", "before_rescore": before}
    run["path"].write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{run['label']}: recall {before['recall']} -> {s['recall']} "
          f"({s['gaps_assessed']}/{s['gaps']} gaps assessed)")
    print(f"statuses before {before['statuses']}\nstatuses after  {s['statuses']}")
    print(f"invalid verdicts {s['invalid_verdicts']}, quotes not verbatim "
          f"{s['quotes_not_verbatim']}; written to {run['path']}")


def _cmd_judge(args: argparse.Namespace) -> None:
    from reglens.eval.answers import load_run
    from reglens.eval.judge import judge, plan

    cfg = load_config(args.config)
    try:
        manifest = load_run(args.run)
    except FileNotFoundError as e:
        raise SystemExit(f"{e}" if args.run == "latest" else f"no run '{args.run}'") from None
    in_run = {e["id"] for e in manifest["items"]}
    args.set = "all"  # the run decides which items are graded; --type / --id narrow it
    items = [i for i in _golden_items(args) if i.id in in_run]
    p = plan(manifest, items, cfg.model("bulk"))
    est = len(p["needs_call"]) * args.tokens_per_call
    print(
        f"run {manifest['run_id']} ({manifest['kind']}): {len(items)} items, "
        f"{len(p['needs_call'])} judge calls on {cfg.model('bulk')} "
        f"(~{est:,} tokens at ~{args.tokens_per_call:,}/call), "
        f"{len(p['deterministic'])} scored without a call, {len(p['cached'])} cached"
    )
    for problem in p["problems"]:
        print(f"  cannot grade: {problem}")
    if est > cfg.budget.approval_threshold_tokens:
        print(f"Above {cfg.budget.approval_threshold_tokens:,} tokens — needs explicit approval.")
    if not args.yes:
        print("Dry run. Re-run with --yes to call the judge model.")
        return

    from reglens.llm.provider import get_provider

    s = judge(get_provider(cfg), cfg, manifest, items, log=lambda m: print(m, flush=True))
    print(
        f"\nrun {s['run_id']}: correctness (mean score/2): in-scope {s['correctness_in_scope']}  "
        f"single {s['correctness_single']}  multi-hop {s['correctness_multi_hop']}\n"
        f"fully correct {s['fully_correct']}, partly {s['partly_correct']}, wrong {s['wrong']}; "
        f"out of scope declined {s['out_of_scope_declined']}; new tokens {s['new_tokens']:,}"
    )
    if s["problems"]:
        print(f"  not graded: {'; '.join(s['problems'])}")
    for item_id, flags in s["inconsistent_verdicts"].items():
        print(f"  check by hand: {item_id}: {'; '.join(flags)}")
    for r in s["per_item"]:
        if r["score"] < 2 and r["type"] != "out_of_scope":
            print(f"  {r['id']:<10} {r['score']}  {r.get('rationale', '')[:150]}")
    print(f"details: {s['file']}")


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
    prs.add_argument("--force", action="store_true", help="re-run PDF conversion (Docling)")
    prs.set_defaults(func=_cmd_parse)

    idx = sub.add_parser("index", help="load chunks + edges into Postgres and embed new chunks")
    idx.add_argument("--no-embed", action="store_true", help="skip embedding")
    idx.set_defaults(func=_cmd_index)

    corpus = sub.add_parser("corpus", help="list, publish, or roll back corpus snapshots")
    action = corpus.add_mutually_exclusive_group()
    action.add_argument("--publish", help="publish a fully embedded, validated staged generation")
    action.add_argument("--rollback", help="activate a previously published generation")
    corpus.set_defaults(func=_cmd_corpus)

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

    ask = sub.add_parser("ask", help="answer a question with citations (one LLM call)")
    ask.add_argument("question")
    ask.add_argument("--json", action="store_true", help="print the full answer record")
    ask.add_argument("--agent", action="store_true",
                     help="agentic retrieval via the RegLens MCP tools (several tool calls)")
    ask.add_argument(
        "--route", action="store_true", help="let the Haiku router pick single-pass or agent"
    )
    ask.set_defaults(func=_cmd_ask)

    eva = sub.add_parser("eval-answers", help="answer-level eval on the golden set (LLM calls)")
    eva.add_argument(
        "--set", default="phase0", help="golden file stem (phase0 = smoke set) or 'all'"
    )
    eva.add_argument("--limit", type=int, help="first N items only")
    eva.add_argument("--tokens-per-call", type=int, default=6000, help="for the estimate")
    eva.add_argument("--yes", action="store_true", help="actually call the model")
    eva.add_argument("--agent", action="store_true", help="agentic answering (MCP tools)")
    eva.add_argument("--type", help="only this golden type, e.g. multi_hop")
    eva.add_argument("--id", help="only these golden ids, comma-separated")
    eva.add_argument("--repeat", type=int, help="repeat run N (>1): separate agent cache")
    eva.add_argument(
        "--route", action="store_true", help="per item, the mode chosen by the cached router"
    )
    eva.add_argument(
        "--agent-tokens-per-call", type=int, default=50000, help="for the routed estimate"
    )
    eva.set_defaults(func=_cmd_eval_answers)

    rte = sub.add_parser("eval-route", help="router accuracy: agent vs single-pass (bulk tier)")
    rte.add_argument("--set", default="phase0", help="golden file stem or 'all'")
    rte.add_argument("--tokens-per-call", type=int, default=1500, help="for the estimate")
    rte.add_argument("--yes", action="store_true", help="actually call the router model")
    rte.add_argument("--type", help="only this golden type")
    rte.add_argument("--id", help="only these golden ids, comma-separated")
    rte.set_defaults(func=_cmd_eval_route)

    jdg = sub.add_parser("judge", help="LLM judge of one eval run's answers (bulk tier, cached)")
    jdg.add_argument("--run", default="latest", help="run id from eval-answers (default: latest)")
    jdg.add_argument("--tokens-per-call", type=int, default=2000, help="for the estimate")
    jdg.add_argument("--yes", action="store_true", help="actually call the judge model")
    jdg.add_argument("--type", help="only this golden type, e.g. multi_hop")
    jdg.add_argument("--id", help="only these golden ids, comma-separated")
    jdg.set_defaults(func=_cmd_judge)

    rg = sub.add_parser("register", help="extract the obligation register (LLM calls)")
    rg.add_argument("--limit", type=int, help="first N batches only (a sample)")
    rg.add_argument("--overhead-tokens", type=int, default=4000, help="for the estimate")
    rg.add_argument("--yes", action="store_true", help="actually call the model")
    rg.add_argument("--migrate-ids", action="store_true",
                    help="assign stable IDs, retaining aliases; no LLM")
    rg.set_defaults(func=_cmd_register)

    gp = sub.add_parser("gap", help="policy gap analysis against the obligation register")
    gp.add_argument("--policy", help="policy Markdown file (default: the synthetic policy)")
    gp.add_argument("--limit", type=int, help="first N batches only (a sample)")
    gp.add_argument("--tokens-per-call", type=int, default=8500, help="for the estimate")
    gp.add_argument("--yes", action="store_true", help="actually call the model")
    gp.add_argument(
        "--rescore", metavar="RUN",
        help="re-validate a saved run ('demo', a gap-… id, or 'latest') under the current "
        "rules and rewrite it (no LLM calls)",
    )
    gp.set_defaults(func=_cmd_gap)

    gold = sub.add_parser("golden", help="validate the golden eval set and show its mix")
    gold.set_defaults(func=_cmd_golden)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
