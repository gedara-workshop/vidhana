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


class TestStore(unittest.TestCase):
    """Raw OCR is tracked in data/ocr.json because tesseract on the CI runner
    and tesseract on a Mac read the same page differently, and the nightly job
    committed that difference as a change to the corpus. Tesseract is faked:
    what is under test is when it is allowed to run."""

    RAW = "No. 1599/13 - TUESDAY, APRIL 28, 2009\n\nfad I, Sahampathi Angammana, Commissioner"

    def setUp(self):
        import tempfile
        self.path = os.path.join(tempfile.mkdtemp(), "ocr.json")
        self.calls = []
        self.saved = (ocr._tesseract, ocr.engine)

        def fake(pdf, page, dpi=ocr.DPI, lang=ocr.LANG):
            self.calls.append((pdf, page))
            return self.RAW
        ocr._tesseract, ocr.engine = fake, lambda *a, **k: "tesseract 5.5.2, eng, 300dpi"

    def tearDown(self):
        ocr._tesseract, ocr.engine = self.saved

    def test_a_page_is_read_once_and_then_always_comes_from_the_store(self):
        first = ocr.read_page("x.pdf", "abc", "1599/13", 1, self.path)
        second = ocr.read_page("x.pdf", "abc", "1599/13", 1, self.path)
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), 1)

    def test_the_stored_text_is_raw_so_the_tidy_can_improve_later(self):
        ocr.read_page("x.pdf", "abc", "1599/13", 1, self.path)
        [rec] = ocr.load_store(self.path).values()
        self.assertEqual(rec["text"], self.RAW)
        self.assertEqual(rec["engine"], "tesseract 5.5.2, eng, 300dpi")

    def test_a_changed_pdf_is_read_afresh(self):
        # Keyed by content, not by gazette number: if the IRD replaces a PDF,
        # the old reading must not be reused for the new document.
        ocr.read_page("x.pdf", "abc", "1599/13", 1, self.path)
        ocr.read_page("x.pdf", "def", "1599/13", 1, self.path)
        self.assertEqual(len(self.calls), 2)

    def test_a_machine_without_tesseract_builds_from_the_store(self):
        ocr.read_page("x.pdf", "abc", "1599/13", 1, self.path)
        ocr._tesseract = lambda *a, **k: None
        self.assertIn("Sahampathi Angammana", ocr.read_page("x.pdf", "abc", "1599/13", 1, self.path))

    def test_a_failed_read_records_nothing(self):
        # Otherwise an empty reading would be cached and never retried.
        ocr._tesseract = lambda *a, **k: None
        self.assertEqual(ocr.read_page("x.pdf", "abc", "1599/13", 1, self.path), "")
        self.assertEqual(ocr.load_store(self.path), {})


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
