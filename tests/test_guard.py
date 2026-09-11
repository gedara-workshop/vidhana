"""Tests for the nightly shrink check.

The fixture numbers are the seven gazettes the first unattended run dropped.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidhana import guard

DROPPED = {"1439/01", "1439/02", "1441/17", "1441/18", "1447/10", "1447/42", "1791/08"}
LISTED = {"2481/22", "2500/106"}


class Shrinkage(unittest.TestCase):
    def test_the_2026_09_10_run_would_have_been_refused(self):
        before = dict(gazettes=LISTED | DROPPED, summaries=LISTED | DROPPED)
        after = dict(gazettes=set(LISTED), summaries=set(LISTED))
        lost = guard.shrinkage(before, after)
        self.assertEqual(set(lost["gazettes"]), DROPPED)
        self.assertEqual(set(lost["summaries"]), DROPPED)

    def test_growth_is_the_point_of_the_job(self):
        before = dict(gazettes=set(LISTED), summaries=set(LISTED))
        after = dict(gazettes=LISTED | {"2510/01"}, summaries=LISTED | {"2510/01"})
        self.assertEqual(guard.shrinkage(before, after), {})

    def test_no_change_is_safe(self):
        s = dict(gazettes=set(LISTED), summaries=set(LISTED))
        self.assertEqual(guard.shrinkage(s, s), {})

    def test_a_swap_is_not_disguised_by_an_equal_count(self):
        # Counting would call this fine. One document out and one in is still a
        # document gone.
        before = dict(gazettes={"2481/22", "2500/106"}, summaries=set())
        after = dict(gazettes={"2481/22", "2510/01"}, summaries=set())
        self.assertEqual(guard.shrinkage(before, after), {"gazettes": ["2500/106"]})

    def test_losing_only_a_summary_is_caught(self):
        before = dict(gazettes=set(LISTED), summaries=set(LISTED))
        after = dict(gazettes=set(LISTED), summaries={"2500/106"})
        self.assertEqual(guard.shrinkage(before, after), {"summaries": ["2481/22"]})

    def test_a_first_run_has_nothing_to_lose(self):
        # No committed file yet reads as an empty baseline, not an error.
        self.assertEqual(guard._load(None, lambda d: d), set())
        before = dict(gazettes=set(), summaries=set())
        self.assertEqual(guard.shrinkage(before, dict(gazettes=LISTED, summaries=LISTED)), {})


if __name__ == "__main__":
    unittest.main()
