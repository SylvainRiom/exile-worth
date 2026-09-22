"""Two pieces of structure that were one bad edit away from breaking.

`expected_slot_count` existed as three identical copies in `app.py` — the card,
the grand total and the valuation point each computed it inline. The next
multi-view stash would have made them disagree, and a disagreement there reads as
a wrong "partial" badge rather than as a crash.

`ScanResult` replaces a tuple of six or seven items whose length the consumer
probed (`payload[6] if len(payload) > 6`) to decide whether provisional readings
existed. A producer adding a field in the wrong position changed behaviour
silently.
"""
import unittest

from exile_worth.app import ScanResult
from exile_worth.layouts import LAYOUTS, RUNE_PAGES, expected_slot_count


class ExpectedSlotCountTests(unittest.TestCase):
    def test_single_view_stash_expects_its_own_cells(self):
        self.assertEqual(expected_slot_count({'layout_id': 'currency'}),
                         len(LAYOUTS['currency'].slots))
        self.assertEqual(expected_slot_count({'layout_id': 'expedition'}),
                         len(LAYOUTS['expedition'].slots))

    def test_a_runes_tab_expects_all_five_views(self):
        """One profile spans five geometries; expecting only the visible one
        would report a fully scanned tab as permanently partial."""
        total = sum(len(LAYOUTS[key].slots) for key in RUNE_PAGES)
        self.assertEqual(expected_slot_count({'layout_id': 'runes'}), total)
        self.assertGreater(total, len(LAYOUTS['runes'].slots))

    def test_every_rune_view_gives_the_same_expectation(self):
        """The visible page must not change what the parent tab expects."""
        counts = {expected_slot_count({'layout_id': key}) for key in RUNE_PAGES}
        self.assertEqual(len(counts), 1, f'views disagree: {counts}')

    def test_legacy_profile_without_a_layout_id_is_currencies(self):
        self.assertEqual(expected_slot_count({}), len(LAYOUTS['currency'].slots))

    def test_unknown_layout_id_falls_back_without_raising(self):
        self.assertEqual(expected_slot_count({'layout_id': 'not-a-layout'}),
                         len(LAYOUTS['currency'].slots))

    def test_the_three_former_copies_now_agree_by_construction(self):
        """The regression the triplication invited: three sites, three answers."""
        tabs = [{'id': 'a', 'league': 'L', 'layout_id': 'currency'},
                {'id': 'b', 'league': 'L', 'layout_id': 'runes'},
                {'id': 'c', 'league': 'L', 'layout_id': 'expedition'}]
        per_card = [expected_slot_count(tab) for tab in tabs]
        grand_total = sum(expected_slot_count(tab) for tab in tabs)
        per_valuation = {tab['id']: expected_slot_count(tab) for tab in tabs}
        self.assertEqual(sum(per_card), grand_total)
        self.assertEqual(sorted(per_valuation.values()), sorted(per_card))


class ScanResultTests(unittest.TestCase):
    def test_fields_are_named_not_positional(self):
        scan = ScanResult(frame='F', tab=None, readings=[], reason='',
                          league='L', layout_id='currency')
        self.assertEqual(scan.layout_id, 'currency')
        self.assertEqual(scan.provisional, ())

    def test_a_preview_carries_no_provisional_readings_by_default(self):
        """The old code inferred this from the tuple's length."""
        scan = ScanResult('F', None, [], '', 'L', None)
        self.assertEqual(scan.provisional, ())

    def test_the_record_is_immutable_across_the_queue(self):
        scan = ScanResult('F', None, [], '', 'L', 'currency')
        with self.assertRaises(Exception):
            scan.layout_id = 'expedition'

    def test_an_unrecognised_structure_is_an_explicit_none(self):
        """Not a missing tuple element the consumer had to guess from a slot name."""
        scan = ScanResult('F', None, [], '', 'L', None)
        self.assertIsNone(scan.layout_id)


if __name__ == '__main__':
    unittest.main()
