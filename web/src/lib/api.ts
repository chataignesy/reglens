// Client for the RegLens FastAPI backend (src/reglens/api/app.py).
// The browser calls the API directly: a streamed agent answer can take 20–90 s, longer than a
// dev-server proxy should be trusted to hold open.

export const API_URL = process.env.NEXT_PUBLIC_REGLENS_API ?? "http://localhost:8000";

export type Mode = "auto" | "single" | "agent";
export type Access = "api" | "subscription";

export interface Meta {
  disclaimer: string;
  examples: string[];
  access: Access[];
  model: string;
}

export interface Source {
  id: string; // "C2"
  label: string; // "CRR"
  ref: string; // "Art. 163(1)"
  level: string; // "law", "EBA guideline", ...
  level_key: string; // "L1", "L2", "L3", "qa", "supervisory"
  text: string;
  url: string | null; // official text (for a consolidated regulation: that exact version)
  version: string; // e.g. "consolidated version of 26.06.2026" or "as downloaded 2026-10-27"
}

export interface Claim {
  text: string;
  kind: string;
  citations: string[];
  check: string;
}

export interface Step {
  tool: string;
  args: unknown[];
  passages: number;
}

export interface AnswerPayload {
  question: string;
  abstained: boolean;
  abstain_reason: string;
  answer: string;
  as_of: string;
  claims: Claim[];
  sources: Source[];
  check: { ok: number; claims: number };
  route: { route: string; reason: string } | null;
  steps: Step[];
  model: string | null;
  tokens: number;
  errors: string[];
  unresolved: string[]; // citation keys the agent used that matched no passage
  unverified: boolean; // the model's reply broke the answer format even after a retry
  raw_output: string; // that reply, for diagnosis only (empty unless unverified)
  missing_info: boolean; // the answer reports that information it needs is missing
  coverage?: { temporal: string; applicability: string; requested_date?: string };
  corpus_generation?: string;
  partial_reads: number; // cited passages the agent only saw as truncated snippets
}

export interface ProgressEvent {
  stage: "retrieved" | "routing" | "routed" | "drafting" | "agent" | "tool" | "fallback" | "agent_failed" | "invalid_reply" | "completing";
  [key: string]: unknown;
}

export async function getMeta(): Promise<Meta> {
  const r = await fetch(`${API_URL}/api/meta`);
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
}

/** POST the question and read the Server-Sent Events stream until `result` or `error`. */
export async function ask(
  body: { question: string; mode: Mode; access: Access; applies_to: string | null; as_of?: string | null; conditions?: Record<string, string[]> },
  apiKey: string | null,
  onProgress: (e: ProgressEvent) => void,
  signal?: AbortSignal,
): Promise<AnswerPayload> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (body.access === "api" && apiKey) headers["X-Anthropic-Key"] = apiKey; // never stored
  const r = await fetch(`${API_URL}/api/ask`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) {
    const detail = await r.json().catch(() => null);
    throw new Error(detail?.detail ?? `API error ${r.status}`);
  }
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const event = /^event: (.+)$/m.exec(block)?.[1];
      const data = /^data: (.+)$/m.exec(block)?.[1];
      if (!event || !data) continue; // keep-alive comments
      const parsed = JSON.parse(data);
      if (event === "progress") onProgress(parsed);
      else if (event === "result") return parsed as AnswerPayload;
      else if (event === "error") throw new Error(parsed.message);
    }
  }
  throw new Error("The answer stream ended unexpectedly.");
}

export interface GapRow {
  obligation_id: string;
  source: string;
  level: string;
  topic: string;
  actor: string;
  obligation: string;
  status: string;
  clauses: string[];
  quote: string;
  quote_ok: boolean;
  rationale: string;
  // "verified" | "not_verbatim" | "none_required" | "invalid" (older runs: absent)
  evidence?: string;
}

export interface GapRun {
  id: string;
  label: string;
  is_demo: boolean;
}

export interface GapResult {
  gaps: number;
  gaps_assessed?: number;
  complete?: boolean; // false: some planted gaps were not assessed in this run
  recall: number | null;
  type_accuracy: number | null;
  by_type: Record<string, string>;
  statuses: Record<string, number>;
  per_gap: { id: string; type: string; found: boolean; statuses: Record<string, string> }[];
  rows: GapRow[];
  file: string;
  run_id: string;
  run_label: string;
  is_demo: boolean;
}

const runQuery = (run?: string) => (run ? `run=${encodeURIComponent(run)}` : "");

export async function getGapRuns(): Promise<GapRun[]> {
  const r = await fetch(`${API_URL}/api/gap/runs`);
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
}

export async function getGap(run?: string): Promise<GapResult> {
  const r = await fetch(`${API_URL}/api/gap?${runQuery(run)}`);
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `API error ${r.status}`);
  return r.json();
}

export const exportUrl = (format: "csv" | "xlsx", run?: string) =>
  `${API_URL}/api/gap/export?format=${format}${run ? `&${runQuery(run)}` : ""}`;
