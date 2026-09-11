"""Regression tests for the acquisition parsers.

Every case here is a real string from a real gazette. Where a case looks odd it
is because the source document is odd, and the comment says which one.

Run: python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import extract, parse
from vidhana.util import normalise_no, parse_date


class TestNormalise(unittest.TestCase):
    def test_zero_padding(self):
        # The listing pads, the PDF header does not. Without normalising, five of
        # the twelve references in the Phase 0 sample fail to connect.
        self.assertEqual(normalise_no("2217/7"), "2217/07")
        self.assertEqual(normalise_no("1487/3"), "1487/03")
        self.assertEqual(normalise_no("2217/07"), "2217/07")

    def test_three_digit_suffix(self):
        self.assertEqual(normalise_no("2500/106"), "2500/106")

    def test_dollar_separator(self):
        # The legacy-font Sinhala line writes '$' where English writes '/'.
        self.assertEqual(normalise_no("2295$10"), "2295/10")

    def test_rejects_non_numbers(self):
        for bad in ("", "rubbish", "20/02/2024", "No. 12 of 2006"):
            self.assertIsNone(normalise_no(bad), bad)


class TestDates(unittest.TestCase):
    def test_corpus_shapes(self):
        cases = {
            "06 Aug 2026": "2026-08-06",
            "THURSDAY, AUGUST 06, 2026": "2026-08-06",
            "thursday, april 04, 2024": "2024-04-04",     # 2378/33 prints lowercase
            "SUNDAY, APRIL 01 2018": "2018-04-01",        # 2064/54 omits the comma
            "2024'12'11": "2024-12-11",
            "11.12.2024": "2024-12-11",
            "01st April, 2018": "2018-04-01",
            "November 13, 2025": "2025-11-13",
        }
        for raw, iso in cases.items():
            self.assertEqual(parse_date(raw), iso, raw)

    def test_impossible_date_is_rejected(self):
        self.assertIsNone(parse_date("FEBRUARY 30, 2024"))


class TestHeader(unittest.TestCase):
    def test_tolerates_real_variants(self):
        # A naive ^No\. (\S+) - (.+, \d{4})$ matches only 19 of the 21 sampled
        # documents. These are the two it misses, plus the em dash and casing.
        cases = {
            "No. 2456 /02 - MONDAY, SEPTEMBER 29, 2025": ("2456/02", "2025-09-29"),
            "No. 2064/54 - SUNDAY, APRIL 01 2018": ("2064/54", "2018-04-01"),
            "No. 1868/10 — MONDAY, JUNE 23, 2014": ("1868/10", "2014-06-23"),
            "  No. 2429/39 - thursday, march 27, 2025  ": ("2429/39", "2025-03-27"),
        }
        for line, expected in cases.items():
            self.assertEqual(parse.header(line), expected, line)


class TestLegacySinhala(unittest.TestCase):
    def test_detects_both_encodings(self):
        for line in (
            "Y%S ,xld m%cd;dka;%sl iudcjd§ ckrcfha .eiÜ m;%h",   # 2011+ font
            "Êòé Èâ¨å Àò°åºå¾àºòè¨ ÌÄå°Éå¼û °¾Ç°ïÆà ªæÌ ÀºòÆ",     # 2007-era font
            "w;s úfYI",
            "wxl 2334$21 - 2023 uehs ui 31 jeks nodod - 2023'05'31",  # no accents at all
        ):
            self.assertTrue(extract.is_legacy_sinhala(line), line)

    def test_keeps_english_legal_prose(self):
        # Semicolons and ampersands are everywhere in this corpus; they must not
        # by themselves mark a line as Sinhala.
        for line in (
            "(b) is an individual registered as an auditor under the Companies "
            "(Auditors) Regulations ; or",
            "BY virtue of the powers vested in me under section 20 of the Value Added Tax Act,",
            "Cybersecurity Services: Threat detection, firewall protection, and data encryption,",
            "Colombo 02.",
        ):
            self.assertFalse(extract.is_legacy_sinhala(line), line)


class TestRelations(unittest.TestCase):
    def _rel(self, text, dst="2463/05"):
        refs = {r["dst_no"]: r["relation"] for r in parse.references(text)}
        return refs.get(dst)

    def test_verb_after_the_reference(self):
        # 2456/02 and 2481/22 both put the verb after the citation.
        self.assertEqual(self._rel(
            "The format and specifications issued under Gazette Notification No. 2463/05 "
            "dated November 17, 2025 shall remain optional and are hereby rescinded with "
            "effect from July 01, 2026."), "rescinds")

    def test_previous_sentence_does_not_leak(self):
        # The real 2481/22 text: the sentence before the reference contains
        # "may amend ...", which must not type this edge as `amends`.
        self.assertEqual(self._rel(
            "The Commissioner General may amend the format and specification of the Tax "
            "Invoice from time to time as required. The format and specifications issued "
            "under Gazette Notification No. 2463/05 dated November 17, 2025 are hereby "
            "rescinded with effect from July 01, 2026."), "rescinds")

    def test_last_amended_by_beats_amends(self):
        # One sentence, two references, two different relations (2312/73, 2429/39).
        text = ("do by this Order amend the order made under that Section and published in "
                "Extraordinary Gazette Notificaiton No. 1465/20 dated October 05, 2006, as "
                "last amended by the Extraordinary Gazette Notificaiton No. 2149/18 dated "
                "November 14, 2019, by the addition of the following new item.")
        refs = {r["dst_no"]: r["relation"] for r in parse.references(text)}
        self.assertEqual(refs["1465/20"], "amends")
        self.assertEqual(refs["2149/18"], "last_amended_by")

    def test_misspelled_notification_still_matches(self):
        # "Notificaiton" (2312/73) and "Notificiaton" (2149/18) are in the source.
        for spelling in ("Notification", "Notificaiton", "Notificiaton"):
            refs = parse.references(f"amend the order published in Gazette {spelling} No. 2104/4")
            self.assertEqual([r["dst_no"] for r in refs], ["2104/04"], spelling)

    def test_self_reference_is_dropped(self):
        self.assertEqual(parse.references("No. 2481/22 - FRIDAY", self_no="2481/22"), [])


class TestDateTyping(unittest.TestCase):
    def _kinds(self, text):
        return {(d["kind"], d["date"]) for d in parse.dates(text)}

    def test_retroactive_effective_date(self):
        # 2316/13: published Jan 2023, effective Oct 2022.
        self.assertIn(("effective", "2022-10-01"),
                      self._kinds("These Regulations operate effective from October 01, 2022 "
                                  "and rescind the Regulations published earlier."))

    def test_two_effective_dates_in_one_document(self):
        # 2334/21 Part A / Part B, seven months apart.
        kinds = self._kinds("Part - A With effect from June 01, 2023; i. Practitioners "
                            "registered with the Council. Part - B With effect from "
                            "January 01, 2024, any individual who does not belong to Part A.")
        self.assertIn(("effective", "2023-06-01"), kinds)
        self.assertIn(("effective", "2024-01-01"), kinds)

    def test_the_operative_clause_is_typed_apart(self):
        # 1791/08, verbatim. The official's own act carries the document's date.
        kinds = self._kinds(
            "BY virtue of the powers vested in me under Sub - section (1) of Section 2 of "
            "the Finance Act, No. 25 of 2003, I, Mahinda Rajapaksa, Minister of Finance and "
            "planning do by this Order determine that with effect from January 1, 2013 there "
            "shall be charged and levied from the persons specified")
        self.assertIn(("operative", "2013-01-01"), kinds)
        self.assertNotIn(("effective", "2013-01-01"), kinds)

    def test_a_reproduced_instruments_commencement_is_not_operative(self):
        # Later in 1791/08: regulations reproduced in full, with their own 2003
        # commencement. Still an effective date — of those regulations — so it
        # is kept, but it must not be mistaken for the order's.
        kinds = self._kinds(
            "1. These regulations may be cited as the Embarkation Levy (Airlines) Regulations, "
            "No. 01 of 2003 Short title and date of and shall come into operation on "
            "September 1, 2003.")
        self.assertIn(("effective", "2003-09-01"), kinds)
        self.assertNotIn(("operative", "2003-09-01"), kinds)

    def test_the_operative_clause_reaches_past_a_long_preamble(self):
        # 1868/10, verbatim: 230 characters between "do by this order" and the
        # date, and the document names its schedule dates as exceptions.
        kinds = self._kinds(
            "I, Mallika Samarasekara, Commissioner General of Inland Revenue do by this order "
            "specify matters relating to and the manner in which tax is calculated in respect "
            "of Value Added Tax on Supply of Financial Services (hereinafter referred as VAT on "
            "Supply of Financial Services) as set out in the Schedule hereto with effect from "
            "01.01.2014 subject to the specific dates mentioned in the Schedule")
        self.assertIn(("operative", "2014-01-01"), kinds)

    def test_midnight_starts_the_next_day(self):
        # 1478/08, verbatim, including "mid night" and the date given twice.
        kinds = self._kinds(
            "I, Mahinda Rajapaksa, President of the Democratic Socialist Republic of Sri "
            "Lanka, do by this Order, amend with effect from the mid night of 31st December, "
            "2006/1st January, 2007, the Order made under the said Section")
        self.assertEqual({d for k, d in kinds if k == "operative"}, {"2007-01-01"})

    def test_midnight_does_not_move_a_deadline(self):
        # "on or before midnight of" a day is the end of that day, not the
        # start of the next. Only dates things take effect from are shifted.
        kinds = self._kinds("and furnish the return on or before midnight of 30th June, 2025.")
        self.assertNotIn(("deadline", "2025-07-01"), kinds)

    def test_rescission_date_is_distinct_from_effective(self):
        kinds = self._kinds("are hereby rescinded with effect from July 01, 2026.")
        self.assertIn(("rescind_effective", "2026-07-01"), kinds)

    def test_deadline(self):
        self.assertIn(("deadline", "2025-10-15"),
                      self._kinds("using e-Service on or before October 15, 2025 in order to "
                                  "get the approval."))

    def test_metadata_only_amendment_form(self):
        """2500/106 sets a date on *another* gazette rather than on itself.

        Neither date here is this document's own effective date, so neither is
        typed `effective`: October is the value it sets on 2481/22, July is the
        value it replaces. The resolver propagates the former onto the target.
        """
        kinds = self._kinds('1. The effective date of \u201cJuly 01, 2026\u201d, is hereby '
                            'amended as \u201cOctober 01, 2026\u201d;')
        self.assertIn(("sets_effective_date", "2026-10-01"), kinds)
        self.assertIn(("replaces_effective_date", "2026-07-01"), kinds)
        self.assertNotIn(("effective", "2026-10-01"), kinds)


class TestSubject(unittest.TestCase):
    def test_classifies_from_act_not_title(self):
        # 34 of 137 listing titles say nothing about subject matter.
        self.assertEqual(parse.subject("Value Added Tax Act",
                                       "Notice under Paragraph 10 of Sixth Schedule"), "vat")
        self.assertEqual(parse.subject("Casino Business (Regulation) Act", ""), "betting-gaming")
        self.assertEqual(parse.subject(None, ""), "other")


if __name__ == "__main__":
    unittest.main()
