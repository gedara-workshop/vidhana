"""Tests for the Phase 2 structuring pass.

None of these call the API — they exercise prompt construction and the accuracy
check, which is where the logic actually lives. The model call itself is a thin
wrapper and costs money to exercise.
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import db, structure


def make_db(tmp):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    with open(db.SCHEMA) as f:
        con.executescript(f.read())
    return con


def add(con, tmp, no, date, text, act="Value Added Tax Act", title="t", needs_ocr=0):
    path = os.path.join(tmp, no.replace("/", "-") + ".txt")
    with open(path, "w") as f:
        f.write(text)
    con.execute(
        "INSERT INTO gazette (no, year, published_date, title, source_url, enabling_act, "
        "enabling_act_no, text_path, needs_ocr) VALUES (?,?,?,?,?,?,?,?,?)",
        (no, int(date[:4]), date, title, "http://x", act, "14 of 2002", path, needs_ocr))


class TestPrompt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = make_db(self.tmp)

    def test_supplies_act_grounded_audience_candidates(self):
        # Phase 0: audience is absent from most documents, so it must be grounded
        # on the enabling Act rather than inferred freely.
        add(self.con, self.tmp, "2481/22", "2026-03-27", "body text")
        p = structure.build_prompt(self.con, "2481/22")
        self.assertIn("VAT-registered businesses", p)
        self.assertIn("do not invent", p)

    def test_unknown_act_lowers_confidence_instead_of_guessing(self):
        add(self.con, self.tmp, "9999/01", "2020-01-01", "body", act="Some Unmapped Act")
        p = structure.build_prompt(self.con, "9999/01")
        self.assertIn("No audience map for this Act", p)

    def test_includes_the_text_of_an_amending_gazette(self):
        """The 2500/106 case.

        Without the amending text the model can only summarise the document as
        published, which for 2481/22 means saying the invoice format starts in
        July when it was moved to October.
        """
        add(self.con, self.tmp, "2481/22", "2026-03-27", "effective from July 01, 2026")
        add(self.con, self.tmp, "2500/106", "2026-08-06",
            'The effective date of "July 01, 2026" is hereby amended as "October 01, 2026"')
        self.con.execute("INSERT INTO gazette_reference VALUES ('2500/106','2481/22','amends','')")
        p = structure.build_prompt(self.con, "2481/22")
        self.assertIn("October 01, 2026", p)
        self.assertIn("which amends this gazette", p)

    def test_flags_missing_image_content(self):
        # 1599/13 is a scan; 2414/14 and 2064/59 have rasterised form pages.
        add(self.con, self.tmp, "2414/14", "2024-12-11", "body", needs_ocr=1)
        self.assertIn("is an image and is missing", structure.build_prompt(self.con, "2414/14"))

    def test_unknown_gazette_raises(self):
        with self.assertRaises(KeyError):
            structure.build_prompt(self.con, "0000/00")


class TestAccuracyCheck(unittest.TestCase):
    """The check exists because PHASE0.md §6's reference summaries are Claude-written
    and were never hand-corrected, so they measure self-consistency. These fields
    are derived by regex from the source text and do not have that problem."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = make_db(self.tmp)
        add(self.con, self.tmp, "2443/30", "2025-07-01", "body")
        self.con.execute("UPDATE gazette SET effective_from='2025-10-01', "
                         "authority='Rukdevi Perpetua Himali Fernando' WHERE no='2443/30'")
        self.con.execute("INSERT INTO gazette_date VALUES "
                         "('2443/30','effective','2025-10-01','ctx')")

    def _summary(self, **kw):
        row = dict(no="2443/30", model="m", summary="s", audience="[]", obligation="obligation",
                   effective_date="2025-10-01", enabling_act="Value Added Tax Act",
                   authority="Rukdevi Perpetua Himali Fernando", tags="[]",
                   confidence="high", notes=None, generated_at="", input_tokens=1,
                   output_tokens=1)
        row.update(kw)
        self.con.execute(
            "INSERT OR REPLACE INTO gazette_summary VALUES "
            "(:no,:model,:summary,:audience,:obligation,:effective_date,:enabling_act,"
            ":authority,:tags,:confidence,:notes,:generated_at,:input_tokens,:output_tokens)", row)

    def test_agreement(self):
        self._summary()
        res = structure.check(self.con)
        self.assertEqual(res["effective_date"], (1, 1))
        self.assertEqual(res["authority"], (1, 1))

    def test_wrong_effective_date_is_caught(self):
        self._summary(effective_date="2025-07-01")
        self.assertEqual(structure.check(self.con)["effective_date"], (0, 1))

    def test_act_match_ignores_punctuation_and_case(self):
        self._summary(enabling_act="value added tax act")
        self.assertEqual(structure.check(self.con)["enabling_act"], (1, 1))

    def test_partial_name_still_counts(self):
        # Phase 1 reads the operative clause; the model may return the signature
        # block spelling. 1868/10 spells its own signatory two different ways.
        self._summary(authority="Himali Fernando")
        self.assertEqual(structure.check(self.con)["authority"], (1, 1))

    def test_effective_date_skipped_when_phase1_found_none(self):
        """Phase 1 falls back to the publication date when no date is stated.
        That fallback is a floor, not a claim, so it must not be graded."""
        self.con.execute("DELETE FROM gazette_date")
        self._summary()
        self.assertEqual(structure.check(self.con)["effective_date"], (0, 0))


if __name__ == "__main__":
    unittest.main()
