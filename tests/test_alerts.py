"""Tests for Phase 4 alerts.

The fixture is the real tax-invoice thread, because it is the smallest shape
that exercises every event kind at once: 2463/05 is rescinded by 2481/22, which
2500/106 both amends and re-dates.
"""
import json
import os
import sqlite3
import sys
import unittest
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import alerts, db, resolve

ATOM = "{http://www.w3.org/2005/Atom}"


def make_db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    db.init(con)
    add(con, "2463/05", "2025-11-17", "Tax invoice format", "Specifies the format.")
    add(con, "2481/22", "2026-03-27", "Tax invoice format, replaced",
        "Requires the new format from July.")
    add(con, "2500/106", "2026-08-06", "Tax invoice format, amended",
        "Moves the start date to October.")
    add(con, "2088/25", "2018-09-11", "Tourist VAT refund scheme",
        "Sets out the refund scheme.")
    ref(con, "2481/22", "2463/05", "rescinds")
    ref(con, "2500/106", "2481/22", "amends")
    # A reference to a gazette the IRD listing does not carry. 13 of these exist
    # in the real corpus and none of them may raise an event.
    ref(con, "2088/25", "1234/56", "amends")
    # And a `cites`, which changes nothing's standing.
    ref(con, "2481/22", "2088/25", "cites")
    con.execute("INSERT INTO gazette_date (no, kind, date, context) VALUES (?,?,?,?)",
                ("2500/106", "replaces_effective_date", "2026-10-01", "from October"))
    resolve.resolve(con)
    return con


def add(con, no, date, title, summary, subject="vat", confidence="high"):
    con.execute("INSERT INTO gazette (no, year, published_date, title, source_url, "
                "subject, enabling_act) VALUES (?,?,?,?,?,?,?)",
                (no, int(date[:4]), date, title, f"http://x/{no}.pdf", subject,
                 "Value Added Tax Act"))
    con.execute("INSERT INTO gazette_summary (no, model, summary, audience, tags, "
                "confidence) VALUES (?,?,?,?,?,?)",
                (no, "test", summary, json.dumps(["VAT-registered businesses"]),
                 "[]", confidence))
    con.execute("INSERT INTO gazette_audience (no, audience, coarse) VALUES (?,?,?)",
                (no, "VAT-registered businesses", "VAT-registered businesses"))


def ref(con, src, dst, relation):
    con.execute("INSERT INTO gazette_reference (src_no, dst_no, relation) VALUES (?,?,?)",
                (src, dst, relation))


class Derive(unittest.TestCase):
    def setUp(self):
        self.con = make_db()
        self.events = alerts.derive(self.con)

    def kinds(self, no):
        return sorted(e["kind"] for e in self.events if e["no"] == no)

    def test_every_gazette_raises_a_published_event(self):
        self.assertEqual(
            sorted(e["no"] for e in self.events if e["kind"] == "published"),
            ["2088/25", "2463/05", "2481/22", "2500/106"])

    def test_relations_raise_events_naming_both_gazettes(self):
        amends = next(e for e in self.events if e["kind"] == "amends")
        self.assertEqual((amends["no"], amends["target_no"]), ("2500/106", "2481/22"))

    def test_cites_raises_nothing(self):
        # A citation of an unrelated instrument changes no standing; alerting on
        # it would bury the events that matter.
        self.assertNotIn("cites", [e["kind"] for e in self.events])

    def test_dangling_edges_raise_nothing(self):
        # We hold no 1234/56, so we can say neither what changed nor what the
        # rule now is. An alert that can say neither is noise.
        self.assertEqual(self.kinds("2088/25"), ["published"])

    def test_effective_change_is_its_own_kind(self):
        self.assertEqual(self.kinds("2500/106"), ["amends", "effective_change", "published"])

    def test_events_are_dated_by_the_acting_gazette(self):
        e = next(x for x in self.events if x["kind"] == "amends")
        self.assertEqual(e["event_date"], "2026-08-06")


class Record(unittest.TestCase):
    def setUp(self):
        self.con = make_db()

    def test_first_run_sees_everything_and_the_second_sees_nothing(self):
        first = alerts.record(self.con, now="2026-09-01T00:00:00Z")
        self.assertEqual(first["new"], first["total"])
        second = alerts.record(self.con, now="2026-09-02T00:00:00Z")
        self.assertEqual((second["new"], second["total"]), (0, first["total"]))

    def test_detected_at_is_never_rewritten(self):
        # Otherwise a nightly run re-notifies a reader about a 2014 gazette.
        alerts.record(self.con, now="2026-09-01T00:00:00Z")
        alerts.record(self.con, now="2026-09-02T00:00:00Z")
        stamps = {r[0] for r in self.con.execute("SELECT DISTINCT detected_at "
                                                 "FROM gazette_event")}
        self.assertEqual(stamps, {"2026-09-01T00:00:00Z"})

    def test_events_that_stop_being_derivable_are_dropped(self):
        alerts.record(self.con)
        self.con.execute("DELETE FROM gazette_reference WHERE relation='amends'")
        r = alerts.record(self.con)
        self.assertEqual(r["dropped"], 2)      # the amends and its effective_change
        self.assertNotIn("amends", [x[0] for x in self.con.execute(
            "SELECT kind FROM gazette_event")])


class Feed(unittest.TestCase):
    def setUp(self):
        self.con = make_db()
        alerts.record(self.con)
        self.entries = alerts.group(alerts.whatsnew(self.con, limit=99))

    def test_one_entry_per_gazette_not_per_event(self):
        self.assertEqual(len(self.entries), 4)
        top = self.entries[0]
        self.assertEqual(top["no"], "2500/106")
        self.assertEqual(top["kinds"], ["effective_change", "amends", "published"])

    def test_entry_title_reads_as_what_the_gazette_does(self):
        titles = {e["no"]: alerts._entry_title(e) for e in self.entries}
        self.assertIn("amends 2481/22 and changes when it takes effect",
                      titles["2500/106"])
        self.assertIn("rescinds 2463/05", titles["2481/22"])
        self.assertIn("new:", titles["2088/25"])

    def test_entry_says_which_document_is_now_the_rule(self):
        body = alerts._entry_body(next(e for e in self.entries if e["no"] == "2481/22"))
        self.assertIn("current document in this rule is now 2500/106", body)

    def test_low_confidence_is_disclosed_in_the_feed(self):
        self.con.execute("UPDATE gazette_summary SET confidence='low' WHERE no='2088/25'")
        e = alerts.group(alerts.whatsnew(self.con, limit=99))
        body = alerts._entry_body(next(x for x in e if x["no"] == "2088/25"))
        self.assertIn("confidence: low", body)

    def test_incomplete_history_is_disclosed_in_the_entry(self):
        # A feed reader cannot ask a follow-up question. An entry that says a
        # rule is current, and says nothing else, will be read as settled.
        ref(self.con, "2500/106", "9999/99", "amends")     # a gazette we do not hold
        resolve.resolve(self.con)
        e = alerts.group(alerts.whatsnew(self.con, limit=99))
        body = alerts._entry_body(next(x for x in e if x["no"] == "2500/106"))
        self.assertIn("history is incomplete", body)
        self.assertIn("not in the corpus", body)

    def test_a_complete_history_carries_no_caution(self):
        body = alerts._entry_body(next(x for x in self.entries if x["no"] == "2500/106"))
        self.assertNotIn("history is incomplete", body)

    def test_feed_is_valid_atom_with_stable_entry_ids(self):
        xml = alerts.atom(self.con, self.entries, feed_id="tag:test", title="t")
        root = ET.fromstring(xml)
        ids = [el.text for el in root.iter(f"{ATOM}id")]
        self.assertIn("tag:vidhana,2026:gazette:2500/106", ids)
        self.assertEqual(len(ids), len(set(ids)))

    def test_feed_updated_is_the_newest_event_not_now(self):
        # A run that finds nothing must not restamp the feed; clients read that
        # as activity and a quiet corpus should look quiet.
        root = ET.fromstring(alerts.atom(self.con, self.entries,
                                         feed_id="tag:test", title="t"))
        self.assertEqual(root.find(f"{ATOM}updated").text, "2026-08-06T00:00:00Z")

    def test_writing_feeds_twice_changes_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            first = alerts.write_feeds(self.con, out_dir=d)
            self.assertTrue(all(w["changed"] for w in first))
            self.assertFalse(any(w["changed"] for w in alerts.write_feeds(self.con,
                                                                          out_dir=d)))


class WhatsNew(unittest.TestCase):
    def setUp(self):
        self.con = make_db()
        alerts.record(self.con)

    def test_since_filters_on_publication_not_detection(self):
        # A reader asking what changed since January means changes to the law,
        # not changes to our database.
        nos = {e["no"] for e in alerts.whatsnew(self.con, since="2026-01-01")}
        self.assertEqual(nos, {"2481/22", "2500/106"})

    def test_kind_filter(self):
        got = alerts.whatsnew(self.con, kind=["rescinds"])
        self.assertEqual([(e["no"], e["target_no"]) for e in got],
                         [("2481/22", "2463/05")])
