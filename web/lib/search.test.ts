import assert from "node:assert/strict";
import test from "node:test";

import { buildIndex, depluralise, matches, runSearch, score, tokenise } from "./search.ts";
import type { Gazette } from "./types.ts";

/* These pin the properties vidhana/search.py is the other half of. Ranking may
 * differ between the two — fts5 stems with porter, this uses a light plural
 * fold — but which documents match, and what the page says about them, may not. */

const g = (over: Partial<Gazette> & { no: string }): Gazette => ({
  published_date: "2026-01-01", title: "", subject: "vat", enabling_act: null,
  status: "in_force", rescinded_by: null, rescinded_from: null, effective_from: "2026-01-01",
  thread_id: null, source: "ird-listing", source_detail: null, source_url: "http://x",
  needs_ocr: 0, summary: null, obligation: null, confidence: "high", notes: null,
  tags: [], audience: [], refs: [], dates: [], head_no: null, thread_size: 1,
  unresolved: 0, missing_refs: [], ...over,
});

test("plural folding touches only the final token", () => {
  // `debits-tax` is the Act's own name; folding every token would quietly
  // rename it. Callers fold the last token, which is where the head noun sits.
  assert.equal(depluralise("rates"), "rate");
  assert.equal(depluralise("notaries"), "notary");
  assert.equal(depluralise("supplies"), "supply");
  assert.equal(depluralise("business"), "business");
  assert.equal(depluralise("gas"), "gas");
});

test("query terms are ANDed, as fts5 does", () => {
  // ORing turned a 13-document answer into 60 on the real corpus, because
  // every gazette in a tax corpus contains "tax".
  const docs = [
    g({ no: "1/1", title: "Tax invoice format", summary: "The tax invoice format." }),
    g({ no: "1/2", title: "Tourist refund scheme", summary: "A refund scheme." }),
  ];
  const idx = buildIndex(docs, null);
  const hits = (q: string) => docs.filter((d) => score(idx, d.no, tokenise(q)) > 0).length;
  assert.equal(hits("tax"), 1);
  assert.equal(hits("refund"), 1);
  assert.equal(hits("tax refund"), 0, "terms are being ORed, not ANDed");
});

test("as-of tests the effective date, never publication", () => {
  // 2316/13 was published in January 2023 and took effect in October 2022.
  // Filtering on publication puts it in the wrong year.
  const doc = g({ no: "2316/13", published_date: "2023-01-20", effective_from: "2022-10-01" });
  assert.equal(matches(doc, { asOf: "2022-11-01" }), true);
  assert.equal(matches(doc, { asOf: "2022-09-01" }), false);
});

test("a rescission that has not bitten yet leaves a document standing", () => {
  const doc = g({ no: "2463/05", effective_from: "2026-01-01", rescinded_from: "2026-07-01",
                  status: "rescinded" });
  assert.equal(matches(doc, { asOf: "2026-03-01" }), true);
  assert.equal(matches(doc, { asOf: "2026-08-01" }), false);
});

test("rules mode answers with the thread head, not the row that matched", () => {
  const docs = [
    g({ no: "2463/05", thread_id: 1, head_no: "2500/106", title: "Tax invoice" }),
    g({ no: "2481/22", thread_id: 1, head_no: "2500/106", title: "Tax invoice" }),
    g({ no: "2500/106", thread_id: 1, head_no: "2500/106", title: "Tax invoice" }),
  ];
  const byNo = new Map(docs.map((d) => [d.no, d]));
  const out = runSearch(docs, buildIndex(docs, null), byNo, { query: "tax invoice", rules: true });
  assert.equal(out.length, 1);
  assert.equal(out[0]?.no, "2500/106", "a rule must be answered by its current document");
});

test("filters compose", () => {
  const docs = [
    g({ no: "1/1", subject: "vat", audience: ["notaries"] }),
    g({ no: "1/2", subject: "vat", audience: [] }),
    g({ no: "1/3", subject: "stamp-duty", audience: ["notaries"] }),
  ];
  const byNo = new Map(docs.map((d) => [d.no, d]));
  const out = runSearch(docs, null, byNo, { subject: "vat", audience: "notaries" });
  assert.deepEqual(out.map((d) => d.no), ["1/1"]);
});
