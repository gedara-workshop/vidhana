import assert from "node:assert/strict";
import test from "node:test";

import { SITE, sitemapEntries, url } from "./site.ts";
import type { Gazette, Thread } from "./types.ts";

const g = (over: Partial<Gazette> & { no: string }): Gazette => ({
  published_date: "2026-01-01", title: "", subject: "vat", enabling_act: null,
  status: "in_force", rescinded_by: null, rescinded_from: null, effective_from: "2026-01-01",
  thread_id: null, source: "ird-listing", source_detail: null, source_url: "http://x",
  needs_ocr: 0, summary: null, obligation: null, confidence: "high", notes: null,
  tags: [], audience: [], refs: [], dates: [], head_no: null, thread_size: 1,
  unresolved: 0, missing_refs: [], ...over,
});

const t = (over: Partial<Thread> & { thread_id: number }): Thread => ({
  subject: "vat", enabling_act: null, root_no: "1/1", head_no: "1/1",
  first_date: "2006-01-01", last_date: "2026-01-01", size: 1, unresolved: 0, questions: [], ...over,
});

test("every URL is absolute and carries the base path", () => {
  // basePath is applied by Next to links, never to sitemap contents. A relative
  // path here ships a sitemap full of URLs that resolve against nothing.
  for (const e of sitemapEntries([g({ no: "2500/106" })], [t({ thread_id: 1 })])) {
    assert.ok(e.url.startsWith("https://"), e.url);
    assert.ok(e.url.startsWith(SITE), e.url);
  }
});

test("every URL ends in a slash, because trailingSlash does", () => {
  // Pages serves /rules/ and 301s /rules. A sitemap of redirects burns crawl
  // budget on hops that teach a crawler nothing.
  for (const e of sitemapEntries([g({ no: "2500/106" })], [t({ thread_id: 1 })])) {
    assert.ok(e.url.endsWith("/"), e.url);
  }
});

test("the slash in a gazette number becomes a dash", () => {
  const entries = sitemapEntries([g({ no: "2500/106" })], []);
  assert.ok(entries.some((e) => e.url === url("/gazette/2500-106/")));
});

test("a gazette's lastModified is the newest date in its rule", () => {
  // A 2006 notice amended in 2026 has a 2026 page: the standing pill flipped to
  // Superseded and the timeline grew a node. Reporting 2006 tells a crawler
  // there is nothing new to fetch, which is exactly wrong.
  const entries = sitemapEntries(
    [
      g({ no: "1439/01", published_date: "2006-04-03", thread_id: 7 }),
      g({ no: "2500/106", published_date: "2026-03-27", thread_id: 7 }),
    ],
    [t({ thread_id: 7, last_date: "2026-03-27" })],
  );
  const old = entries.find((e) => e.url.endsWith("/gazette/1439-01/"));
  assert.equal(old?.lastModified, "2026-03-27");
});

test("a gazette in no rule reports its own date", () => {
  const entries = sitemapEntries([g({ no: "2295/10", published_date: "2022-08-01" })], []);
  const only = entries.find((e) => e.url.endsWith("/gazette/2295-10/"));
  assert.equal(only?.lastModified, "2022-08-01");
});

test("every page the site renders appears exactly once", () => {
  const gazettes = [g({ no: "2500/106", thread_id: 7 }), g({ no: "2481/22", thread_id: 7 })];
  const threads = [t({ thread_id: 7 })];
  const entries = sitemapEntries(gazettes, threads);
  const urls = entries.map((e) => e.url);
  assert.equal(new Set(urls).size, urls.length, "duplicate URL in the sitemap");
  // three fixed routes + one per rule + one per gazette
  assert.equal(entries.length, 3 + threads.length + gazettes.length);
});
