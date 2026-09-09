"""Tests for the static front end.

Two things are checked here. First, that `export-web` produces what the page
needs — including the disclosures, which a result must never render without.
Second, and more importantly, that the browser's search agrees with the CLI's:
if the web and the terminal disagree about which document is currently the
rule, one of them is lying to somebody.

The JavaScript is exercised through `node`, which the repository already
depends on for the design canvas. Where node is absent the JS tests skip
rather than fail — the Python half still runs.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import db, resolve, search, web

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "docs", "core.js")
NODE = shutil.which("node")


def make_db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db.init(con)
    add(con, "2463/05", "2025-11-17", "Tax invoice format", "Specifies the tax invoice format.")
    add(con, "2481/22", "2026-03-27", "Tax invoice format, replaced", "Requires the new format from July.")
    add(con, "2500/106", "2026-08-06", "Tax invoice format, amended", "Moves the start date to October.")
    add(con, "2088/25", "2018-09-11", "Tourist VAT refund scheme", "Sets out the refund scheme.")
    ref(con, "2481/22", "2463/05", "rescinds")
    ref(con, "2500/106", "2481/22", "amends")
    ref(con, "2088/25", "9999/99", "amends")        # a gazette we do not hold
    resolve.resolve(con)
    search.reindex(con)
    return con


def add(con, no, date, title, summary, subject="vat", conf="high", source="ird-listing"):
    con.execute("INSERT INTO gazette (no, year, published_date, title, source_url, subject, "
                "enabling_act, source) VALUES (?,?,?,?,?,?,?,?)",
                (no, int(date[:4]), date, title, f"http://x/{no}.pdf", subject,
                 "Value Added Tax Act", source))
    con.execute("INSERT INTO gazette_summary (no, model, summary, audience, tags, confidence) "
                "VALUES (?,?,?,?,?,?)",
                (no, "test", summary, '["VAT-registered businesses"]', '["vat"]', conf))
    con.execute("INSERT INTO gazette_audience (no, audience, coarse) VALUES (?,?,?)",
                (no, "VAT-registered businesses", "VAT-registered businesses"))


def ref(con, src, dst, relation):
    con.execute("INSERT INTO gazette_reference (src_no, dst_no, relation) VALUES (?,?,?)",
                (src, dst, relation))


class Export(unittest.TestCase):
    def setUp(self):
        self.con = make_db()
        self.index, self.bodies = web.build(self.con)
        self.by = {g["no"]: g for g in self.index["gazettes"]}

    def test_every_gazette_carries_what_a_result_needs(self):
        # A card cannot be rendered without these, so their absence must fail
        # here rather than as a blank line in someone's browser.
        for g in self.index["gazettes"]:
            for k in ("no", "published_date", "title", "subject", "status",
                      "source", "source_url", "head_no", "unresolved", "missing_refs"):
                self.assertIn(k, g, g["no"])

    def test_thread_head_is_carried_not_recomputed(self):
        self.assertEqual(self.by["2481/22"]["head_no"], "2500/106")
        self.assertEqual(self.by["2463/05"]["status"], "rescinded")
        self.assertEqual(self.by["2463/05"]["rescinded_by"], "2481/22")

    def test_missing_references_reach_the_page(self):
        # The incomplete-history disclosure is computed here, once, so the page
        # cannot forget to derive it.
        self.assertEqual(self.by["2088/25"]["missing_refs"], ["9999/99"])
        self.assertEqual(self.by["2463/05"]["missing_refs"], [])

    def test_counts_distinguish_recovered_documents(self):
        self.assertEqual(self.index["counts"]["gazettes"], 4)
        self.assertEqual(self.index["counts"]["recovered"], 0)
        add(self.con, "1791/08", "2012-12-31", "Embarkation levy", "Levy.",
            subject="other", source="web-archive")
        idx, _ = web.build(self.con)
        self.assertEqual(idx["counts"]["recovered"], 1)

    def test_export_is_byte_stable(self):
        with tempfile.TemporaryDirectory() as d:
            first = web.export(self.con, d)
            self.assertTrue(all(v["changed"] for v in first.values()))
            second = web.export(self.con, d)
            self.assertFalse(any(v["changed"] for v in second.values()))

    def test_missing_text_files_do_not_break_the_export(self):
        # A fresh clone has the database rebuilt but no extracted text.
        _, bodies = web.build(self.con)
        self.assertEqual(bodies, {})


@unittest.skipUnless(NODE, "node is not installed")
class JsCore(unittest.TestCase):
    """Exercise docs/core.js directly — these are the functions that must not
    drift from vidhana/search.py."""

    def run_js(self, body):
        with open(CORE) as f:
            core = f.read()
        script = f"{core}\nconst C = globalThis.VidhanaCore;\n{body}"
        r = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_plural_folding_matches_the_python(self):
        out = json.loads(self.run_js(
            'console.log(JSON.stringify(["tax-rates","notaries","debits-tax","business","gas","supplies"]'
            '.map((w) => w.split("-").map((p, i, a) => i === a.length - 1 ? C.depl(p) : p).join("-"))))'))
        want = []
        for w in ["tax-rates", "notaries", "debits-tax", "business", "gas", "supplies"]:
            parts = w.split("-")
            parts[-1] = search._depluralise(parts[-1])
            want.append("-".join(parts))
        self.assertEqual(out, want)

    def test_as_of_changes_the_standing_it_reports(self):
        # 1823/05 is rescinded today and was the transfer-pricing rule on
        # 1 January 2015. Reporting "Rescinded" while time-travelling
        # contradicts the feature — the reader asked what stood then.
        g = dict(no="1823/05", status="rescinded", rescinded_by="2104/04",
                 rescinded_from="2018-04-01", head_no="2217/07")
        got = json.loads(self.run_js(
            f'const g = {json.dumps(g)};'
            'console.log(JSON.stringify([C.standing(g), C.standing(g, "2015-01-01")]));'))
        today, then = got
        self.assertEqual(today["pill"], "Rescinded")
        self.assertEqual(then["pill"], "In force on this date")
        self.assertIn("Rescinded since", then["conseq"])
        self.assertIn("2104/04", then["conseq"])

    def test_standing_matches_the_resolver(self):
        cases = [
            (dict(no="2463/05", status="rescinded", rescinded_by="2481/22",
                  rescinded_from="2026-07-01", head_no="2500/106"), "res"),
            (dict(no="2481/22", status="in_force", head_no="2500/106"), "sup"),
            (dict(no="2500/106", status="in_force", head_no="2500/106"), "ok"),
            (dict(no="2088/25", status="standalone", head_no=None), "ok"),
        ]
        got = json.loads(self.run_js(
            f'console.log(JSON.stringify({json.dumps([c[0] for c in cases])}.map((g) => C.standing(g).cls)))'))
        self.assertEqual(got, [c[1] for c in cases])

    def test_as_of_uses_the_effective_date_not_publication(self):
        # 2316/13 published 2023-01, effective 2022-10. Filtering on publication
        # would put it in the wrong year — the exact bug this guards.
        g = dict(no="2316/13", published_date="2023-01-20", effective_from="2022-10-01",
                 rescinded_from=None, subject="vat", audience=[], status="in_force")
        got = json.loads(self.run_js(
            f'const g = {json.dumps(g)};'
            'console.log(JSON.stringify(['
            '  C.matches(g, {asOf: "2022-11-01"}),'
            '  C.matches(g, {asOf: "2022-09-01"})]))'))
        self.assertEqual(got, [True, False])

    def test_a_rescission_that_has_not_bitten_yet_does_not_remove_a_document(self):
        g = dict(no="2463/05", effective_from="2026-01-01", rescinded_from="2026-07-01",
                 subject="vat", audience=[], status="rescinded")
        got = json.loads(self.run_js(
            f'const g = {json.dumps(g)};'
            'console.log(JSON.stringify(['
            '  C.matches(g, {asOf: "2026-03-01"}),'
            '  C.matches(g, {asOf: "2026-08-01"})]))'))
        self.assertEqual(got, [True, False])

    def test_the_same_documents_match_as_the_cli(self):
        """The property that actually matters, and the honest version of it.

        Exact rank parity is not achievable and not worth chasing: SQLite's
        fts5 stems with porter, this stems with a light plural fold, and the
        two bm25 implementations normalise length differently. Measured over
        the real corpus they agree on 4-5 of the top 5 documents and differ on
        ordering for about half of queries.

        What must never differ is *which documents match* and *what the page
        says about them* — a document the CLI finds and the browser does not
        is a document a reader will conclude does not exist.
        """
        con = make_db()
        index, _ = web.build(con)
        bodies = {g["no"]: g["summary"] or "" for g in index["gazettes"]}
        js = (f'const gz = {json.dumps(index["gazettes"])};'
              f'const bodies = {json.dumps(bodies)};'
              'const idx = C.buildIndex(gz, bodies);'
              'const qt = C.tokens("tax invoice");'
              'console.log(JSON.stringify(gz.map((g) => [g.no, C.score(idx, g.no, qt)])'
              '  .filter((r) => r[1] > 0).sort((a, b) => b[1] - a[1]).map((r) => r[0])));')
        web_hits = set(json.loads(self.run_js(js)))
        cli_hits = {r["no"] for r in search.search(con, "tax invoice", 50)}
        self.assertTrue(web_hits, "the web search returned nothing")
        self.assertEqual(web_hits, cli_hits,
                         "web and CLI disagree about which documents match")

    def test_query_terms_are_anded_like_fts5(self):
        """`gazette_fts MATCH 'tax invoice'` requires both words. Matching
        either instead turned a three-document answer into sixty on the real
        corpus — every gazette in a tax corpus contains "tax"."""
        con = make_db()
        index, _ = web.build(con)
        bodies = {g["no"]: g["summary"] or "" for g in index["gazettes"]}
        js = (f'const gz = {json.dumps(index["gazettes"])};'
              f'const bodies = {json.dumps(bodies)};'
              'const idx = C.buildIndex(gz, bodies);'
              'const hit = (q) => gz.filter((g) => C.score(idx, g.no, C.tokens(q)) > 0).length;'
              'console.log(JSON.stringify([hit("tax"), hit("refund"), hit("tax refund")]));')
        tax, refund, both = json.loads(self.run_js(js))
        # Three documents are about tax invoices and one about refunds. Under OR
        # a query for both words would match all four; under AND, none — no
        # document in the fixture is about both.
        self.assertEqual((tax, refund), (3, 1))
        self.assertEqual(both, 0, "query terms are being ORed, not ANDed")

    def test_standing_is_identical_to_the_cli_for_every_document(self):
        """Ranking may differ. Standing may not — it is the one claim a reader
        acts on, and the two surfaces disagreeing about it would be the
        product failing at its whole purpose."""
        con = make_db()
        index, _ = web.build(con)
        js = (f'const gz = {json.dumps(index["gazettes"])};'
              'console.log(JSON.stringify(Object.fromEntries('
              '  gz.map((g) => [g.no, C.standing(g).pill]))));')
        web_state = json.loads(self.run_js(js))
        for r in search.search(con, "tax OR refund OR format", 50):
            expected = ("Rescinded" if r["status"] == "rescinded"
                        else "Superseded" if r["head_no"] and r["head_no"] != r["no"]
                        else "In force · current")
            self.assertEqual(web_state[r["no"]], expected, r["no"])
