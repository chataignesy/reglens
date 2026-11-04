import { Badge } from "@/components/ui/badge";

// Colour by authority: law (CRR, RTS), EBA (guidelines, Q&A), ECB supervisory expectation.
const STYLE: Record<string, string> = {
  L1: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  L2: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  L3: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  qa: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  supervisory: "bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200",
};

export function LevelBadge({ levelKey, label }: { levelKey: string; label: string }) {
  return <Badge className={STYLE[levelKey] ?? "bg-muted text-foreground"}>{label}</Badge>;
}

const KIND_STYLE: Record<string, string> = {
  law: STYLE.L1,
  supervisory: STYLE.L3,
  interpretation: "bg-muted text-muted-foreground",
};

export function KindBadge({ kind }: { kind: string }) {
  return <Badge className={KIND_STYLE[kind] ?? "bg-muted text-foreground"}>{kind}</Badge>;
}
