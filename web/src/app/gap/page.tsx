import type { Metadata } from "next";
import { GapView } from "@/components/gap/gap-view";

export const metadata: Metadata = { title: "Policy gap analysis · RegLens" };

export default function GapPage() {
  return <GapView />;
}
