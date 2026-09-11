"""Tests for corpus completeness and archive recovery.

The URL fixtures are real paths from the Internet Archive's snapshots of
documents.gov.lk, including the malformed one that caused a Provincial Councils
Elections gazette to be ingested as an IRD tax gazette.
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import archive, db


class NumberMatching(unittest.TestCase):
    """The bug this class exists for: asking for 1439/01 also probes the
    unpadded `1439-1`, and the CDX filter is a regex over the whole URL, so
    `1439-19` and `1439-10` match it. Acceptance must be exact."""

    def accepts(self, no, url):
        n, s = archive._norm(no)
        want = (int(n), int(s))
        claims = archive._numbers(url)
        return bool(claims) and all(c == want for c in claims)

    def test_exact_match_is_accepted(self):
        self.assertTrue(self.accepts(
            "1791/08", "http://documents.gov.lk/files/egz/2012/12/1791-08_E.pdf"))
        self.assertTrue(self.accepts(
            "1447/42", "http://documents.gov.lk/Extgzt/2006/Pdf/Jun/1447-42/1447-42E.pdf"))

    def test_unpadded_prefix_collision_is_rejected(self):
        # 1439/01 must not match 1439-19 or 1439-10.
        for other in ("1439-19", "1439-10", "1439-12"):
            url = f"http://documents.gov.lk/Extgzt/2006/Pdf/Mar/{other}/{other}e.pdf"
            self.assertFalse(self.accepts("1439/01", url), other)

    def test_directory_and_filename_must_agree(self):
        # A real archive path where the two disagree. Trusting either alone
        # ingests the wrong gazette.
        url = ("http://www.documents.gov.lk/old/gazette/forms/Extgzt/2006/Pdf/"
               "Mar/1439-19/1436-19e.pdf")
        self.assertEqual(archive._numbers(url), [(1439, 19), (1436, 19)])
        self.assertFalse(self.accepts("1439/19", url))
        self.assertFalse(self.accepts("1436/19", url))

    def test_zero_padding_is_irrelevant_to_equality(self):
        self.assertTrue(self.accepts(
            "1791/08", "http://documents.gov.lk/files/egz/2012/12/1791-8_E.pdf"))

    def test_non_gazette_urls_claim_nothing(self):
        for url in ("http://documents.gov.lk/index.html",
                    "http://documents.gov.lk/files/act/1980/1/01-1980_E.pdf"):
            self.assertEqual(archive._numbers(url), [])


class Missing(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        db.init(self.con)
        for no, date in (("1439/03", "2006-04-03"), ("2500/106", "2026-08-06")):
            self.con.execute(
                "INSERT INTO gazette (no, year, published_date, title, source_url) "
                "VALUES (?,?,?,?,?)", (no, int(date[:4]), date, "t", "http://x"))
        for src, dst, rel in (("1439/03", "224/03", "rescinds"),      # pre-listing
                              ("2500/106", "1791/08", "amends"),      # in range
                              ("2500/106", "1439/03", "amends")):     # held
            self.con.execute("INSERT INTO gazette_reference (src_no, dst_no, relation) "
                             "VALUES (?,?,?)", (src, dst, rel))

    def test_only_unheld_references_are_reported(self):
        self.assertEqual(sorted(m["no"] for m in archive.missing(self.con)),
                         ["1791/08", "224/03"])

    def test_in_range_is_distinguished_from_pre_listing(self):
        # Outside the covered range is expected and unfixable from this source;
        # inside it is a defect in the listing. Conflating them would report the
        # IRD as sound or as far worse than it is, depending which way you lean.
        by_no = {m["no"]: m for m in archive.missing(self.con)}
        self.assertTrue(by_no["1791/08"]["in_range"])
        self.assertFalse(by_no["224/03"]["in_range"])


class Provenance(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        db.init(self.con)

    def test_listing_documents_are_the_default(self):
        self.con.execute(
            "INSERT INTO gazette (no, year, published_date, title, source_url) "
            "VALUES ('2500/106',2026,'2026-08-06','t','http://x')")
        self.assertEqual(self.con.execute(
            "SELECT source FROM gazette WHERE no='2500/106'").fetchone()[0], "ird-listing")

    def test_recovered_documents_stay_distinguishable(self):
        db.upsert_gazette(self.con, dict(
            no="1791/08", year=2012, published_date="2012-12-31", title="t",
            source_url="http://web.archive.org/…", source="web-archive",
            source_detail="…/1791-08_E.pdf @ 20230126031356"))
        r = self.con.execute("SELECT source, source_detail FROM gazette "
                             "WHERE no='1791/08'").fetchone()
        self.assertEqual(r["source"], "web-archive")
        self.assertIn("1791-08", r["source_detail"])


def _recovered(con, no, original, ts, sha):
    db.upsert_gazette(con, dict(
        no=no, year=2006, published_date="2006-04-03", title="t",
        source_url=archive.WAYBACK.format(ts=ts, url=original),
        source="web-archive", source_detail=f"{original} @ {ts}"))
    con.execute("UPDATE gazette SET pdf_sha256=? WHERE no=?", (sha, no))


class Record(unittest.TestCase):
    """The tracked record of recoveries. It exists because the first unattended
    nightly run, on a cold database, could not see the seven recovered gazettes
    and silently dropped them from the published corpus."""

    ORIG = "http://www.documents.gov.lk/old/gazette/forms/Extgzt/2006/Pdf/Apr/1439-1/1439-1e.pdf"

    def setUp(self):
        import tempfile
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        db.init(self.con)
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "recovered.json")

    def test_records_what_is_needed_to_fetch_it_again(self):
        _recovered(self.con, "1439/01", self.ORIG, "20241121131244", "478346d4")
        archive.export_recovered(self.con, self.path)
        [rec] = archive.load_recovered(self.path)
        self.assertEqual(rec, dict(no="1439/01", original=self.ORIG,
                                   timestamp="20241121131244", sha256="478346d4"))
        # The snapshot is rebuilt from the record, not searched for: an `if_`
        # capture at a fixed timestamp is immutable.
        self.assertEqual(archive.snapshot_of(rec)["snapshot"],
                         f"https://web.archive.org/web/20241121131244if_/{self.ORIG}")

    def test_never_prunes_a_recovery_the_database_does_not_hold(self):
        # This is the cold-rebuild state exactly: the record lists a gazette the
        # fresh database has not re-acquired yet. Pruning on that basis is the
        # bug the record exists to fix.
        _recovered(self.con, "1439/01", self.ORIG, "20241121131244", "478346d4")
        archive.export_recovered(self.con, self.path)
        empty = sqlite3.connect(":memory:"); empty.row_factory = sqlite3.Row
        db.init(empty)
        r = archive.export_recovered(empty, self.path)
        self.assertEqual(r["total"], 1)
        self.assertEqual([x["no"] for x in archive.load_recovered(self.path)], ["1439/01"])

    def test_listing_documents_are_not_recorded(self):
        self.con.execute(
            "INSERT INTO gazette (no, year, published_date, title, source_url, pdf_sha256) "
            "VALUES ('2500/106',2026,'2026-08-06','t','http://x','abc')")
        self.assertEqual(archive.export_recovered(self.con, self.path)["total"], 0)

    def test_output_is_stable(self):
        # Sorted and byte-identical on re-export, so the file only ever shows a
        # diff when a recovery actually changed.
        _recovered(self.con, "1791/08", "http://documents.gov.lk/files/egz/2012/12/1791-08_E.pdf",
                   "20230126031356", "fafbf395")
        _recovered(self.con, "1439/01", self.ORIG, "20241121131244", "478346d4")
        archive.export_recovered(self.con, self.path)
        first = open(self.path).read()
        r = archive.export_recovered(self.con, self.path)
        self.assertEqual(open(self.path).read(), first)
        self.assertEqual(r["added"], 0)
        self.assertEqual([x["no"] for x in archive.load_recovered(self.path)],
                         ["1439/01", "1791/08"])


class Unavailable(unittest.TestCase):
    """ae2d2cd deleted this class by accident while adding `_numbers`, leaving
    every `raise ArchiveUnavailable` in place. A rate-limited lookup then died
    with NameError instead of being reported as a lookup failure, and nothing
    noticed because nothing was rate-limited in between."""

    def test_an_exhausted_retry_raises_the_documented_error(self):
        import urllib.request
        saved = urllib.request.urlopen

        def refuse(*a, **k):
            raise OSError("429 Too Many Requests")
        urllib.request.urlopen = refuse
        try:
            with self.assertRaises(archive.ArchiveUnavailable):
                archive._get("http://web.archive.org/x", attempts=1)
        finally:
            urllib.request.urlopen = saved
