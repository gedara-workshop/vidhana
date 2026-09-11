import type { Gazette, Thread } from "./types";
import { rulePath } from "./rules.ts";
import { toSlug } from "./standing.ts";

/* Absolute URLs for the deployed site.
 *
 * `basePath` is applied by Next to links and assets, but *not* to the URLs
 * inside sitemap.xml or robots.txt — those are written by us and must be
 * absolute. Resolving them here keeps one source of truth for "where does this
 * site live", so a custom domain is an environment change rather than a search
 * through the app for hardcoded `/vidhana/` prefixes.
 */

export const ORIGIN =
  process.env.NEXT_PUBLIC_SITE_ORIGIN ?? "https://gedara-workshop.github.io";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** The site root, no trailing slash: `https://host` or `https://host/vidhana`. */
export const SITE = `${ORIGIN}${BASE}`;

/** An absolute URL for a route. `path` is the in-app path, leading slash and
 *  trailing slash included — `trailingSlash: true` means `/rules/`, not
 *  `/rules`, and a sitemap that disagrees with the served URL wastes a crawl. */
export const url = (path: string): string => `${SITE}${path}`;

export interface SitemapEntry {
  url: string;
  lastModified: string;
  /** Relative to the other pages on this site only; it carries no absolute
   *  meaning to a crawler. Rules rank above the gazettes that compose them
   *  because a rule page answers the question a searcher actually asked. */
  priority: number;
  changeFrequency: "daily" | "weekly" | "monthly" | "yearly";
}

/** Every statically rendered page, with the date its content last changed.
 *
 *  A gazette page is not stale on the day it was published: it is rewritten
 *  every time something later in its rule supersedes or rescinds it, because
 *  the standing pill and the timeline both change. So `lastModified` is the
 *  newest date in the thread, not the gazette's own — otherwise a 2006 notice
 *  amended last month reports 2006 and never gets recrawled.
 */
export function sitemapEntries(gazettes: Gazette[], threads: Thread[]): SitemapEntry[] {
  const newest = new Map<number, string>();
  for (const g of gazettes) {
    if (g.thread_id === null) continue;
    const seen = newest.get(g.thread_id);
    if (!seen || g.published_date > seen) newest.set(g.thread_id, g.published_date);
  }

  const corpusDate = gazettes.reduce(
    (max, g) => (g.published_date > max ? g.published_date : max),
    "0000-00-00",
  );

  const entries: SitemapEntry[] = [
    // Search and the rules index change whenever the corpus does.
    { url: url("/"), lastModified: corpusDate, priority: 1.0, changeFrequency: "daily" },
    { url: url("/rules/"), lastModified: corpusDate, priority: 0.9, changeFrequency: "daily" },
    { url: url("/feeds/"), lastModified: corpusDate, priority: 0.5, changeFrequency: "monthly" },
  ];

  for (const t of threads) {
    entries.push({
      url: url(rulePath(t)),
      lastModified: t.last_date,
      priority: 0.8,
      changeFrequency: "weekly",
    });
  }

  for (const g of gazettes) {
    entries.push({
      url: url(`/gazette/${toSlug(g.no)}/`),
      lastModified: (g.thread_id !== null ? newest.get(g.thread_id) : null) ?? g.published_date,
      priority: 0.6,
      changeFrequency: "monthly",
    });
  }

  return entries;
}
