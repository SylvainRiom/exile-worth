"""A cell confirmed empty is knowledge, not the absence of it.

Before this, a confirmed-empty cell was deleted, which made it indistinguishable
from a cell that had never been read. A fully scanned tab therefore claimed to be
partial forever, which destroyed the meaning of the "partial" signal the rest of
the application relies on.

The invariant these tests protect: an empty cell is recorded as read and holding
nothing, and is still never a stored zero or an invented price.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from exile_worth.model import Reading, Reason, Store, estimate_readings


class EmptyCellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def empty(self, slot):
        return Reading(slot, None, None, 0, Reason.EMPTY)

    def test_confirmed_empty_is_recorded_as_read(self):
        self.store.sync('A', 'tab', [self.empty('C01')])
        self.assertEqual(self.store.rows('A'), [], 'an empty cell holds no stock')
        self.assertEqual(self.store.empty_slots('A'), {('tab', 'C01')},
                         'but it must be known as read')

    def test_empty_cell_is_never_a_stored_zero(self):
        self.store.sync('A', 'tab', [self.empty('C01')])
        stored = self.store.db.execute(
            'SELECT item, quantity FROM slots WHERE slot=?', ('C01',)).fetchone()
        self.assertEqual(stored, (None, None),
                         'a zero quantity would later be valued as a real reading')

    def test_confirmed_empty_removes_previous_stock(self):
        self.store.sync('A', 'tab', [Reading('C01', 'divine', 5)])
        self.assertEqual(len(self.store.rows('A')), 1)
        self.store.sync('A', 'tab', [self.empty('C01')])
        self.assertEqual(self.store.rows('A'), [])
        self.assertIn(('tab', 'C01'), self.store.empty_slots('A'))

    def test_stock_reappearing_clears_the_empty_mark(self):
        self.store.sync('A', 'tab', [self.empty('C01')])
        self.store.sync('A', 'tab', [Reading('C01', 'divine', 3)])
        self.assertEqual(self.store.empty_slots('A'), set())
        self.assertEqual(self.store.rows('A')[0][2:4], ('divine', 3))

    def test_repeated_empty_reading_is_not_a_change(self):
        """Otherwise every scan of an empty tab would append a history snapshot."""
        self.assertTrue(self.store.sync('A', 'tab', [self.empty('C01')]))
        self.assertFalse(self.store.sync('A', 'tab', [self.empty('C01')]))
        self.assertEqual(len(self.store.history('A')), 1)

    def test_unreadable_cell_keeps_a_recorded_emptiness(self):
        self.store.sync('A', 'tab', [self.empty('C01')])
        self.store.sync('A', 'tab', [Reading('C01', None, None, 0, Reason.UNREADABLE_COUNT)])
        self.assertIn(('tab', 'C01'), self.store.empty_slots('A'),
                      'an unreadable reading must not erase the last known state')

    def test_a_fully_scanned_tab_reports_nothing_unread(self):
        """The regression this whole change exists for."""
        readings = [Reading(f'C{i:02}', 'divine', i) for i in range(1, 4)]
        readings += [self.empty(f'C{i:02}') for i in range(4, 8)]
        self.store.sync('A', 'tab', readings)
        expected_cells = len(readings)
        rows = self.store.rows('A')
        empty = self.store.empty_slots('A')
        unread = max(0, expected_cells - len(rows) - len(empty))
        self.assertEqual(unread, 0, 'a tab whose every cell was read is not partial')

    def test_empty_cells_do_not_enter_the_valuation(self):
        readings = [Reading('C01', 'divine', 2), self.empty('C02')]
        estimate = estimate_readings(readings, {'divine': 1.0})
        self.assertEqual(estimate.valued, 1)
        self.assertEqual(estimate.unread, 0, 'an empty cell is read, not unread')
        self.assertEqual(estimate.amount, 2.0)

    def test_valuation_point_does_not_count_empty_cells_as_unread(self):
        self.store.sync('A', 'tab', [Reading('C01', 'divine', 2), self.empty('C02')])
        market = {'prices': {'divine': 1.0}, 'primary': 'divine', 'fetched': 0, 'stale': False}
        self.store.record_valuation('A', market, expected={'tab': 2})
        point = self.store.valuations('A')[-1]
        self.assertEqual(point['tabs']['tab']['unread'], 0)

    def test_approximate_slots_ignores_empty_rows(self):
        self.store.sync('A', 'tab', [Reading('C01', 'verisium', 38300, approximate=True)])
        self.store.sync('A', 'tab', [self.empty('C02')])
        self.assertEqual(self.store.approximate_slots('A'), {('tab', 'C01')})

    def test_league_and_tab_isolation_still_holds(self):
        self.store.sync('A', 'tab1', [self.empty('C01')])
        self.store.sync('B', 'tab1', [self.empty('C01')])
        self.store.sync('A', 'tab2', [self.empty('C01')])
        self.assertEqual(self.store.empty_slots('A'), {('tab1', 'C01'), ('tab2', 'C01')})
        self.assertEqual(self.store.empty_slots('B'), {('tab1', 'C01')})


class EmptyColumnMigrationTests(unittest.TestCase):
    def test_existing_database_gains_the_column_without_losing_stock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'old.sqlite'
            # A database written before the column existed.
            legacy = sqlite3.connect(path)
            legacy.executescript('''
                CREATE TABLE slots (
                  league TEXT, tab TEXT, slot TEXT, item TEXT, quantity INTEGER,
                  confirmed TEXT, uncertain INTEGER, PRIMARY KEY(league, tab, slot));
                CREATE TABLE history (
                  id INTEGER PRIMARY KEY, time TEXT, league TEXT, tab TEXT, snapshot TEXT);
                CREATE TABLE price_history (
                  league TEXT, fetched REAL, primary_currency TEXT, prices TEXT,
                  PRIMARY KEY(league, fetched));
                CREATE TABLE valuations (
                  id INTEGER PRIMARY KEY, time TEXT NOT NULL, league TEXT NOT NULL,
                  signature TEXT NOT NULL, reason TEXT NOT NULL, data TEXT NOT NULL);
            ''')
            legacy.execute("INSERT INTO slots VALUES('A','tab','C01','divine',7,'2026-09-22T00:00:00',0)")
            legacy.commit()
            legacy.close()

            store = Store(path)
            try:
                self.assertEqual(store.rows('A')[0][2:4], ('divine', 7),
                                 'existing stock must survive the migration')
                self.assertEqual(store.empty_slots('A'), set(),
                                 'old rows default to not-empty')
                store.sync('A', 'tab', [Reading('C02', None, None, 0, Reason.EMPTY)])
                self.assertEqual(store.empty_slots('A'), {('tab', 'C02')})
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
