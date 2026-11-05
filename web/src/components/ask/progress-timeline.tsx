"use client";

import { useEffect, useState } from "react";
import { Bot, BookOpen, FileSearch, GitBranch, Loader2, PenLine, Search, Undo2 } from "lucide-react";
import type { ProgressEvent } from "@/lib/api";

const short = (v: unknown, n = 60) => {
  const s = String(v ?? "");
  return s.length > n ? `${s.slice(0, n)}…` : s;
};

/** A tool call in words, e.g. get_article(["CRR", "178", null]) -> "Read CRR Art. 178". */
export function stepLabel(tool: string, args: unknown[]): string {
  const [a, b, c] = args ?? [];
  switch (tool) {
    case "search":
      return `Searched: "${short(a)}"${c ? ` in ${c}` : ""}`;
    case "get_article":
      return `Read ${a} Art. ${b}${c ? `(${c})` : ""}`;
    case "get_passage":
      return `Read in full: ${short(a, 70)}`;
    case "follow_reference":
      return `Followed the references of ${short(a, 70)}`;
    case "get_definition":
      return `Looked up the definition of "${a}"`;
    case "get_qa":
      return `Checked EBA Q&As on CRR Art. ${a}${b ? ` ("${short(b, 40)}")` : ""}`;
    default:
      return tool;
  }
}

function describe(e: ProgressEvent): { icon: React.ReactNode; text: string } {
  switch (e.stage) {
    case "retrieved":
      return {
        icon: <Search className="size-4" />,
        text: `Searched the corpus: ${e.passages} passages${
          Array.isArray(e.refs) && e.refs.length ? ` (top: ${(e.refs as string[]).join(", ")})` : ""
        }`,
      };
    case "routing":
      return { icon: <GitBranch className="size-4" />, text: "Deciding: quick answer or research agent" };
    case "routed":
      return {
        icon: <GitBranch className="size-4" />,
        text:
          e.route === "agent"
            ? `Needs several provisions: research agent (${short(e.reason, 90)})`
            : `One lookup is enough: quick answer (${short(e.reason, 90)})`,
      };
    case "drafting":
      return { icon: <PenLine className="size-4" />, text: "Drafting a cited answer" };
    case "agent":
      return { icon: <Bot className="size-4" />, text: `Research agent started (up to ${e.max_calls} tool calls)` };
    case "agent_failed":
      return {
        icon: <Undo2 className="size-4" />,
        text: "The research agent reached its cost cap without an answer: answering in a single pass instead",
      };
    case "fallback":
      return {
        icon: <Undo2 className="size-4" />,
        text: "The quick answer lacked information: handing over to the research agent",
      };
    case "tool": {
      const keys = Array.isArray(e.keys) ? e.keys.length : 0;
      const icon = e.tool === "search" ? <FileSearch className="size-4" /> : <BookOpen className="size-4" />;
      return { icon, text: `${stepLabel(String(e.tool), (e.args as unknown[]) ?? [])} → ${keys} passages` };
    }
    default:
      return { icon: <Loader2 className="size-4" />, text: String(e.stage) };
  }
}

export function ProgressTimeline({ events, running }: { events: ProgressEvent[]; running: boolean }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running) return;
    const start = Date.now(); // remounted per question (key), so elapsed starts at 0
    const t = setInterval(() => setElapsed(Math.round((Date.now() - start) / 1000)), 500);
    return () => clearInterval(t);
  }, [running]);

  if (!running && events.length === 0) return null;
  return (
    <div className="rounded-lg border bg-muted/30 px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        {running && <Loader2 className="size-4 animate-spin" />}
        {running ? "Working" : "Done"}
        {running && <span className="ml-auto font-mono text-xs text-muted-foreground">{elapsed}s</span>}
      </div>
      <ol className="space-y-1.5">
        {events.map((e, i) => {
          const { icon, text } = describe(e);
          return (
            <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-0.5 shrink-0 text-foreground">{icon}</span>
              <span>{text}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
