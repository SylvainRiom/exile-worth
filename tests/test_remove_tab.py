import json
import tempfile
import unittest
from pathlib import Path

from exile_worth.model import Reading, Reason, Store
from exile_worth.vision import Profiles


class RemoveTabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path/'inventory.sqlite3')
        self.market = dict(prices={'divine': 1, 'exalted': .01}, primary='divine', fetched=1, stale=False)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_forget_tab_drops_its_cells_only_and_keeps_the_history(self):
        self.store.sync('A', 'one', [Reading('C01', 'exalted', 10), Reading('C02', None, None, 1, Reason.EMPTY)])
        self.store.sync('A', 'two', [Reading('C01', 'exalted', 5)])
        self.store.sync('B', 'one', [Reading('C01', 'exalted', 7)])
        self.store.record_valuation('A', self.market)
        self.assertEqual(self.store.forget_tab('A', 'one'), 2)
        self.assertEqual([row[:4] for row in self.store.rows('A')], [('two', 'C01', 'exalted', 5)])
        self.assertEqual(self.store.empty_slots('A'), set())
        self.assertEqual(len(self.store.rows('B')), 1, 'Another league keeps its tab')
        self.assertTrue(self.store.history('A'))
        self.assertEqual(self.store.valuations('A')[0]['tabs']['one']['amount'], .1)

    def test_profiles_remove_persists_and_keeps_the_name_for_history(self):
        profiles = Profiles(self.path)
        profiles.data['tabs'] = [dict(id='one', name='Currency', league='A'),
                                 dict(id='two', name='Ritual', league='A')]
        before = profiles.data['tabs']
        removed = profiles.remove('one')
        self.assertEqual(removed['name'], 'Currency')
        self.assertIsNot(profiles.data['tabs'], before, 'The live loop may be iterating the old list')
        saved = json.loads((self.path/'profiles.json').read_text('utf-8'))
        self.assertEqual([tab['id'] for tab in saved['tabs']], ['two'])
        self.assertEqual(saved['removed'], {'one': 'Currency'})
        self.assertIsNone(profiles.remove('one'))


if __name__ == '__main__':
    unittest.main()
