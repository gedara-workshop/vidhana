"""Tests for the public corpus-health report."""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import db, health, resolve


def corpus():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db.init(con)
    for no, pub, src in (("1439/01", "2006-04-03", "web-archive"),
                         ("2481/22", "2026-03-27", "ird-listing"),
                         ("2500/106", "2026-08-06", "ird-listing")):
        con.execute("INSERT INTO gazette (no, year, published_date, title, source_url, source, "
                    "subject) VALUES (?,?,?,?,?,?,'vat')",
                    (no, int(pub[:4]), pub, "t", "http://x", src))
    con.execute("UPDATE gazette SET parse_warnings='pdf date 2008-09-05 != listing 2008-09-06' "
                "WHERE no='1439/01'")
    con.execute("INSERT INTO gazette_page (no, page, chars, max_image_width, needs_ocr) VALUES ('1439/01', 1, 0, 1600, 1)")
    con.execute("INSERT INTO gazette_reference (src_no, dst_no, relation) "
                "VALUES ('2500/106','2481/22','amends')")
    # one referenced gazette inside the range, one before it
    for dst in ("1680/21", "0224/03"):
        con.execute("INSERT INTO gazette_reference (src_no, dst_no, relation) "
                    "VALUES ('2481/22',?, 'amends')", (dst,))
    resolve.resolve(con)
    return con


class Report(unittest.TestCase):
    def setUp(self):
        self.r = health.report(corpus())

    def test_it_counts_the_corpus_and_its_provenance(self):
        c = self.r["corpus"]
        self.assertEqual((c["gazettes"], c["listed"], c["recovered"]), (3, 2, 1))
        self.assertEqual((c["first"], c["last"]), ("2006-04-03", "2026-08-06"))

    def test_missing_documents_are_split_by_whether_the_listing_covers_them(self):
        # Inside the range is a defect in the source; before it is expected.
        self.assertEqual(self.r["missing"]["in_range"], ["1680/21"])
        self.assertEqual(self.r["missing"]["before_listing"], 1)

    def test_parse_warnings_and_ocr_are_named_not_counted(self):
        self.assertEqual(self.r["parse_warnings"][0]["no"], "1439/01")
        self.assertIn("pdf date", self.r["parse_warnings"][0]["warnings"][0])
        self.assertEqual(self.r["needs_ocr"], [dict(no="1439/01", pages=1)])

    def test_every_answer_set_is_accounted_for(self):
        self.assertEqual(sum(self.r["answers"].values()),
                         self.r["corpus"]["rules"])

    def test_there_is_no_timestamp_in_the_report(self):
        # A "generated at" field would differ on every run, so the nightly job
        # would commit every night — and its history is a record of the law
        # changing, not of the workflow running. The build stamps the page.
        flat = json.dumps(self.r)
        self.assertNotIn("generated_at", flat)
        self.assertEqual(health.report(corpus()), self.r)

    def test_grading_writes_nothing(self):
        con = corpus()
        before = con.execute("SELECT COUNT(*) FROM summary_check").fetchone()[0]
        health.report(con)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM summary_check").fetchone()[0], before)


if __name__ == "__main__":
    unittest.main()
