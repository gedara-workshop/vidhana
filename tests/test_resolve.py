"""Tests for the amendment-graph resolver.

Fixtures mirror real threads from the corpus, trimmed to the smallest shape that
exercises the rule.
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import db, resolve


def make_db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    with open(db.SCHEMA) as f:
        con.executescript(f.read())
    return con


def add(con, no, date, title="t", subject="vat", act="Value Added Tax Act"):
    con.execute("INSERT INTO gazette (no, year, published_date, title, source_url, "
                "subject, enabling_act) VALUES (?,?,?,?,?,?,?)",
                (no, int(date[:4]), date, title, "http://x", subject, act))


def ref(con, src, dst, relation):
    con.execute("INSERT INTO gazette_reference (src_no, dst_no, relation) VALUES (?,?,?)",
                (src, dst, relation))


def date(con, no, kind, d):
    con.execute("INSERT INTO gazette_date (no, kind, date, context) VALUES (?,?,?,'')",
                (no, kind, d))


class TestThreading(unittest.TestCase):
    def test_cites_does_not_merge_threads(self):
        # 1868/10 and 2316/13 both cite 1606/30 (a depreciation-rates gazette).
        # A plain citation must not bind unrelated rules into one thread.
        con = make_db()
        add(con, "1000/01", "2010-01-01")
        add(con, "2000/01", "2020-01-01")
        add(con, "1606/30", "2009-06-19")
        ref(con, "1000/01", "1606/30", "cites")
        ref(con, "2000/01", "1606/30", "cites")
        r = resolve.resolve(con)
        self.assertEqual(r["threads"], 0)
        self.assertEqual(r["standalone"], 3)

    def test_amends_creates_one_thread(self):
        con = make_db()
        add(con, "1000/01", "2010-01-01")
        add(con, "2000/01", "2020-01-01")
        ref(con, "2000/01", "1000/01", "amends")
        r = resolve.resolve(con)
        self.assertEqual(r["threads"], 1)
        self.assertEqual(r["threaded"], 2)

    def test_dangling_reference_does_not_create_a_node(self):
        # 13 of 106 real edges point outside the listing.
        con = make_db()
        add(con, "2000/01", "2020-01-01")
        ref(con, "2000/01", "0224/03", "rescinds")
        r = resolve.resolve(con)
        self.assertEqual(r["threads"], 0)
        self.assertEqual(r["standalone"], 1)


class TestRescission(unittest.TestCase):
    def test_rescission_uses_its_own_effective_date(self):
        # 2481/22 rescinds 2463/05 only from 01 Jul 2026, not on publication:
        # there is a window in which both stand.
        con = make_db()
        add(con, "2463/05", "2025-11-17")
        add(con, "2481/22", "2026-03-27")
        ref(con, "2481/22", "2463/05", "rescinds")
        date(con, "2481/22", "rescind_effective", "2026-07-01")
        resolve.resolve(con)
        row = con.execute("SELECT * FROM gazette WHERE no='2463/05'").fetchone()
        self.assertEqual(row["status"], "rescinded")
        self.assertEqual(row["rescinded_by"], "2481/22")
        self.assertEqual(row["rescinded_from"], "2026-07-01")

    def test_head_is_the_latest_standing_document(self):
        con = make_db()
        add(con, "2463/05", "2025-11-17")
        add(con, "2481/22", "2026-03-27")
        ref(con, "2481/22", "2463/05", "rescinds")
        resolve.resolve(con)
        t = con.execute("SELECT head_no FROM rule_thread").fetchone()
        self.assertEqual(t["head_no"], "2481/22")


class TestEffectiveDate(unittest.TestCase):
    def test_retroactive_effective_date_is_kept(self):
        # 2316/13: published Jan 2023, effective Oct 2022.
        con = make_db()
        add(con, "2316/13", "2023-01-24")
        date(con, "2316/13", "effective", "2022-10-01")
        resolve.resolve(con)
        self.assertEqual(
            con.execute("SELECT effective_from FROM gazette WHERE no='2316/13'")
               .fetchone()["effective_from"], "2022-10-01")

    def test_falls_back_to_publication(self):
        con = make_db()
        add(con, "1991/35", "2016-11-02")
        resolve.resolve(con)
        self.assertEqual(
            con.execute("SELECT effective_from FROM gazette WHERE no='1991/35'")
               .fetchone()["effective_from"], "2016-11-02")

    def test_metadata_amendment_propagates_to_its_target(self):
        # The 2500/106 case: it moves 2481/22 from July to October. Neither
        # document states that on its own.
        con = make_db()
        add(con, "2481/22", "2026-03-27")
        add(con, "2500/106", "2026-08-06")
        date(con, "2481/22", "effective", "2026-07-01")
        date(con, "2500/106", "sets_effective_date", "2026-10-01")
        date(con, "2500/106", "replaces_effective_date", "2026-07-01")
        ref(con, "2500/106", "2481/22", "amends")
        resolve.resolve(con)
        rows = {r["no"]: r["effective_from"] for r in
                con.execute("SELECT no, effective_from FROM gazette")}
        self.assertEqual(rows["2481/22"], "2026-10-01")
        # the amending instrument itself takes effect on publication; October is
        # a value it sets on another gazette, not its own effective date
        self.assertEqual(rows["2500/106"], "2026-08-06")


class TestOperativeOn(unittest.TestCase):
    def setUp(self):
        self.con = make_db()
        add(self.con, "2463/05", "2025-11-17")
        add(self.con, "2481/22", "2026-03-27")
        add(self.con, "2500/106", "2026-08-06")
        date(self.con, "2463/05", "effective", "2026-01-01")
        date(self.con, "2481/22", "effective", "2026-07-01")
        date(self.con, "2500/106", "sets_effective_date", "2026-10-01")
        ref(self.con, "2481/22", "2463/05", "rescinds")
        date(self.con, "2481/22", "rescind_effective", "2026-07-01")
        ref(self.con, "2500/106", "2481/22", "amends")
        resolve.resolve(self.con)
        self.tid = self.con.execute("SELECT thread_id FROM rule_thread").fetchone()["thread_id"]

    def _on(self, when):
        return {r["no"] for r in resolve.operative_on(self.con, self.tid, when)}

    def test_before_anything_takes_effect(self):
        self.assertEqual(self._on("2025-12-01"), set())

    def test_old_rule_alone(self):
        self.assertEqual(self._on("2026-05-01"), {"2463/05"})

    def test_old_rule_is_gone_once_rescission_bites(self):
        self.assertNotIn("2463/05", self._on("2026-07-02"))

    def test_new_format_not_operative_before_its_amended_date(self):
        # The whole point: on 09 Sep 2026 the new invoice format is NOT yet in
        # force, because 2500/106 moved it to October.
        self.assertNotIn("2481/22", self._on("2026-09-09"))

    def test_new_format_operative_after_october(self):
        self.assertIn("2481/22", self._on("2026-10-15"))


if __name__ == "__main__":
    unittest.main()
