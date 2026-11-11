"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CheckCircle2, ChevronRight, CircleAlert, Route, Wrench } from "lucide-react";
import type { AnswerPayload, Source } from "@/lib/api";
import { KindBadge, LevelBadge } from "@/components/level-badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { stepLabel } from "@/components/ask/progress-timeline";

/** "[C2]" in the answer text becomes a Markdown link the renderer turns into a badge. */
const withCitationLinks = (text: string) => text.replace(/\[(C\d+|C\?)\]/g, "[$1](#cite-$1)");

function CitationBadge({ id, source, onOpen }: { id: string; source?: Source; onOpen: () => void }) {
  if (!source) {
    return (
      <span
        title="This citation did not match a passage: the claim is not backed by a verified source"
        className="mx-0.5 rounded bg-destructive/10 px-1 text-xs font-medium text-destructive"
      >
        ?
      </span>
    );
  }
  return (
    <Tooltip>
      <TooltipTrigger
        onClick={onOpen}
        className="mx-0.5 inline-flex cursor-pointer items-center rounded bg-primary/10 px-1 align-baseline text-xs font-semibold text-primary hover:bg-primary/20"
      >
        {id.replace("C", "")}
      </TooltipTrigger>
      <TooltipContent>
        {source.label} {source.ref} — {source.level}
      </TooltipContent>
    </Tooltip>
  );
}

function SourceItem({ source, open, onToggle }: { source: Source; open: boolean; onToggle: () => void }) {
  const [prefix, ...body] = source.text.split("\n");
  return (
    <li id={`src-${source.id}`} className="rounded-lg border">
      <button
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={`src-body-${source.id}`}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted/50"
      >
        <ChevronRight className={`size-4 shrink-0 transition-transform ${open ? "rotate-90" : ""}`} />
        <span className="font-semibold text-primary">{source.id.replace("C", "")}</span>
        <span className="font-medium">
          {source.label} {source.ref}
        </span>
        <span className="ml-auto">
          <LevelBadge levelKey={source.level_key} label={source.level} />
        </span>
      </button>
      {open && (
        <div id={`src-body-${source.id}`} className="border-t px-3 py-2 text-sm">
          <p className="mb-1 text-xs text-muted-foreground">{prefix}</p>
          <p className="whitespace-pre-line leading-relaxed">{body.join("\n")}</p>
          <p className="mt-2 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
            {source.version && <span>Text from the {source.version}.</span>}
            {source.url && (
              <a href={source.url} target="_blank" rel="noreferrer" className="text-primary underline-offset-4 hover:underline">
                Official text ↗
              </a>
            )}
            <span>RegLens shows extracted text: check the official source.</span>
          </p>
        </div>
      )}
    </li>
  );
}

export function AnswerView({ result }: { result: AnswerPayload }) {
  const [openSources, setOpenSources] = useState<Set<string>>(new Set());
  const byId = Object.fromEntries(result.sources.map((s) => [s.id, s]));
  const toggle = (id: string) =>
    setOpenSources((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const openAndScroll = (id: string) => {
    setOpenSources((prev) => new Set(prev).add(id));
    requestAnimationFrame(() =>
      document.getElementById(`src-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }),
    );
  };
  const allOk = result.check.ok === result.check.claims;

  if (result.unverified) {
    return (
      <Card className="border-amber-300 dark:border-amber-800">
        <CardContent className="flex gap-3 text-sm">
          <CircleAlert className="size-5 shrink-0 text-amber-600" />
          <div className="min-w-0 flex-1">
            <p className="font-medium">No verified answer</p>
            <p className="text-muted-foreground">
              The model&apos;s reply did not follow the required answer format, even after one retry, so
              its claims and citations could not be checked. Try asking again or rephrasing.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{result.errors.join("; ")}</p>
            {result.raw_output && (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs font-medium">
                  Show the unverified raw output (for diagnosis only, not an answer)
                </summary>
                <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs">
                  {result.raw_output}
                </pre>
              </details>
            )}
            <p className="mt-2 text-xs text-muted-foreground">{result.as_of}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (result.abstained || (result.errors.length > 0 && !result.answer)) {
    return (
      <Card className="border-amber-300 dark:border-amber-800">
        <CardContent className="flex gap-3 text-sm">
          <CircleAlert className="size-5 shrink-0 text-amber-600" />
          <div>
            <p className="font-medium">
              {result.abstained ? "Not answered from the RegLens corpus" : "No answer"}
            </p>
            <p className="text-muted-foreground">
              {result.abstain_reason || result.errors.join("; ")}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">{result.as_of}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent>
          <div className="text-sm leading-relaxed [&_li]:my-1 [&_p]:my-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_strong]:font-semibold">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  if (href?.startsWith("#cite-")) {
                    const id = href.slice(6);
                    return <CitationBadge id={id} source={byId[id]} onOpen={() => openAndScroll(id)} />;
                  }
                  return (
                    <a href={href} className="underline" target="_blank" rel="noreferrer">
                      {children}
                    </a>
                  );
                },
              }}
            >
              {withCitationLinks(result.answer)}
            </ReactMarkdown>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">{result.as_of}</p>
          {result.errors.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-amber-700 dark:text-amber-400">
              {result.errors.map((e, i) => (
                <li key={i} className="flex gap-1.5">
                  <CircleAlert className="mt-0.5 size-3.5 shrink-0" /> {e}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <ul className="space-y-1 text-xs" aria-label="Answer signals">
        <li className="flex items-center gap-1.5">
          <CheckCircle2 className="size-3.5 text-emerald-600" />
          <span>
            <span className="font-medium">Scope:</span> answered from the RegLens corpus (EU credit risk
            regulation). Questions outside it should be declined.
          </span>
        </li>
        <li className="flex items-center gap-1.5">
          {result.missing_info || result.partial_reads > 0 ? (
            <CircleAlert className="size-3.5 text-amber-600" />
          ) : (
            <CheckCircle2 className="size-3.5 text-emerald-600" />
          )}
          <span>
            <span className="font-medium">Completeness:</span>{" "}
            {result.partial_reads > 0
              ? `relies on ${result.partial_reads} passage(s) read only as truncated snippets; `
              : ""}
            {result.missing_info
              ? "the answer reports that information it needs is missing (see the text)."
              : result.partial_reads > 0
                ? "check those sources in full."
                : "no gaps reported. A judged completeness score exists only in the evaluation."}
          </span>
        </li>
        {(result.coverage?.temporal === "unknown" || result.coverage?.applicability === "unknown") && (
          <li className="text-amber-700">Requested date or applicability is not verified for every source. Check the official provisions before relying on this answer.</li>
        )}
        <li>Semantic evidence assessment: {result.semantic_review?.status === "model_assessed" ? "model assessment available; practitioner review still required" : "not performed"}.</li>
        {!!result.research?.unresolved?.length && <li className="text-amber-700">Research checks still unresolved: {result.research.unresolved.join(", ")}.</li>}
      </ul>

      {result.sources.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold">Sources</h3>
          <ul className="space-y-2">
            {result.sources.map((s) => (
              <SourceItem key={s.id} source={s} open={openSources.has(s.id)} onToggle={() => toggle(s.id)} />
            ))}
          </ul>
        </section>
      )}

      {result.claims.length > 0 && (
        <details className="rounded-lg border" open={!allOk}>
          <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
            {allOk ? (
              <CheckCircle2 className="size-4 text-emerald-600" />
            ) : (
              <CircleAlert className="size-4 text-amber-600" />
            )}
            Mechanical citation checks: {result.check.ok}/{result.check.claims} claims passed
          </summary>
          <p className="border-t px-3 pt-2 text-xs text-muted-foreground">
            Code checks that each claim cites a passage it was given, that its numbers appear in that
            passage, and that claims labelled law cite law. It does not check that the passage supports
            the meaning of the claim (conditions, negation, scope): read the sources.
          </p>
          <ul className="space-y-2 px-3 py-2 text-sm">
            {result.claims.map((c, i) => (
              <li key={i} className="flex items-start gap-2">
                {c.check === "ok" ? (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
                ) : (
                  <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" />
                )}
                <KindBadge kind={c.kind} />
                <span className="flex-1">
                  {c.text}{" "}
                  <span className="text-xs text-muted-foreground">
                    {c.citations.map((x) => x.replace("C", "")).join(", ")}
                    {c.check !== "ok" && ` — ${c.check}`}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {result.steps.length > 0 && (
        <details className="rounded-lg border">
          <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
            <Wrench className="size-4" /> Research steps: {result.steps.length} tool calls
          </summary>
          <ol className="space-y-1 border-t px-3 py-2 font-mono text-xs">
            {result.steps.map((s, i) => (
              <li key={i}>
                {i + 1}. {stepLabel(s.tool, s.args)} → {s.passages} passages
              </li>
            ))}
          </ol>
        </details>
      )}

      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        {result.route && <Route className="size-3.5" />}
        {result.route && `Answered by ${result.route.route === "agent" ? "the research agent" : "a quick single pass"} · `}
        {result.model} · {result.tokens.toLocaleString()} tokens
      </p>
    </div>
  );
}
