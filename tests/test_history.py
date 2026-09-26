import sqlite3
import tempfile
import unittest
from pathlib import Path

from exile_worth.history_ui import fixed_value
from exile_worth.model import Event, Reading, Store, item_changes, stock_change


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

    def test_item_changes_sum_tabs_value_at_end_prices_and_keep_unpriced(self):
        start = dict(rows=[['one', 'C01', 'exalted', 10, '', 0, 0], ['one', 'C02', 'chaos', 5, '', 0, 0],
                           ['two', 'C01', 'relic', 1, '', 0, 0]], prices={'divine': 100, 'exalted': 2})
        # Five exalted moved from tab one to tab two, three more farmed;
        # the chaos are spent; a relic nobody prices is new.
        end = dict(rows=[['one', 'C01', 'exalted', 5, '', 0, 0], ['two', 'C05', 'exalted', 8, '', 0, 0],
                         ['two', 'C01', 'relic', 2, '', 0, 0], ['two', 'C09', None, None, '', 1, 0]],
                   prices={'divine': 100, 'exalted': 4, 'chaos': 1})
        changes = {item: rest for item, *rest in item_changes(start, end)}
        self.assertEqual(changes['exalted'], [10, 13, 3, 3 * 4 / 100])
        self.assertEqual(changes['chaos'], [5, 0, -5, -5 / 100])
        self.assertEqual(changes['relic'], [1, 2, 1, None], 'Unpriced stays None, never zero')
        self.assertEqual([entry[0] for entry in item_changes(start, end)], ['exalted', 'chaos', 'relic'])
        self.assertEqual(item_changes(end, end), [])

    def test_stock_change_ignores_tabs_being_registered_or_removed(self):
        def point(amount, prices=None, **tabs):
            return dict(amount=amount, prices=prices or {'divine': 1, 'chaos': .1},
                        tabs={tab: dict(amount=value, observed=None if value is None else 'x')
                              for tab, value in tabs.items()})
        # One tab, then a second one registered: the total jumps, nothing was gained.
        points = [point(10, one=10), point(510, one=10, two=500), point(515, one=12, two=503)]
        start, before, after = stock_change(points)
        self.assertIs(start, points[1])
        self.assertEqual((before, after), (510, 515))
        # A removed tab is not a loss: only the tabs the last point read count.
        points.append(point(12, one=12))
        start, before, after = stock_change(points)
        self.assertIs(start, points[0])
        self.assertEqual((before, after), (10, 12))
        # Registered but never read yet (the plain `D2`) does not move the start.
        start, _before, _after = stock_change([point(10, one=10), point(10, one=10, d2=None)])
        self.assertEqual(start['tabs'], {'one': dict(amount=10, observed='x')})
        # Each point at its own rates, in the chosen currency.
        self.assertEqual(stock_change([point(1, one=1), point(1, {'divine': 1, 'chaos': .05}, one=1)], 'chaos')[1:],
                         (10, 20))
        # Only the newest point covers every tab: no comparable change.
        self.assertIsNone(stock_change([point(10, one=10), point(510, one=10, two=500)]))
        self.assertIsNone(stock_change([point(10, one=10)]))

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
