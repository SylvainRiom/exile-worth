import tempfile
import unittest
from pathlib import Path

import numpy as np

from exile_worth.model import Reading, Store, estimate_readings
from exile_worth.pricing import Ninja, parse_overview
from exile_worth.vision import Consensus, Profiles, Scanner, SLOTS, normalize


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.sqlite')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_revisit_replaces_does_not_add(self):
        self.store.sync('A','tab',[Reading('1','exalted',10)])
        self.store.sync('A','tab',[Reading('1','exalted',12)])
        self.store.sync('A','tab',[Reading('1','exalted',12)])
        self.assertEqual(self.store.rows('A')[0][3],12)
        self.assertEqual(len(self.store.history('A')),2)

    def test_unknown_preserves_quantity_and_flags(self):
        self.store.sync('A','tab',[Reading('1','exalted',10)])
        self.store.sync('A','tab',[Reading('1','exalted',None)])
        row = self.store.rows('A')[0]
        self.assertEqual((row[3],row[5]), (10,1))
        self.store.sync('A','tab',[Reading('1','exalted',0)])
        row = self.store.rows('A')[0]
        self.assertEqual((row[3],row[5]), (0,0))

    def test_tabs_and_leagues_are_isolated(self):
        for league,tab,n in [('A','one',10),('A','two',20),('B','one',100)]:
            self.store.sync(league,tab,[Reading('1','exalted',n)])
        prices = {'exalted':.5,'divine':1.0}
        estimate = estimate_readings(
            [Reading(slot,item,qty) for _t,slot,item,qty,_c,_u in self.store.rows('A')], prices)
        self.assertEqual(estimate.amount,15)      # 10+20 exalted at .5, divine at 1
        self.assertEqual(estimate.unpriced,0)
        other = estimate_readings(
            [Reading(slot,item,qty) for _t,slot,item,qty,_c,_u in self.store.rows('B')], prices)
        self.assertEqual(other.amount,50)         # league B is valued on its own

    def test_missing_price_excluded_and_reported(self):
        self.store.sync('A','one',[Reading('1','unknown',7)])
        estimate = estimate_readings(
            [Reading(slot,item,qty) for _t,slot,item,qty,_c,_u in self.store.rows('A')],
            {'divine':1.0})
        self.assertEqual(estimate.unpriced,1)
        self.assertIsNone(estimate.amount, 'an unpriced item must not be valued at zero')


class VisionTests(unittest.TestCase):
    def test_consensus_resets_between_tabs_and_unknowns(self):
        c = Consensus(3)
        reading = [Reading('1','exalted',12)]
        self.assertIsNone(c.push('a',reading)[0].quantity)
        self.assertIsNone(c.push('a',reading)[0].quantity)
        self.assertEqual(c.push('a',reading)[0].quantity,12)
        self.assertIsNone(c.push('b',reading)[0].quantity)
        self.assertIsNone(c.push('b',[Reading('1','exalted',None)])[0].quantity)
        self.assertIsNone(c.push('b',reading)[0].quantity)

    def test_occlusion_does_not_mean_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            frame = np.full((1080,1920,3),150,np.uint8)
            profiles.calibrate('L11','exalted',frame)
            class FakeDigits:
                def read(self, image):
                    return (123,.99) if image.any() else (None,0)
            scanner = Scanner(profiles,FakeDigits())
            self.assertEqual(scanner.read(frame)[0].quantity,123)
            hidden = np.zeros_like(frame)
            self.assertIsNone(scanner.read(hidden)[0].quantity)
            profiles.calibrate('L11','exalted',hidden,empty=True)
            self.assertEqual(scanner.read(hidden)[0].quantity,0)

    def test_structure_and_tab_identity_both_required(self):
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            frame = np.random.default_rng(42).integers(0,255,(1080,1920,3),dtype=np.uint8)
            self.assertIsNone(profiles.identify(frame,'A')[0])
            profiles.register('$$','A',(140,96,65,27),frame)
            self.assertEqual(profiles.identify(frame,'A')[0]['name'],'$$')
            self.assertIsNone(profiles.identify(frame,'B')[0])
            wrong_layout = frame.copy()
            wrong_layout[150:760,:645] = 0
            self.assertTrue(profiles.identify(wrong_layout,'A')[0] is None)
            occluded = frame.copy()
            occluded[96:123,140:205] = 0
            self.assertIsNone(profiles.identify(occluded,'A')[0])

    def test_wrong_aspect_ratio_rejected(self):
        with self.assertRaises(ValueError):
            normalize(np.zeros((1000,1000,3),np.uint8))


class PricingTests(unittest.TestCase):
    def test_live_response_shape_top_level_items(self):
        result = parse_overview({'core': {'primary':'divine', 'items':[{'id':'divine','name':'Divine Orb'}]},
                                 'items':[{'id':'alch','name':'Orb of Alchemy'}],
                                 'lines':[{'id':'alch','primaryValue':.003782}]})
        self.assertEqual(result['items']['alch']['name'],'Orb of Alchemy')
        self.assertEqual(result['prices']['divine'],1)
        self.assertEqual(result['prices']['alch'],.003782)

    def test_invalid_price_is_not_zero(self):
        result = parse_overview({'core':{'primary':'divine','items':[]},'lines':[
            {'id':'missing'}, {'id':'bad','primaryValue':float('nan')}, {'id':'negative','primaryValue':-1}]})
        self.assertEqual(result['prices'],{'divine':1})

    def test_cache_avoids_network_and_isolates_routes(self):
        import hashlib
        import json
        import time
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            client = Ninja(cache=Path(directory))
            route = '/test?league=A'
            key = hashlib.sha256((client.base+route).encode()).hexdigest()+'.json'
            (Path(directory)/key).write_text(json.dumps(dict(data={'ok':1},checked=time.time(),fetched=time.time(),stale=False)))
            with patch('exile_worth.pricing.urlopen',side_effect=OSError('offline')) as request:
                self.assertEqual(client.get(route)['data'],{'ok':1})
                request.assert_not_called()
                with self.assertRaises(OSError):
                    client.get('/test?league=B')


if __name__ == '__main__':
    unittest.main()
