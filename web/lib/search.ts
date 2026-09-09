import type { Bodies, Gazette } from "./types";

/* Search, ported from docs/core.js and typed. The properties this must keep,
 * because vidhana/search.py is the other half of them:
 *
 *   - the same documents match. One the CLI finds and this does not is one a
 *     reader concludes does not exist.
 *   - terms are ANDed. `gazette_fts MATCH 'tax invoice'` requires both words;
 *     ORing them turned a 13-document answer into 60, because every gazette in
 *     a tax corpus contains "tax".
 *
 * Ranking need not match exactly: fts5 stems with porter, this uses a light
 * plural fold, and the two bm25 implementations normalise length differently.
 * Measured over 144 documents they agree on 4-5 of the top 5 and order them
 * differently for about half of queries. Standing is what must never differ.
 */

/** Mirrors search._depluralise: folds only the final token of a term, since
 *  that is where the head noun sits. `debits-tax` must not become `debit-tax`. */
export function depluralise(w: string): string {
  if (w.length < 4 || w.endsWith("ss")) return w;
  if (w.endsWith("ies")) return `${w.slice(0, -3)}y`;
  if (/(ses|xes|ches|shes)$/.test(w)) return w.slice(0, -2);
  return w.endsWith("s") ? w.slice(0, -1) : w;
}

const STOP = new Set(["the", "of", "and", "to", "in", "a", "for", "on", "by", "no"]);

export function tokenise(s: string | null | undefined): string[] {
  const m = String(s ?? "").toLowerCase().match(/[a-z0-9][a-z0-9/-]*/g);
  if (!m) return [];
  return m.map(depluralise).filter((t) => t.length > 1 && !STOP.has(t));
}

/** Field weights mirror search.WEIGHTS over the same three fields gazette_fts
 *  indexes. Tags and audience are deliberately excluded even though the export
 *  carries them: the CLI does not index them, and a field only one surface
 *  searches is a guaranteed disagreement. They stay filterable as facets. */
const FIELDS = ["title", "summary", "body"] as const;
type Field = (typeof FIELDS)[number];
const WEIGHT: Record<Field, number> = { title: 6, summary: 4, body: 1 };

interface DocEntry {
  tf: Record<Field, Map<string, number>>;
  len: Record<Field, number>;
}

export interface SearchIndex {
  df: Map<string, number>;
  docs: Map<string, DocEntry>;
  avg: Record<Field, number>;
  n: number;
}

export function buildIndex(gazettes: Gazette[], bodies: Bodies | null): SearchIndex {
  const df = new Map<string, number>();
  const docs = new Map<string, DocEntry>();
  const total: Record<Field, number> = { title: 0, summary: 0, body: 0 };

  for (const g of gazettes) {
    const text: Record<Field, string[]> = {
      title: tokenise(g.title),
      summary: tokenise(g.summary),
      body: tokenise(bodies?.[g.no] ?? ""),
    };
    const tf = {} as Record<Field, Map<string, number>>;
    const len = {} as Record<Field, number>;
    const seen = new Set<string>();
    for (const f of FIELDS) {
      const counts = new Map<string, number>();
      for (const t of text[f]) counts.set(t, (counts.get(t) ?? 0) + 1);
      tf[f] = counts;
      len[f] = text[f].length;
      total[f] += text[f].length;
      for (const t of counts.keys()) seen.add(t);
    }
    for (const t of seen) df.set(t, (df.get(t) ?? 0) + 1);
    docs.set(g.no, { tf, len });
  }

  const avg = {} as Record<Field, number>;
  for (const f of FIELDS) avg[f] = total[f] / (docs.size || 1) || 1;
  return { df, docs, avg, n: docs.size };
}

const present = (d: DocEntry, t: string): boolean =>
  d.tf.title.has(t) || d.tf.summary.has(t) || d.tf.body.has(t);

export function score(index: SearchIndex, no: string, queryTokens: string[]): number {
  const d = index.docs.get(no);
  if (!d) return 0;
  for (const t of queryTokens) if (!present(d, t)) return 0;   // AND, like fts5

  const k1 = 1.2;
  const b = 0.75;
  let total = 0;
  for (const t of queryTokens) {
    const nq = index.df.get(t) ?? 0;
    if (!nq) continue;
    const idf = Math.log(1 + (index.n - nq + 0.5) / (nq + 0.5));
    for (const f of FIELDS) {
      const freq = d.tf[f].get(t) ?? 0;
      if (!freq) continue;
      total += WEIGHT[f] * idf *
        (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * d.len[f] / index.avg[f]));
    }
  }
  return total;
}

export interface Filters {
  subject?: string | null;
  audience?: string | null;
  status?: "current" | "inforce" | "rescinded" | null;
  asOf?: string | null;
}

/** Mirrors search._filters. `asOf` tests the effective date, never publication:
 *  2316/13 was published in January 2023 and took effect in October 2022, so
 *  publication order is not chronological order. */
export function matches(g: Gazette, f: Filters): boolean {
  if (f.subject && g.subject !== f.subject) return false;
  if (f.audience && !g.audience.includes(f.audience)) return false;
  if (f.status === "current" &&
      !(g.status !== "rescinded" && (!g.head_no || g.head_no === g.no))) return false;
  if (f.status === "inforce" && g.status === "rescinded") return false;
  if (f.status === "rescinded" && g.status !== "rescinded") return false;
  if (f.asOf) {
    if (!g.effective_from || g.effective_from > f.asOf) return false;
    if (g.rescinded_from && g.rescinded_from <= f.asOf) return false;
  }
  return true;
}

export interface SearchOptions extends Filters {
  query?: string;
  /** Collapse to one result per rule, answered by its current document. */
  rules?: boolean;
}

export function runSearch(
  gazettes: Gazette[],
  index: SearchIndex | null,
  byNo: Map<string, Gazette>,
  opts: SearchOptions,
): Gazette[] {
  const qt = tokenise(opts.query);
  let rows = gazettes.filter((g) => matches(g, opts));

  if (qt.length && index) {
    rows = rows
      .map((g) => ({ g, s: score(index, g.no, qt) }))
      .filter((r) => r.s > 0)
      .sort((a, b) => b.s - a.s || (a.g.published_date < b.g.published_date ? 1 : -1))
      .map((r) => r.g);
  } else {
    rows = [...rows].sort((a, b) => (a.published_date < b.published_date ? 1 : -1));
  }

  if (opts.rules) {
    const seen = new Set<string>();
    const out: Gazette[] = [];
    for (const g of rows) {
      const key = g.thread_id ? `t${g.thread_id}` : `g${g.no}`;
      if (seen.has(key)) continue;
      seen.add(key);
      // A thread's answer is its current document, which may not be the row
      // that matched — that is the entire point of the mode.
      const head = g.head_no ? byNo.get(g.head_no) : undefined;
      out.push(head ?? g);
    }
    rows = out;
  }
  return rows;
}
