"use client";

import { useEffect, useRef, useState } from "react";
import { KeyRound, Send, Square } from "lucide-react";
import { ask, getMeta, type Access, type AnswerPayload, type Meta, type Mode, type ProgressEvent } from "@/lib/api";
import { AnswerView } from "@/components/ask/answer-view";
import { ProgressTimeline } from "@/components/ask/progress-timeline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/** A radio group (WAI-ARIA pattern): one tab stop, arrow keys move and select. */
function Segmented<T extends string>({
  value,
  options,
  onChange,
  disabled,
  label,
}: {
  value: T;
  options: { value: T; label: string; hint?: string }[];
  onChange: (v: T) => void;
  disabled?: boolean;
  label: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (from: number, step: number) => {
    const next = (from + step + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  return (
    <div className="inline-flex rounded-lg bg-muted p-[3px]" role="radiogroup" aria-label={label}>
      {options.map((o, i) => (
        <button
          key={o.value}
          ref={(el) => {
            refs.current[i] = el;
          }}
          role="radio"
          aria-checked={value === o.value}
          aria-label={o.label}
          tabIndex={value === o.value ? 0 : -1}
          title={o.hint}
          disabled={disabled}
          onClick={() => onChange(o.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" || e.key === "ArrowDown") {
              e.preventDefault();
              move(i, 1);
            } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
              e.preventDefault();
              move(i, -1);
            }
          }}
          className={`rounded-md px-3 py-1 text-sm transition-colors disabled:opacity-50 ${
            value === o.value ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: "auto", label: "Auto", hint: "A small model decides whether the question needs several provisions" },
  { value: "single", label: "Quick", hint: "One retrieval pass and one cited answer (~6k tokens)" },
  { value: "agent", label: "Deep", hint: "The research agent follows references and reads definitions (40–90k tokens)" },
];

export function AskView() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [access, setAccess] = useState<Access>("api");
  const [apiKey, setApiKey] = useState(""); // memory only: never stored, gone on reload
  const [mode, setMode] = useState<Mode>("auto");
  const [applies, setApplies] = useState<"any" | "SI" | "LSI">("any");
  const [legalDate, setLegalDate] = useState("");
  const [approach, setApproach] = useState("");
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState(0);
  const [result, setResult] = useState<AnswerPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const [metaTry, setMetaTry] = useState(0);
  useEffect(() => {
    getMeta()
      .then((m) => {
        setMeta(m);
        setMetaError(null);
        if (m.access.includes("subscription")) setAccess("subscription");
      })
      .catch(() => setMetaError("The RegLens API is not reachable. Start it with: uv run uvicorn reglens.api.app:app --port 8000"));
  }, [metaTry]);

  const canAsk = question.trim().length >= 3 && !running && (access === "subscription" || apiKey.trim());

  async function submit() {
    if (!canAsk) return;
    abort.current = new AbortController();
    setRunning(true);
    setRunId((n) => n + 1);
    setEvents([]);
    setResult(null);
    setError(null);
    setAsked(question.trim());
    try {
      const r = await ask(
        { question: question.trim(), mode, access, applies_to: applies !== "any" ? applies : null, as_of: legalDate || null, conditions: approach ? { approach: [approach] } : {} },
        access === "api" ? apiKey.trim() : null,
        (e) => setEvents((prev) => [...prev, e]),
        abort.current.signal,
      );
      setResult(r);
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Ask EU credit risk regulation</h1>
        <p className="text-sm text-muted-foreground">
          CRR including CRR3, RTS, EBA guidelines and Q&amp;A, the ECB guide to internal models. Every claim cites its
          article or paragraph and is labelled law, supervisory expectation or interpretation.
        </p>
      </section>

      {metaError && (
        <p className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/40 px-3 py-2 text-sm text-destructive" role="alert">
          {metaError}
          <Button size="sm" variant="outline" onClick={() => setMetaTry((n) => n + 1)}>
            Retry
          </Button>
        </p>
      )}

      <section className="grid gap-4 rounded-lg border p-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label>Call Claude with</Label>
          <Segmented
            label="Call Claude with"
            value={access}
            onChange={setAccess}
            disabled={running}
            options={[
              { value: "api" as Access, label: "Your API key" },
              ...(meta?.access.includes("subscription")
                ? [{ value: "subscription" as Access, label: "Local subscription" }]
                : []),
            ]}
          />
          {access === "api" && (
            <div className="relative">
              <KeyRound className="absolute top-2 left-2.5 size-4 text-muted-foreground" />
              <Input
                type="password"
                autoComplete="off"
                placeholder="sk-ant-…"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="pl-8"
                aria-label="Anthropic API key"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Kept in this tab&apos;s memory only. Sent with each question to your local RegLens API, which passes it to the Anthropic API and nowhere else. Never stored or logged.
              </p>
            </div>
          )}
        </div>
        <div className="space-y-2">
          <Label>Answering</Label>
          <Segmented label="Answering" value={mode} onChange={setMode} options={MODES} disabled={running} />
          <p className="text-xs text-muted-foreground">{MODES.find((m) => m.value === mode)?.hint}</p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
              <label className="text-xs">Legal application date <input aria-label="Legal application date" type="date" value={legalDate} disabled={running} onChange={(e) => setLegalDate(e.target.value)} className="rounded border p-1" /></label>
              <label className="text-xs">Approach <select aria-label="Approach" value={approach} disabled={running} onChange={(e) => setApproach(e.target.value)} className="rounded border p-1"><option value="">Any</option><option value="SA">SA</option><option value="IRB">IRB</option></select></label>
              <Label className="text-xs">Institution type</Label>
              <Segmented
                label="Institution type"
                value={applies}
                onChange={setApplies}
                disabled={running}
                options={[
                  { value: "any" as const, label: "Any" },
                  { value: "SI" as const, label: "SI" },
                  { value: "LSI" as const, label: "LSI" },
                ]}
              />
            </div>
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {meta?.examples.map((q) => (
            <button
              key={q}
              onClick={() => setQuestion(q)}
              disabled={running}
              className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit();
          }}
          placeholder="e.g. Which LGD input floors apply to retail exposures secured by residential property?"
          rows={3}
          aria-label="Your question"
        />
        <div className="flex items-center gap-2">
          <Button onClick={submit} disabled={!canAsk}>
            <Send className="size-4" /> Ask
          </Button>
          {running && (
            <Button variant="outline" onClick={() => abort.current?.abort()}>
              <Square className="size-4" /> Stop
            </Button>
          )}
          <span className="text-xs text-muted-foreground">Ctrl + Enter</span>
        </div>
      </section>

      {(running || events.length > 0 || result || error) && (
        <section className="space-y-4">
          <h2 className="text-base font-semibold">{asked}</h2>
          <ProgressTimeline key={runId} events={events} running={running} />
          {error && <p className="rounded-lg border border-destructive/40 px-3 py-2 text-sm text-destructive">{error}</p>}
          {result && <AnswerView result={result} />}
        </section>
      )}
    </div>
  );
}
