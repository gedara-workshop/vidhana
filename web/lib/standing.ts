import type { Gazette } from "./types";

/** How a document stands, derived from the resolver's output and never
 *  recomputed from the reference graph here. `resolve.py` already decided;
 *  a second implementation is a second answer.
 *
 *  `asOf` changes the question and therefore the answer. 1823/05 is rescinded
 *  today and was transfer-pricing law on 1 January 2015 — labelling it
 *  "Rescinded" while time-travelling contradicts the feature. */
export interface StandingView {
  kind: "current" | "amended" | "rescinded" | "as-of";
  /** Short label. Recognised at a glance, not read. */
  pill: string;
  /** The only sentence. Null when there is nothing to act on. */
  consequence: string | null;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  const month = MONTHS[Number(m) - 1];
  return month ? `${Number(d)} ${month} ${y}` : iso;
}

export function standingOf(g: Gazette, asOf?: string | null): StandingView {
  if (asOf) {
    // Reaching here means the document passed the as-of filter, so it was
    // operative then. What it became since is the second line, not the headline.
    const since = g.rescinded_by
      ? `Rescinded since, by ${g.rescinded_by}` +
        (g.rescinded_from ? ` from ${formatDate(g.rescinded_from)}` : "")
      : g.head_no && g.head_no !== g.no
        ? `Amended since — ${g.head_no} is the latest document in this rule`
        : null;
    return { kind: "as-of", pill: "In force on this date", consequence: since };
  }
  if (g.status === "rescinded") {
    return {
      kind: "rescinded",
      pill: "Rescinded",
      consequence: g.rescinded_by
        ? `Rescinded by ${g.rescinded_by}` +
          (g.rescinded_from ? `, from ${formatDate(g.rescinded_from)}` : "")
        : null,
    };
  }
  if (g.head_no && g.head_no !== g.no) {
    // Not "Superseded". Half these rules are one schedule amended item by item
    // over twenty years: 1947/45 amends item 05 of the stamp-duty schedule and
    // 2429/39 amends item 09, so neither replaces the other, and the corpus
    // cannot reliably say which item a gazette touches — "item 4 and 10" in
    // one document, "immediately after the item 26" meaning item 27 in
    // another, "time 10" for "item 10" in a third. What the resolver does know
    // is that this document is in force and something later in its rule amends
    // it, which is what this says. The reader is still sent to the latest
    // document, which is the part they act on.
    return {
      kind: "amended",
      pill: "In force · amended",
      consequence: `${g.head_no} is the latest document in this rule`,
    };
  }
  return { kind: "current", pill: "In force · current", consequence: null };
}

/** Gazette numbers contain a slash, which cannot go in a path segment.
 *  `2500/106` <-> `2500-106`. Derived, never authoritative — the slash form
 *  remains the identity everywhere else, exactly as CLAUDE.md requires. */
export const toSlug = (no: string): string => no.replace("/", "-");
export const fromSlug = (slug: string): string => slug.replace("-", "/");
