import assert from "node:assert/strict";
import test from "node:test";

import { formatDate, fromSlug, standingOf, toSlug } from "./standing.ts";
import type { Gazette } from "./types.ts";

const g = (over: Partial<Gazette> & { no: string }): Gazette => ({
  published_date: "2026-01-01", title: "", subject: "vat", enabling_act: null,
  status: "in_force", rescinded_by: null, rescinded_from: null, effective_from: "2026-01-01",
  thread_id: null, source: "ird-listing", source_detail: null, source_url: "http://x",
  needs_ocr: 0, summary: null, obligation: null, confidence: "high", notes: null,
  tags: [], audience: [], refs: [], dates: [], head_no: null, thread_size: 1,
  unresolved: 0, missing_refs: [], ...over,
});

test("the current document carries no consequence line", () => {
  // There is nothing to act on, and a sentence there trains readers to skip
  // the ones that matter.
  const s = standingOf(g({ no: "2500/106", head_no: "2500/106" }));
  assert.equal(s.kind, "current");
  assert.equal(s.consequence, null);
});

test("an amended document is not called superseded", () => {
  // 1947/45 amends item 05 of the stamp-duty schedule; 2429/39 amends item 09.
  // Neither replaces the other, and "Superseded" told readers otherwise.
  const s = standingOf(g({ no: "2481/22", head_no: "2500/106" }));
  assert.equal(s.kind, "amended");
  assert.equal(s.pill, "In force · amended");
  assert.match(s.consequence ?? "", /2500\/106 is the latest document in this rule/);
  assert.doesNotMatch(s.pill + (s.consequence ?? ""), /superseded/i);
});

test("a rescission is named with its date", () => {
  const s = standingOf(g({ no: "2463/05", status: "rescinded",
                           rescinded_by: "2481/22", rescinded_from: "2026-07-01" }));
  assert.equal(s.pill, "Rescinded");
  assert.match(s.consequence ?? "", /2481\/22, from 1 Jul 2026/);
});

test("as-of reports what stood then, not what stands now", () => {
  // 1823/05 is rescinded today and was transfer-pricing law on 1 January 2015.
  // Labelling it "Rescinded" while time-travelling contradicts the feature.
  const doc = g({ no: "1823/05", status: "rescinded", rescinded_by: "2104/04",
                  rescinded_from: "2018-04-01", head_no: "2217/07" });
  assert.equal(standingOf(doc).pill, "Rescinded");
  const then = standingOf(doc, "2015-01-01");
  assert.equal(then.pill, "In force on this date");
  assert.match(then.consequence ?? "", /Rescinded since, by 2104\/04/);
});

test("slugs round-trip and keep the slash form as the identity", () => {
  assert.equal(toSlug("2500/106"), "2500-106");
  assert.equal(fromSlug("2500-106"), "2500/106");
  assert.equal(fromSlug(toSlug("2217/07")), "2217/07");
});

test("dates render as a person would write them", () => {
  assert.equal(formatDate("2026-08-06"), "6 Aug 2026");
  assert.equal(formatDate(null), "");
});
