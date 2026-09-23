import unittest

from exile_worth.tables import sort_key, sorted_rows


class SortKeyTests(unittest.TestCase):
    def test_numbers_sort_by_value_not_text(self):
        rows = [('a', '1,000'), ('b', '254'), ('c', '≈ 24,700'), ('d', '12 (provisional)'), ('e', '0.125')]
        self.assertEqual(sorted_rows(rows), ['e', 'd', 'b', 'a', 'c'])

    def test_cells_sort_in_natural_order(self):
        rows = [('x', 'C10'), ('y', 'C2'), ('z', 'L1')]
        self.assertEqual(sorted_rows(rows), ['y', 'x', 'z'])

    def test_text_ignores_case(self):
        self.assertEqual(sorted_rows([('a', 'exalted Orb'), ('b', 'Divine Orb')]), ['b', 'a'])

    def test_missing_values_stay_last_in_both_directions(self):
        rows = [('a', '—'), ('b', '3'), ('c', ''), ('d', '10')]
        self.assertEqual(sorted_rows(rows), ['b', 'd', 'a', 'c'])
        self.assertEqual(sorted_rows(rows, descending=True), ['d', 'b', 'a', 'c'])

    def test_equal_values_keep_their_previous_order(self):
        rows = [('a', '5'), ('b', '5'), ('c', '1')]
        self.assertEqual(sorted_rows(rows, descending=True), ['a', 'b', 'c'])

    def test_numbers_before_text(self):
        self.assertLess(sort_key('999'), sort_key('abc'))

    def test_a_pending_change_sorts_by_its_confirmed_quantity(self):
        self.assertEqual(sort_key('141 → 145 (provisional)'), (0, (141.0,)))

    def test_a_share_sorts_by_its_percentage(self):
        self.assertEqual(sorted_rows([('a', '12.5 %'), ('b', '3.0 %'), ('c', '—')]), ['b', 'a', 'c'])
