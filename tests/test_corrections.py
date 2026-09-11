"""Tests for data/corrections.json handling.

Fixture strings are what the model actually wrote for 1933/14, whose schedule
item is "Any Bond or Mortgage for any definite and certain sum of money".
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import corrections, db, search

ACT = "Stamp Duty (Special Provisions) Act"
BONDS = "parties to bonds and mortgages that secure a definite and certain sum of money"
PARTIES = "parties to leases, transfers and other stampable instruments"

ENTRY = dict(no="1933/14", field="audience", **{"from": BONDS}, to=PARTIES,
             reason="Schedule item 07 is a bond or mortgage, a stampable instrument.")


class Grounding(unittest.TestCase):
    def test_the_word_match_alone_cannot_place_it(self):
        # The false positive this exists for. The model narrowed correctly and
        # the heuristic cannot tell.
        self.assertEqual(search.ground_audience(ACT, BONDS, no="1933/14", reviewed=()),
                         (None, "ungrounded"))

    def test_a_reviewed_placement_grounds_it(self):
        self.assertEqual(search.ground_audience(ACT, BONDS, no="1933/14", reviewed=(ENTRY,)),
                         (PARTIES, "reviewed"))

    def test_a_placement_is_for_one_gazette_only(self):
        # The same words on another gazette were not what the reviewer read.
        self.assertEqual(search.ground_audience(ACT, BONDS, no="1778/32", reviewed=(ENTRY,))[1],
                         "ungrounded")

    def test_a_correction_cannot_invent_an_audience(self):
        # The rule the model is held to holds for people too.
        bad = dict(ENTRY, to="everyone who owns property")
        with self.assertRaises(ValueError):
            search.ground_audience(ACT, BONDS, no="1933/14", reviewed=(bad,))


class Loading(unittest.TestCase):
    def write(self, entries):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "corrections.json")
        with open(p, "w") as f:
            json.dump(entries, f)
        corrections.load.cache_clear()
        return p

    def test_an_unsupported_field_is_an_error_not_a_no_op(self):
        # An entry that silently does nothing is worse than a failed build.
        with self.assertRaises(ValueError):
            corrections.load(self.write([dict(ENTRY, field="effective_date")]))

    def test_every_entry_needs_a_reason(self):
        with self.assertRaises(ValueError):
            corrections.load(self.write([dict(ENTRY, reason=" ")]))

    def test_no_file_means_no_corrections(self):
        corrections.load.cache_clear()
        self.assertEqual(corrections.load("/nonexistent/corrections.json"), ())


class Stale(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        db.init(self.con)
        self.con.execute("INSERT INTO gazette (no, year, published_date, title, source_url) "
                         "VALUES ('1933/14', 2015, '2015-09-21', 't', 'http://x')")

    def summarise(self, audience):
        self.con.execute("DELETE FROM gazette_summary")
        self.con.execute("INSERT INTO gazette_summary (no, model, summary, audience) "
                         "VALUES ('1933/14', 'm', 's', ?)", (json.dumps(audience),))

    def test_a_correction_that_still_matches_is_not_stale(self):
        self.summarise([BONDS, "notaries"])
        self.assertEqual(corrections.stale(self.con, (ENTRY,)), [])

    def test_a_resummarised_gazette_leaves_the_correction_stale(self):
        # The reviewer's decision was about a sentence that no longer exists.
        self.summarise(["mortgagors and mortgagees", "notaries"])
        self.assertEqual([e["no"] for e in corrections.stale(self.con, (ENTRY,))], ["1933/14"])


if __name__ == "__main__":
    unittest.main()
