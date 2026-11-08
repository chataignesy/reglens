"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { CheckCircle2, ChevronRight, CircleAlert, Download, XCircle } from "lucide-react";
import { exportUrl, getGap, getGapRuns, type GapResult, type GapRun } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const STATUS: Record<string, { label: string; cls: string }> = {
  covered: { label: "covered", cls: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200" },
  partial: { label: "partial", cls: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" },
  missing: { label: "missing", cls: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200" },
  contradicted: { label: "contradicted", cls: "bg-rose-200 text-rose-950 dark:bg-rose-900 dark:text-rose-100" },
  not_applicable: { label: "not applicable", cls: "bg-muted text-muted-foreground" },
  other_document: { label: "other document", cls: "bg-slate-100 text-slate-800 dark:bg-slate-900 dark:text-slate-200" },
  unassessed: { label: "unassessed", cls: "bg-muted text-muted-foreground" },
};
const FINDINGS = ["partial", "missing", "contradicted"];
const PAGE = 100;

function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, cls: "bg-muted" };
  return <Badge className={s.cls}>{s.label}</Badge>;
}

export function GapView() {
  const [data, setData] = useState<GapResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statuses, setStatuses] = useState<Set<string>>(new Set(FINDINGS));
  const [topic, setTopic] = useState("");
  const [text, setText] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const [runs, setRuns] = useState<GapRun[]>([]);
  const [run, setRun] = useState<string | undefined>(undefined);

  useEffect(() => {
    getGapRuns().then(setRuns).catch(() => setRuns([]));
  }, []);

  useEffect(() => {
    getGap(run)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError((e as Error).message));
  }, [run]);

  const rows = useMemo(() => {
    if (!data) return [];
    const q = text.trim().toLowerCase();
    return data.rows.filter(
      (r) =>
        statuses.has(r.status) &&
        (!topic || r.topic === topic) &&
        (!q || r.obligation.toLowerCase().includes(q) || r.source.toLowerCase().includes(q)),
    );
  }, [data, statuses, topic, text]);

  if (error) return <p className="rounded-lg border border-destructive/40 px-3 py-2 text-sm text-destructive">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Loading the coverage matrix…</p>;

  const counts = data.rows.reduce<Record<string, number>>((acc, r) => ((acc[r.status] = (acc[r.status] ?? 0) + 1), acc), {});
  const topics = [...new Set(data.rows.map((r) => r.topic))].sort();
  const toggleStatus = (s: string) =>
    setStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });

  return (
    <div className="space-y-6">
      <section className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Policy gap analysis</h1>
        <p className="text-sm text-muted-foreground">
          A <strong>synthetic</strong> Model Validation Policy of the fictitious RegLens Demo Bank, checked against{" "}
          {data.rows.length} obligations extracted from the CRR, RTS, EBA guidelines and the ECB guide. Each verdict cites
          the policy clause and quotes it; quotes are verified in code. A starting point for a reviewer, not a final
          judgement.
        </p>
        <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
          <label htmlFor="gap-run" className="text-muted-foreground">
            Run
          </label>
          <select
            id="gap-run"
            value={data.run_id}
            onChange={(e) => setRun(e.target.value)}
            className="h-7 rounded-md border bg-background px-2 text-xs"
          >
            {(runs.length ? runs : [{ id: data.run_id, label: data.run_label, is_demo: data.is_demo }]).map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
          {data.is_demo && <Badge variant="outline">demo data committed with the project</Badge>}
        </div>
      </section>

      <section className="grid grid-cols-3 gap-3 sm:grid-cols-7">
        {["covered", "partial", "missing", "contradicted", "other_document", "not_applicable", "unassessed"].map((s) => (
          <button
            key={s}
            onClick={() => toggleStatus(s)}
            className={`rounded-lg border p-3 text-left transition-colors ${statuses.has(s) ? "border-foreground/40 bg-muted/50" : "opacity-60 hover:opacity-100"}`}
            aria-pressed={statuses.has(s)}
            aria-label={`${counts[s] ?? 0} ${STATUS[s].label}: show or hide`}
          >
            <div className="text-2xl font-semibold tabular-nums">{counts[s] ?? 0}</div>
            <StatusBadge status={s} />
          </button>
        ))}
      </section>

      {data.recall !== null && (
        <Card>
          <CardContent className="space-y-3">
            <p className="text-sm">
              <strong>Planted gaps found: {Math.round(data.recall * 100)}%</strong> of {data.gaps} deliberately planted
              deficiencies ({Object.entries(data.by_type).map(([k, v]) => `${k} ${v}`).join(" · ")}); flag type correct{" "}
              {data.type_accuracy !== null ? `${Math.round(data.type_accuracy * 100)}%` : "–"}.
            </p>
            {data.complete === false && (
              <p className="flex items-center gap-1.5 text-sm text-amber-700 dark:text-amber-400">
                <CircleAlert className="size-4" /> Incomplete run: only {data.gaps_assessed} of {data.gaps} planted gaps
                were assessed. Unassessed gaps count as not found.
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              Caveat: the planted gaps were found after one prompt revision on this same policy, so this is a tuned
              result, not an independent test. Of a 20-finding sample beyond the planted gaps, all were factually correct
              but about 11 belong in a validation policy.
            </p>
            <div className="flex flex-wrap gap-2">
              {data.per_gap.map((g) => (
                <span key={g.id} title={Object.entries(g.statuses).map(([o, s]) => `${o}: ${s}`).join(", ")}
                  className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs">
                  {g.found ? <CheckCircle2 className="size-3.5 text-emerald-600" /> : <XCircle className="size-3.5 text-red-600" />}
                  {g.id} <span className="text-muted-foreground">{g.type}</span>
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <section className="flex flex-wrap items-center gap-3">
        <select
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          className="h-8 rounded-lg border bg-background px-2 text-sm"
          aria-label="Topic"
        >
          <option value="">All topics</option>
          {topics.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Search obligations, e.g. internal audit"
          aria-label="Search obligations"
          className="h-8 w-64"
        />
        <span className="text-xs text-muted-foreground">
          {rows.length} of {data.rows.length} obligations
        </span>
        <span className="ml-auto flex gap-2">
          <a href={exportUrl("csv", data.run_id)} className="inline-flex h-8 items-center gap-1 rounded-lg border px-2.5 text-sm hover:bg-muted">
            <Download className="size-4" /> CSV
          </a>
          <a href={exportUrl("xlsx", data.run_id)} className="inline-flex h-8 items-center gap-1 rounded-lg border px-2.5 text-sm hover:bg-muted">
            <Download className="size-4" /> Excel (with reviewer columns)
          </a>
        </span>
      </section>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead className="w-28">Status</TableHead>
              <TableHead>Obligation</TableHead>
              <TableHead className="w-48">Source</TableHead>
              <TableHead className="w-24">Policy</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.slice(0, limit).map((r) => (
              <Fragment key={r.obligation_id}>
                <TableRow
                  className="cursor-pointer"
                  tabIndex={0}
                  aria-expanded={open === r.obligation_id}
                  onClick={() => setOpen(open === r.obligation_id ? null : r.obligation_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setOpen(open === r.obligation_id ? null : r.obligation_id);
                    }
                  }}
                >
                  <TableCell>
                    <ChevronRight className={`size-4 transition-transform ${open === r.obligation_id ? "rotate-90" : ""}`} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={r.status} />
                  </TableCell>
                  <TableCell className="whitespace-normal">{r.obligation}</TableCell>
                  <TableCell className="whitespace-normal text-xs text-muted-foreground">{r.source}</TableCell>
                  <TableCell className="text-xs">{r.clauses.join(", ") || "–"}</TableCell>
                </TableRow>
                {open === r.obligation_id && (
                  <TableRow className="bg-muted/30 hover:bg-muted/30">
                    <TableCell />
                    <TableCell colSpan={4} className="space-y-1 whitespace-normal py-3 text-sm">
                      <p>
                        <span className="font-medium">Why: </span>
                        {r.rationale}
                      </p>
                      {r.quote && (
                        <p className="text-muted-foreground">
                          <span className="font-medium text-foreground">Policy text: </span>“{r.quote}”
                          {(r.evidence === "not_verbatim" || (!r.evidence && !r.quote_ok)) &&
                            " (quote not found verbatim in the cited clauses: check it)"}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        {r.obligation_id} · topic {r.topic} · {r.actor}
                      </p>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="py-6 text-center text-sm text-muted-foreground">
                  No obligations match these filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      {rows.length > limit && (
        <button onClick={() => setLimit(limit + PAGE)} className="text-sm text-primary underline-offset-4 hover:underline">
          Show {Math.min(PAGE, rows.length - limit)} more
        </button>
      )}
      <p className="text-xs text-muted-foreground">
        Results: {data.run_label} ({data.file})
      </p>
    </div>
  );
}
