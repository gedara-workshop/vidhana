"""Tests for pre-answered rule questions.

The fixture is the tax-invoice rule as the corpus holds it: 2463/05, then
2481/22 prescribing the new format from July 1, 2026, then 2500/106 moving
that date to October 1, 2026. It is the example the README opens with, and
the one where an answer written from a single document is wrong.
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import answers, db, resolve


def corpus():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db.init(con)
    for no, pub in (("2463/05", "2025-11-17"), ("2481/22", "2026-03-27"), ("2500/106", "2026-08-06")):
        con.execute("INSERT INTO gazette (no, year, published_date, title, source_url, subject, "
                    "pdf_sha256) VALUES (?,?,?,?,?,?,?)",
                    (no, int(pub[:4]), pub, "Tax invoice", "http://x", "vat", "sha-" + no))
    for src, dst, rel in (("2481/22", "2463/05", "rescinds"), ("2500/106", "2481/22", "amends")):
        con.execute("INSERT INTO gazette_reference (src_no, dst_no, relation) VALUES (?,?,?)",
                    (src, dst, rel))
    for no, kind, d in (("2481/22", "effective", "2026-07-01"),
                        ("2481/22", "rescind_effective", "2026-07-01"),
                        ("2500/106", "sets_effective_date", "2026-10-01"),
                        ("2500/106", "replaces_effective_date", "2026-07-01")):
        con.execute("INSERT INTO gazette_date (no, kind, date, context) VALUES (?,?,?,'')",
                    (no, kind, d))
    resolve.resolve(con)
    return con


GOOD = [
    dict(question="From when must VAT-registered businesses use the new tax invoice format?",
         answer="From 1 October 2026. Gazette 2481/22 set 1 July 2026, and 2500/106 moved it "
                "to 1 October 2026.",
         cites=["2481/22", "2500/106"]),
    dict(question="Does the 2025 invoice notice still apply?",
         answer="No. 2463/05 is rescinded by 2481/22 from 1 July 2026.",
         cites=["2463/05", "2481/22"]),
    dict(question="Which document sets the invoice format now?",
         answer="2481/22, as amended by 2500/106.",
         cites=["2481/22", "2500/106"]),
]


class Verify(unittest.TestCase):
    def setUp(self):
        self.con = corpus()
        self.root = self.con.execute("SELECT root_no FROM rule_thread").fetchone()[0]

    def problems(self, qs):
        return answers.verify(self.con, self.root, qs)

    def test_a_faithful_set_passes(self):
        self.assertEqual(self.problems(GOOD), [])

    def test_a_date_no_document_contains_is_refused(self):
        # The failure that matters most: a plausible, invented date.
        bad = [dict(GOOD[0], answer="From 1 September 2026, per 2500/106.")] + GOOD[1:]
        self.assertTrue(any("2026-09-01" in p for p in self.problems(bad)))

    def test_citing_a_gazette_outside_the_rule_is_refused(self):
        bad = [dict(GOOD[0], cites=["2500/106", "2429/39"])] + GOOD[1:]
        self.assertTrue(any("2429/39" in p and "not part of this rule" in p
                            for p in self.problems(bad)))

    def test_mentioning_an_unrelated_gazette_is_refused(self):
        bad = [dict(GOOD[0], answer="From 1 October 2026, as 2312/73 also says.")] + GOOD[1:]
        self.assertTrue(any("2312/73" in p for p in self.problems(bad)))

    def test_the_current_document_must_be_cited(self):
        # An answer set built only from superseded documents is the README's
        # failure: telling someone July when it is October.
        stale = [dict(q, cites=[c for c in q["cites"] if c != "2500/106"] or ["2463/05"])
                 for q in GOOD]
        self.assertTrue(any("never cited" in p for p in self.problems(stale)))

    def test_wording_that_goes_stale_on_its_own_is_refused(self):
        bad = [dict(GOOD[0], answer="Businesses will need the new format from 1 October "
                                    "2026 (2500/106).")] + GOOD[1:]
        self.assertTrue(any("'will'" in p for p in self.problems(bad)))

    def test_too_few_questions_is_refused(self):
        self.assertTrue(any("questions" in p for p in self.problems(GOOD[:2])))


class Staleness(unittest.TestCase):
    def setUp(self):
        self.con = corpus()
        self.root = self.con.execute("SELECT root_no FROM rule_thread").fetchone()[0]
        self.path = os.path.join(tempfile.mkdtemp(), "answers.json")
        answers.save({self.root: dict(rule=self.root, basis=answers.basis(self.con, self.root),
                                      model="m", generated_at="t", questions=GOOD)}, self.path)

    def test_a_current_passing_set_is_published(self):
        self.assertIn(self.root, answers.publishable(self.con, self.path))

    def test_a_new_amendment_hides_the_answers_until_regenerated(self):
        # The whole product is currency. An answer written before the rule
        # changed must not be shown after it.
        self.con.execute("INSERT INTO gazette (no, year, published_date, title, source_url, "
                         "subject, pdf_sha256) VALUES ('2510/01',2026,'2026-09-30','t','x','vat','s')")
        self.con.execute("INSERT INTO gazette_reference (src_no, dst_no, relation) "
                         "VALUES ('2510/01','2481/22','amends')")
        resolve.resolve(self.con)
        self.assertEqual(answers.publishable(self.con, self.path), {})

    def test_the_fingerprint_ignores_nothing_that_matters(self):
        before = answers.basis(self.con, self.root)
        self.con.execute("UPDATE gazette SET pdf_sha256='replaced' WHERE no='2481/22'")
        self.assertNotEqual(answers.basis(self.con, self.root), before)

    def test_the_fingerprint_is_stable_when_nothing_changed(self):
        self.assertEqual(answers.basis(self.con, self.root), answers.basis(self.con, self.root))


if __name__ == "__main__":
    unittest.main()
