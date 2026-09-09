"""Tests for OCR post-processing and the migration helper.

`ocr_page` itself shells out to pdftoppm and tesseract, so it is exercised by the
real pipeline rather than here; these cover the logic around it.
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import db, ocr


class TestTidy(unittest.TestCase):
    def test_drops_vowelless_runs(self):
        # Tesseract renders the legacy-Sinhala half as consonant soup.
        out = ocr._tidy("Prtr I Sc rzd cndd\nThe Gazette of the Democratic Socialist Republic")
        self.assertIn("Gazette", out)
        self.assertNotIn("Prtr I Sc", out)

    def test_keeps_short_lines_with_real_words(self):
        self.assertIn("EXTRAORDINARY", ocr._tidy("EXTRAORDINARY"))

    def test_drops_stray_punctuation_lines(self):
        self.assertEqual(ocr._tidy("...\n|\n-"), "")

    def test_collapses_blank_runs(self):
        self.assertEqual(ocr._tidy("a real line\n\n\n\n\nanother real line"),
                         "a real line\n\nanother real line")

    def test_preserves_english_with_few_vowels_when_short(self):
        # "TIN" and similar are legitimate; the vowel test only applies to
        # longer runs so it cannot eat abbreviations.
        self.assertIn("TIN", ocr._tidy("TIN"))


class TestMarkers(unittest.TestCase):
    def test_markers_are_distinguishable(self):
        """OCR text is materially noisier than the text layer, so it must never
        be merged in silently — anything downstream has to be able to tell."""
        self.assertIn("OCR", ocr.BEGIN)
        self.assertIn("may contain errors", ocr.BEGIN)
        self.assertNotEqual(ocr.BEGIN, ocr.END)


class TestMigration(unittest.TestCase):
    def test_adds_a_missing_column_in_place(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE gazette_page (no TEXT, page INTEGER, chars INTEGER, "
                    "max_image_width INTEGER, needs_ocr INTEGER)")
        con.execute("INSERT INTO gazette_page VALUES ('1/1',1,10,0,0)")
        added = db.migrate(con)
        self.assertIn("gazette_page.ocr_chars", added)
        # existing data survives
        self.assertEqual(con.execute("SELECT chars FROM gazette_page").fetchone()["chars"], 10)

    def test_is_idempotent(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        with open(db.SCHEMA) as f:
            con.executescript(f.read())
        db.migrate(con)
        self.assertEqual(db.migrate(con), [])


class TestUnionOfKeys(unittest.TestCase):
    def test_ragged_rows_keep_every_column(self):
        """Only OCR'd pages carry ocr_chars. Taking the first row's keys dropped
        the column for any document whose page 1 needed no OCR."""
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        with open(db.SCHEMA) as f:
            con.executescript(f.read())
        con.execute("INSERT INTO gazette (no, year, published_date, title, source_url) "
                    "VALUES ('2414/14', 2024, '2024-12-11', 't', 'u')")
        db.replace_children(con, "gazette_page", "2414/14", [
            dict(no="2414/14", page=1, chars=1725, max_image_width=720, needs_ocr=0),
            dict(no="2414/14", page=7, chars=323, max_image_width=2811, needs_ocr=1,
                 ocr_chars=837),
        ])
        got = {r["page"]: r["ocr_chars"] for r in
               con.execute("SELECT page, ocr_chars FROM gazette_page")}
        self.assertEqual(got[7], 837)
        self.assertIsNone(got[1])


if __name__ == "__main__":
    unittest.main()
