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
class Restore(unittest.TestCase):
    """Re-acquiring recorded recoveries on a cold rebuild. Network and the
    pipeline are faked: what is under test is which document is allowed into
    the database, and what happens when the archive does not cooperate."""

    GOOD = b"%PDF-1.4 the gazette we verified"
    SHA = __import__("hashlib").sha256(GOOD).hexdigest()

    def setUp(self):
        import json, tempfile
        from vidhana import pipeline
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        db.init(self.con)
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "recovered.json")
        with open(self.path, "w") as f:
            json.dump([dict(no="1791/08", original="http://documents.gov.lk/files/egz/2012/12/1791-08_E.pdf",
                            timestamp="20230126031356", sha256=self.SHA)], f)
        self.calls = []
        self.served = self.GOOD
        self.saved = (archive._get, archive.backfill, pipeline.PDF_DIR, pipeline.TEXT_DIR)
        pipeline.PDF_DIR = os.path.join(self.dir, "pdf")
        pipeline.TEXT_DIR = os.path.join(self.dir, "text")

        def fake_get(url, timeout=60, attempts=3):
            self.calls.append(url)
            if isinstance(self.served, Exception):
                raise self.served
            return self.served

        def fake_backfill(con, no, snapshot=None, use_ocr=True):
            db.upsert_gazette(con, dict(no=no, year=2012, published_date="2012-12-31",
                                        title="t", source_url=snapshot["snapshot"],
                                        source="web-archive"))
            return dict(no=no, status="recovered")

        archive._get, archive.backfill = fake_get, fake_backfill

    def tearDown(self):
        from vidhana import pipeline
        archive._get, archive.backfill, pipeline.PDF_DIR, pipeline.TEXT_DIR = self.saved

    def pdf(self):
        from vidhana import pipeline
        from vidhana.fetch import pdf_path
        return pdf_path(pipeline.PDF_DIR, "1791/08")

    def held(self):
        return bool(self.con.execute("SELECT 1 FROM gazette WHERE no='1791/08'").fetchone())

    def test_a_cold_rebuild_gets_the_document_back(self):
        [r] = archive.restore(self.con, self.path)
        self.assertEqual(r["status"], "recovered")
        self.assertTrue(self.held())
        # By exact snapshot URL — never a CDX search.
        self.assertEqual(self.calls, [
            "https://web.archive.org/web/20230126031356if_/"
            "http://documents.gov.lk/files/egz/2012/12/1791-08_E.pdf"])

    def test_a_document_that_is_not_the_verified_one_never_reaches_the_database(self):
        self.served = b"%PDF-1.4 something else entirely"
        [r] = archive.restore(self.con, self.path)
        self.assertEqual(r["status"], "hash mismatch")
        self.assertFalse(self.held())
        self.assertFalse(os.path.exists(self.pdf()), "a foreign PDF was left in the cache")

    def test_an_unreachable_archive_is_reported_not_swallowed(self):
        self.served = archive.ArchiveUnavailable("429 Too Many Requests")
        [r] = archive.restore(self.con, self.path)
        self.assertEqual(r["status"], "unavailable")
        self.assertFalse(self.held())

    def test_a_verified_cached_pdf_costs_no_request(self):
        os.makedirs(os.path.dirname(self.pdf()), exist_ok=True)
        with open(self.pdf(), "wb") as f:
            f.write(self.GOOD)
        [r] = archive.restore(self.con, self.path)
        self.assertEqual(r["status"], "recovered")
        self.assertEqual(self.calls, [])

    def test_a_stale_cached_pdf_is_replaced_rather_than_trusted(self):
        # fetch.ensure skips any file that exists, so a wrong one left in the
        # CI cache would otherwise be ingested as if it were right.
        os.makedirs(os.path.dirname(self.pdf()), exist_ok=True)
        with open(self.pdf(), "wb") as f:
            f.write(b"%PDF-1.4 stale")
        archive.restore(self.con, self.path)
        self.assertEqual(len(self.calls), 1)
        with open(self.pdf(), "rb") as f:
            self.assertEqual(f.read(), self.GOOD)

    def test_a_gazette_the_listing_now_carries_is_left_to_the_listing(self):
        self.con.execute(
            "INSERT INTO gazette (no, year, published_date, title, source_url) "
            "VALUES ('1791/08',2012,'2012-12-31','t','http://ird')")
        [r] = archive.restore(self.con, self.path)
        self.assertEqual(r["status"], "already held")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.con.execute(
            "SELECT source FROM gazette WHERE no='1791/08'").fetchone()[0], "ird-listing")

    def test_a_pipeline_failure_leaves_no_half_ingested_row(self):
        def boom(con, no, snapshot=None, use_ocr=True):
            db.upsert_gazette(con, dict(no=no, year=2012, published_date="2012-01-01",
                                        title="placeholder", source_url="x", source="web-archive"))
            raise RuntimeError("pdftotext exploded")
        archive.backfill = boom
        [r] = archive.restore(self.con, self.path)
        self.assertEqual(r["status"], "failed")
        self.assertFalse(self.held(), "a placeholder row survived a failed restore")
