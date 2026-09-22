import sqlite3
import tempfile
import unittest
from pathlib import Path

from joy_tracker.history_ui import fixed_value
from joy_tracker.model import Event, Reading, Store


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'inventory.sqlite'
        self.store = Store(self.path)
        self.market = dict(prices={'divine': 100, 'exalted': 2}, primary='chaos', fetched=1, stale=False)
        self.store.sync('A', 'one', [Reading('C01','exalted',10)])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_prices_alone_make_a_point_and_old_values_are_frozen(self):
        self.store.record_valuation('A', self.market)
        self.market['prices']['exalted'] = 4
        self.market['fetched'] = 2
        self.store.record_valuation('A', self.market)
        points = self.store.valuations('A')
        self.assertEqual([p['amount'] for p in points], [.2,.4])
        self.assertEqual(fixed_value(points[1], points[0]['prices']), .2)
        self.assertEqual(points[0]['rate'], 100)

    def test_repeat_observation_deduplicates_but_quality_changes_are_saved(self):
        self.store.record_valuation('A', self.market, {'one':2, 'unseen':3})
        self.store.db.execute("UPDATE slots SET confirmed='2099-01-01T00:00:00+00:00'")
        self.assertIsNone(self.store.record_valuation('A', self.market, {'one':2, 'unseen':3}))
        self.store.sync('A','one',[Reading('C01',None,None)])
        self.store.record_valuation('A', self.market, {'one':2, 'unseen':3})
        point = self.store.valuations('A')[-1]
        self.assertEqual(point['amount'], .2)
        self.assertEqual(point['tabs']['one']['uncertain'], 1)
        self.assertEqual(point['tabs']['one']['unread'], 1)
        self.assertEqual(point['tabs']['unseen']['unread'], 3)

    def test_sessions_and_snapshots_survive_restart_and_are_league_isolated(self):
        self.store.record_valuation('A', self.market, reason=Event.SESSION_START, force=True)
        self.store.close()
        self.store = Store(self.path)
        self.assertIsNotNone(self.store.active_session('A'))
        self.assertIsNone(self.store.active_session('B'))
        self.assertEqual(self.store.valuations('B'), [])
        self.store.record_valuation('A', self.market, reason=Event.SESSION_END, force=True)
        self.assertIsNone(self.store.active_session('A'))
        self.assertEqual(len(self.store.valuations('A')), 2)
        for index in range(501):
            self.market['fetched'] = index + 2
            self.store.record_valuation('A', self.market)
        self.assertEqual(len(self.store.valuations('A')), 500)
        self.assertEqual(self.store.last_completed_session('A')[0]['reason'], Event.SESSION_START)

    def test_unpriced_and_approximate_are_preserved(self):
        self.store.sync('A', 'one', [Reading('C01','exalted',24700, approximate=True), Reading('C02','unknown',3)])
        self.store.record_valuation('A', self.market)
        point = self.store.valuations('A')[0]
        self.assertEqual(point['tabs']['one']['approximate'], 1)
        self.assertEqual(point['tabs']['one']['unpriced'], 1)

    def test_legacy_database_migrates_without_inventory_loss(self):
        legacy = Path(self.temp.name)/'legacy.sqlite'
        with sqlite3.connect(legacy) as db:
            db.execute('CREATE TABLE slots (league TEXT, tab TEXT, slot TEXT, item TEXT, quantity INTEGER, confirmed TEXT, uncertain INTEGER, PRIMARY KEY(league,tab,slot))')
            db.execute("INSERT INTO slots VALUES('A','old-uuid','1','divine',7,'2026-01-01',0)")
        db.close()
        store = Store(legacy)
        try:
            self.assertEqual(store.rows('A')[0][:4], ('old-uuid','1','divine',7))
            self.assertEqual(len(store.rows('A')[0]), 6)
            self.assertEqual(store.approximate_slots('A'), set())
            self.assertEqual(store.valuations('A'), [])
        finally:
            store.close()
