import type { Gazette, Thread } from "./types";
import { fromSlug, toSlug } from "./standing.ts";

/* How a rule is addressed.
 *
 * A rule used to live at /rule/<thread_id>/, and thread_id is a position: the
 * resolver numbers threads in sort order, so any change to the corpus's shape
 * renumbers them. On 2026-09-10 seven documents went missing for a night and
 * 11 of the 20 rule URLs silently pointed at a different rule.
 *
 * A rule is now addressed by a gazette. Canonically by its first document —
 * `/rule/1439-01/` — and, as an alias, by any of its other documents. That
 * makes every rule URL ever published durable without keeping a history:
 *
 *  - an older document joins the rule (a recovery):   the old root is now a
 *    member, so its URL redirects to the new root;
 *  - two rules merge (one gazette amends both):        the absorbed root is a
 *    member of the merged rule, and redirects to it;
 *  - a rule splits (a parser fix removes an edge):     each old member lands
 *    in some rule, or stands alone and redirects to its own gazette page.
 *
 * The only way a /rule/<gazette>/ URL can break is for the gazette to leave
 * the corpus, and `vidhana guard` refuses to publish that.
 */

/** The highest numeric rule id ever published. Those URLs were live for two
 *  days under two different numberings that disagree — /rule/3/ meant the ESC
 *  rule, then an income-tax one — so neither can be honoured without being
 *  wrong for someone. They go to the index instead. Frozen: never grows. */
export const LEGACY_RULE_IDS = 20;

export const ruleSlug = (t: Thread): string => toSlug(t.root_no);

export const rulePath = (t: Thread): string => `/rule/${ruleSlug(t)}/`;

export type RuleAddress =
  | { kind: "rule"; thread: Thread }
  | { kind: "redirect"; to: string; reason: "member" | "standalone" | "legacy" };

/** What a /rule/<address>/ URL means. `undefined` is a 404. */
export function resolveRuleAddress(
  address: string,
  gazettes: Gazette[],
  threads: Thread[],
): RuleAddress | undefined {
  if (/^\d+$/.test(address)) {
    const n = Number(address);
    return n >= 1 && n <= LEGACY_RULE_IDS
      ? { kind: "redirect", to: "/rules/", reason: "legacy" }
      : undefined;
  }
  const no = fromSlug(address);
  const g = gazettes.find((x) => x.no === no);
  if (!g) return undefined;
  const t = g.thread_id === null ? undefined : threads.find((x) => x.thread_id === g.thread_id);
  if (!t) return { kind: "redirect", to: `/gazette/${address}/`, reason: "standalone" };
  if (t.root_no === g.no) return { kind: "rule", thread: t };
  return { kind: "redirect", to: rulePath(t), reason: "member" };
}

/** Every address the site answers under /rule/: each gazette, plus the frozen
 *  legacy ids. Exactly one per rule is canonical; the rest redirect. */
export function ruleAddresses(gazettes: Gazette[]): string[] {
  const legacy = Array.from({ length: LEGACY_RULE_IDS }, (_, i) => String(i + 1));
  return [...gazettes.map((g) => toSlug(g.no)), ...legacy];
}
