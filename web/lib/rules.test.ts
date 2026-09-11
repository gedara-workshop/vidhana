import assert from "node:assert/strict";
import test from "node:test";

import { LEGACY_RULE_IDS, resolveRuleAddress, ruleAddresses, rulePath } from "./rules.ts";
import type { Gazette, Thread } from "./types.ts";

const g = (no: string, thread_id: number | null, published_date = "2026-01-01"): Gazette => ({
  no, published_date, title: "", subject: "vat", enabling_act: null, status: "in_force",
  rescinded_by: null, rescinded_from: null, effective_from: published_date, thread_id,
  source: "ird-listing", source_detail: null, source_url: "http://x", needs_ocr: 0,
  summary: null, obligation: null, confidence: "high", notes: null, tags: [], audience: [],
  refs: [], dates: [], head_no: null, thread_size: 1, unresolved: 0, missing_refs: [],
});

const t = (thread_id: number, root_no: string, head_no = root_no): Thread => ({
  thread_id, subject: "vat", enabling_act: null, root_no, head_no,
  first_date: "2006-01-01", last_date: "2026-01-01", size: 2, unresolved: 0,
});

test("a rule is canonically addressed by its first gazette", () => {
  const a = resolveRuleAddress("2463-05", [g("2463/05", 7), g("2500/106", 7)], [t(7, "2463/05")]);
  assert.equal(a?.kind, "rule");
});

test("any other member redirects to the rule", () => {
  const a = resolveRuleAddress("2500-106", [g("2463/05", 7), g("2500/106", 7)], [t(7, "2463/05")]);
  assert.deepEqual(a, { kind: "redirect", to: "/rule/2463-05/", reason: "member" });
});

test("the address does not depend on the thread's position", () => {
  // The bug: thread_id is a sort position. Renumber every thread and every
  // URL must still mean the same rule.
  const before = resolveRuleAddress("2463-05", [g("2463/05", 20)], [t(20, "2463/05")]);
  const after = resolveRuleAddress("2463-05", [g("2463/05", 19)], [t(19, "2463/05")]);
  assert.equal(before?.kind, "rule");
  assert.equal(after?.kind, "rule");
});

test("a recovered older document moves the root, and the old root still resolves", () => {
  // 1680/21 is missing today. If it is recovered and turns out to be the
  // oldest document in a rule, the URL everyone had becomes an alias.
  const gz = [g("1680/21", 3), g("1709/10", 3)];
  const a = resolveRuleAddress("1709-10", gz, [t(3, "1680/21")]);
  assert.deepEqual(a, { kind: "redirect", to: "/rule/1680-21/", reason: "member" });
});

test("when two rules merge, the absorbed root redirects to the merged rule", () => {
  const gz = [g("2064/53", 1), g("2064/54", 1), g("2510/01", 1)];
  const a = resolveRuleAddress("2064-54", gz, [t(1, "2064/53")]);
  assert.deepEqual(a, { kind: "redirect", to: "/rule/2064-53/", reason: "member" });
});

test("a gazette that stands alone redirects to its own page", () => {
  const a = resolveRuleAddress("2295-10", [g("2295/10", null)], []);
  assert.deepEqual(a, { kind: "redirect", to: "/gazette/2295-10/", reason: "standalone" });
});

test("legacy numeric ids go to the index, never to a guessed rule", () => {
  // Two numberings were live and they disagree, so any specific rule would be
  // wrong for someone.
  for (const id of ["1", "3", String(LEGACY_RULE_IDS)]) {
    assert.deepEqual(resolveRuleAddress(id, [], []),
                     { kind: "redirect", to: "/rules/", reason: "legacy" });
  }
  assert.equal(resolveRuleAddress(String(LEGACY_RULE_IDS + 1), [], []), undefined);
  assert.equal(resolveRuleAddress("0", [], []), undefined);
});

test("an address that names no gazette is a 404", () => {
  assert.equal(resolveRuleAddress("9999-99", [g("2463/05", 7)], [t(7, "2463/05")]), undefined);
});

test("every gazette is an address, and exactly one per rule is canonical", () => {
  const gz = [g("2463/05", 7), g("2481/22", 7), g("2500/106", 7), g("2295/10", null)];
  const th = [t(7, "2463/05")];
  const addrs = ruleAddresses(gz);
  assert.equal(addrs.length, gz.length + LEGACY_RULE_IDS);
  const canonical = addrs.filter((a) => resolveRuleAddress(a, gz, th)?.kind === "rule");
  assert.deepEqual(canonical, ["2463-05"]);
  assert.equal(rulePath(th[0]!), "/rule/2463-05/");
});
