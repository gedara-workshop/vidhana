"""Tests for Phase 3 search.

Fixtures are real strings from the corpus — real tags as the model wrote them,
real audience sentences, the real tax-invoice thread — because the whole design
question here is what the model's actual output looks like, not what a tidy
example would look like.
"""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import db, resolve, search


class TagNormalisation(unittest.TestCase):
    def test_alias_folds_abbreviations(self):
        self.assertEqual(search.tag_key("vat"), "value-added-tax")
        self.assertEqual(search.tag_key("VAT"), "value-added-tax")

    def test_plural_folds_on_the_final_token_only(self):
        self.assertEqual(search.tag_key("tax-rates"), search.tag_key("tax-rate"))
        self.assertEqual(search.tag_key("tax-exemptions"), "tax-exemption")
        self.assertEqual(search.tag_key("notaries"), "notary")
        self.assertEqual(search.tag_key("supplies"), "supply")

    def test_plural_inside_a_tag_is_left_alone(self):
        # `debits-tax` is the Act's own name. Folding every token would turn it
        # into `debit-tax` by accident; the alias map handles that pair instead.
        self.assertEqual(search.tag_key("debits-tax"), "debits-tax")
        self.assertEqual(search.tag_key("debit-tax"), "debits-tax")

    def test_short_words_and_double_s_survive(self):
        self.assertEqual(search.tag_key("gas"), "gas")
        self.assertEqual(search.tag_key("business"), "business")

    def test_display_form_is_the_most_used_variant(self):
        raws = ["tax-rates", "tax-rates", "tax-rate", "notaries"]
        canon = search.canonical_tags(raws)
        self.assertEqual(canon["tax-rate"], "tax-rates")
        self.assertEqual(canon["notary"], "notaries")

    def test_display_form_breaks_ties_alphabetically(self):
        # Not by row order — facets must not change when a document is re-summarised.
        a = search.canonical_tags(["tax-rate", "tax-rates"])
        b = search.canonical_tags(["tax-rates", "tax-rate"])
        self.assertEqual(a, b)


class AudienceGrounding(unittest.TestCase):
    def test_narrowing_grounds_to_its_candidate(self):
        coarse, why = search.ground_audience(
            "Value Added Tax Act", "VAT-registered businesses importing the listed goods")
        self.assertEqual(why, "grounded")
        self.assertEqual(coarse, "VAT-registered businesses")

    def test_narrowing_that_swaps_the_head_noun_still_grounds(self):
        coarse, why = search.ground_audience(
            "Value Added Tax Act", "VAT-registered wholesalers and retailers")
        self.assertEqual((coarse, why), ("VAT-registered businesses", "grounded"))

    def test_one_branch_of_an_enumerated_candidate_grounds(self):
        # The Stamp Duty candidate lists three kinds of instrument; a narrowing
        # keeps one and drops the rest, so a half-the-words rule would reject
        # exactly the documents that obeyed the instruction.
        coarse, why = search.ground_audience(
            "Stamp Duty (Special Provisions) Act",
            "parties to qualifying leases of land within the Colombo Port City area")
        self.assertEqual(why, "grounded")
        self.assertIn("parties to", coarse)

    def test_unrelated_audience_does_not_ground(self):
        coarse, why = search.ground_audience("Value Added Tax Act", "Samurdhi Authority")
        self.assertEqual((coarse, why), (None, "ungrounded"))

    def test_act_name_typo_in_the_source_falls_back_to_subject(self):
        # "Value Addded Tax Act" is a real typo in a real gazette. Substring
        # lookup misses it; the subject classification does not.
        self.assertEqual(
            search.ground_audience("Value Addded Tax Act", "VAT-registered businesses"),
            (None, "no-map"))
        self.assertEqual(
            search.ground_audience("Value Addded Tax Act", "VAT-registered businesses",
                                   subject="vat"),
            ("VAT-registered businesses", "grounded"))

    def test_no_map_is_distinct_from_ungrounded(self):
        # An Act we never mapped is a gap in our curation, not a model failure,
        # and conflating them misreports one as the other.
        self.assertEqual(search.ground_audience("Made Up Act", "anyone")[1], "no-map")


def make_db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db.init(con)
    return con


def add(con, no, date, title, body="", summary=None, tags=(), audience=(),
        subject="vat", act="Value Added Tax Act"):
    con.execute("INSERT INTO gazette (no, year, published_date, title, source_url, "
                "subject, enabling_act) VALUES (?,?,?,?,?,?,?)",
                (no, int(date[:4]), date, title, "http://x", subject, act))
    if summary is not None:
        con.execute("INSERT INTO gazette_summary (no, model, summary, tags, audience) "
                    "VALUES (?,?,?,?,?)",
                    (no, "test", summary, json.dumps(list(tags)), json.dumps(list(audience))))
    db.index_fts(con, no, title, body, summary)


def ref(con, src, dst, relation):
    con.execute("INSERT INTO gazette_reference (src_no, dst_no, relation) VALUES (?,?,?)",
                (src, dst, relation))


class Search(unittest.TestCase):
    def setUp(self):
        # The real tax-invoice thread: 2463/05 rescinded by 2481/22, which
        # 2500/106 then amends. All three match "tax invoice" equally well and
        # only one of them is the rule.
        self.con = make_db()
        add(self.con, "2463/05", "2025-11-17", "Tax invoice format",
            summary="Specifies the tax invoice format.", tags=["tax-invoices", "vat"],
            audience=["VAT-registered businesses"])
        add(self.con, "2481/22", "2026-03-27", "Tax invoice format, replaced",
            summary="Requires the new tax invoice format.", tags=["tax-invoices"],
            audience=["VAT-registered businesses"])
        add(self.con, "2500/106", "2026-08-06", "Tax invoice format, amended",
            summary="Moves the tax invoice start date to October.", tags=["tax-invoices"],
            audience=["VAT-registered businesses"])
        add(self.con, "2088/25", "2018-09-11", "Tourist VAT refund scheme",
            summary="Sets out the tourist refund scheme.", tags=["tourist-refunds"],
            audience=["consumers (indirectly, through prices)"])
        ref(self.con, "2481/22", "2463/05", "rescinds")
        ref(self.con, "2500/106", "2481/22", "amends")
        resolve.resolve(self.con)
        search.reindex(self.con)

    def test_hits_carry_their_standing(self):
        by_no = {r["no"]: r for r in search.search(self.con, "tax OR refund", 10)}
        self.assertIn("rescinded by 2481/22", by_no["2463/05"]["standing"])
        self.assertIn("2500/106 is the current document", by_no["2481/22"]["standing"])
        self.assertIn("current document in a 3-document rule", by_no["2500/106"]["standing"])
        self.assertEqual(by_no["2088/25"]["standing"], "standalone")

    def test_an_incomplete_chain_is_disclosed_in_the_standing(self):
        # "In force" means "not rescinded by another document we hold", and the
        # corpus is known to be missing gazettes the IRD listing omits. Where a
        # rule's history has a hole the claim is weaker than it reads, and the
        # reader is told at the point the claim is made.
        ref(self.con, "2500/106", "9999/99", "amends")     # a gazette we do not hold
        resolve.resolve(self.con)
        search.reindex(self.con)
        r = {x["no"]: x for x in search.search(self.con, "tax invoice", 10)}["2500/106"]
        self.assertFalse(r["chain_complete"])
        self.assertIn("history incomplete", r["standing"])

    def test_a_complete_chain_says_nothing_extra(self):
        r = {x["no"]: x for x in search.search(self.con, "tax invoice", 10)}["2500/106"]
        self.assertTrue(r["chain_complete"])
        self.assertNotIn("incomplete", r["standing"])

    def test_in_force_drops_what_was_rescinded(self):
        nos = [r["no"] for r in search.search(self.con, "tax invoice", 10, in_force=True)]
        self.assertNotIn("2463/05", nos)
        self.assertIn("2500/106", nos)

    def test_as_of_uses_effective_date_and_respects_the_rescission_date(self):
        # 2463/05 stood until 2481/22 rescinded it. Before that date it is the
        # answer; after it, it is history.
        early = [r["no"] for r in search.search(self.con, "tax invoice", 10,
                                                as_of="2026-01-01")]
        self.assertIn("2463/05", early)
        self.assertNotIn("2500/106", early)          # not published yet
        late = [r["no"] for r in search.search(self.con, "tax invoice", 10,
                                               as_of="2026-08-06")]
        self.assertNotIn("2463/05", late)

    def test_facet_filters_compose(self):
        nos = [r["no"] for r in search.search(
            self.con, "tax OR refund", 10, subject=["vat"], tag=["tax-invoices"])]
        self.assertNotIn("2088/25", nos)
        self.assertIn("2500/106", nos)

    def test_summary_is_searchable(self):
        # The word "October" appears only in a summary, never in a title or body.
        nos = [r["no"] for r in search.search(self.con, "October", 10)]
        self.assertEqual(nos, ["2500/106"])

    def test_rules_returns_one_result_per_thread(self):
        out = search.rules(self.con, "tax invoice", 10)
        threads = [t for t in out if t["size"] == 3]
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]["current"]["no"], "2500/106")
        self.assertEqual([m["no"] for m in threads[0]["matches"]],
                         ["2463/05", "2481/22", "2500/106"])

    def test_standalone_documents_are_threads_of_one(self):
        out = search.rules(self.con, "refund", 10)
        self.assertEqual([t["current"]["no"] for t in out], ["2088/25"])

    def test_rare_tags_are_unlisted_but_still_filterable(self):
        listed = [f["name"] for f in search.facets(self.con, min_uses=3)["tag"]]
        self.assertNotIn("tourist-refunds", listed)          # used once
        self.assertEqual(
            [r["no"] for r in search.search(self.con, "refund", 10,
                                            tag=["tourist-refunds"])],
            ["2088/25"])

    def test_reindex_reports_what_it_grounded(self):
        r = search.reindex(self.con)
        self.assertEqual(r["indexed"], 4)
        self.assertEqual(r["ungrounded"], 0)
