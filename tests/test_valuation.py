import unittest
from types import SimpleNamespace

from exile_worth.app import App

from exile_worth.model import Reading, estimate_readings, line_value


class ValuationTests(unittest.TestCase):
    def test_ambiguous_family_displays_name_without_inventing_value(self):
        app = SimpleNamespace(market={'items': {
            'flux13': {'name': 'Thaumaturgic Flux (Level 13)'},
            'flux20': {'name': 'Thaumaturgic Flux (Level 20)'},
        }})
        app.item_name = lambda item: App.item_name(app, item)
        reading = Reading('E01',None,9,alternatives=('flux13','flux20'))
        self.assertEqual(App.reading_name(app,reading), 'Thaumaturgic Flux · unknown variant')
        self.assertIsNone(estimate_readings([reading], {'divine':1,'flux13':2}).amount)

    def test_unknown_name_is_explicit(self):
        app = SimpleNamespace(market={'items':{}})
        self.assertEqual(App.reading_name(app,Reading('E01',None,9)), 'Unrecognised item')

    def test_capture_estimate_without_registered_tab(self):
        readings = [Reading('a','exalted',200),Reading('b','divine',3)]
        estimate = estimate_readings(readings, {'exalted':.005,'divine':1})
        self.assertEqual(estimate.amount,4)
        self.assertEqual((estimate.valued,estimate.unread,estimate.unpriced),(2,0,0))

    def test_conversion_when_primary_is_not_divine(self):
        self.assertEqual(line_value('exalted',200,{'exalted':1,'divine':200}),1)

    def test_unknown_and_unpriced_cases_do_not_invent_value(self):
        readings = [Reading('a','divine',2),Reading('b',None,10),Reading('c','exalted',None),
                    Reading('d','unpriced',10)]
        estimate = estimate_readings(readings,{'divine':1})
        self.assertEqual((estimate.amount,estimate.unread,estimate.unpriced),(2,2,1))

    def test_all_unknown_is_not_zero_but_empty_known_slot_is(self):
        self.assertIsNone(estimate_readings([Reading('a',None,None)],{'divine':1}).amount)
        self.assertEqual(estimate_readings([Reading('a','exalted',0)],{'divine':1}).amount,0)

    def test_missing_or_invalid_divine_rate_is_not_zero(self):
        for rate in (None,0,-1,float('nan'),float('inf')):
            self.assertIsNone(line_value('exalted',200,{'exalted':1,'divine':rate}))


if __name__ == '__main__':
    unittest.main()
