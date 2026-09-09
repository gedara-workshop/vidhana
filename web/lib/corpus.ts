import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { CorpusIndex, Gazette, Thread } from "./types";

/* Build-time corpus access. Read straight off disk rather than imported, so a
 * rebuilt index needs no code change and the 1 MB body file never lands in a
 * server-component payload — the client fetches that itself, once. */

const DATA = process.env.VIDHANA_DATA ?? join(process.cwd(), "public", "data");

let cached: CorpusIndex | null = null;

export function corpus(): CorpusIndex {
  if (cached) return cached;
  const raw = readFileSync(join(DATA, "index.json"), "utf8");
  const parsed = JSON.parse(raw) as CorpusIndex;
  if (!Array.isArray(parsed.gazettes) || !parsed.counts) {
    throw new Error("index.json is not the shape lib/types.ts expects — re-run `vidhana export-web`");
  }
  cached = parsed;
  return parsed;
}

export const allGazettes = (): Gazette[] => corpus().gazettes;
export const allThreads = (): Thread[] => corpus().threads;

export function gazetteMap(): Map<string, Gazette> {
  return new Map(corpus().gazettes.map((g) => [g.no, g]));
}

export function gazette(no: string): Gazette | undefined {
  return corpus().gazettes.find((g) => g.no === no);
}

export function thread(id: number): Thread | undefined {
  return corpus().threads.find((t) => t.thread_id === id);
}

/** Documents in a rule, oldest first — the order the history reads in. */
export function threadMembers(id: number): Gazette[] {
  return corpus().gazettes
    .filter((g) => g.thread_id === id)
    .sort((a, b) => (a.published_date < b.published_date ? -1 : 1));
}

/** Gazette numbers a rule references but the corpus does not hold. The reason
 *  "in force" is reported as conditional rather than asserted. */
export function missingFrom(members: Gazette[]): string[] {
  const out = new Set<string>();
  for (const m of members) for (const r of m.missing_refs) out.add(r);
  return [...out].sort();
}

export function facetCounts() {
  const gz = allGazettes();
  const subject = new Map<string, number>();
  const audience = new Map<string, number>();
  for (const g of gz) {
    subject.set(g.subject, (subject.get(g.subject) ?? 0) + 1);
    for (const a of g.audience) audience.set(a, (audience.get(a) ?? 0) + 1);
  }
  const byCount = (a: [string, number], b: [string, number]) => b[1] - a[1];
  return {
    subject: [...subject.entries()].sort(byCount),
    audience: [...audience.entries()].sort(byCount),
    status: [
      ["current", gz.filter((g) => g.status !== "rescinded" && (!g.head_no || g.head_no === g.no)).length],
      ["inforce", gz.filter((g) => g.status !== "rescinded").length],
      ["rescinded", gz.filter((g) => g.status === "rescinded").length],
    ] as [string, number][],
  };
}
