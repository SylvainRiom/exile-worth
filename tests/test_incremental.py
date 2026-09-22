import tempfile
import itertools
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from exile_worth.layouts import LAYOUTS
from exile_worth.vision import Profiles, Scanner


class Digits:
    def __init__(self):
        self.calls = 0

    def read(self, image):
        self.calls += 1
        return int(image[0, 0, 0]), .99


class Matcher:
    # Mirrors IconMatcher: a rebuilt catalogue must be a new revision, because
    # the scanner keys its incremental cache on that, not on id().
    _revisions = itertools.count()

    def __init__(self):
        self.revision = next(Matcher._revisions)
        self.calls = 0

    def match_many(self, patches):
        self.calls += len(patches)
        return [SimpleNamespace(item='divine', alternatives=['divine'], confidence=.99) for _ in patches]


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.digits, self.matcher = Digits(), Matcher()
        self.scanner = Scanner(Profiles(Path(self.temp.name)), self.digits, self.matcher)
        self.frame = np.full((1080, 1920, 3), 12, np.uint8)

    def tearDown(self):
        self.temp.cleanup()

    def read(self, tick=0, layout='currency', tab='A'):
        return self.scanner.read_incremental(self.frame, layout, tab, tick)

    def confirm(self):
        self.assertIsNone(self.read()[0].quantity)
        self.assertEqual(self.scanner.preview_readings[0].quantity, 12)
        self.assertIsNone(self.read()[0].quantity)
        self.assertEqual(self.read()[0].quantity, 12)

    def test_unchanged_confirmed_image_has_no_ocr_or_icon_search(self):
        self.confirm()
        before = (self.digits.calls, self.matcher.calls)
        for tick in range(1, 20):
            self.assertEqual(self.read(tick)[0].quantity, 12)
        self.assertEqual((self.digits.calls, self.matcher.calls), before)
        self.assertEqual(self.scanner.last_metrics['ocr'], 0)

    def test_counter_change_only_reads_one_counter_and_reconfirms(self):
        self.confirm()
        before = (self.digits.calls, self.matcher.calls)
        slot, rect = next(iter(LAYOUTS['currency'].slots.items()))
        x,y,w,h = rect
        self.frame[y,x] = 24
        first = self.read(1)
        self.assertIsNone(first[0].quantity)
        self.assertTrue(all(r.quantity == 12 for r in first[1:]))
        self.assertIsNone(self.read(2)[0].quantity)
        self.assertEqual(self.read(3)[0].quantity, 24)
        self.assertEqual(self.digits.calls-before[0], 3)
        self.assertEqual(self.matcher.calls, before[1])

    def test_icon_change_invalidates_match(self):
        self.confirm()
        before = self.matcher.calls
        x,y,w,h = next(iter(LAYOUTS['currency'].slots.values()))
        self.frame[y+22,x] = 240
        # The changed artwork is searched again. If object and quantity still
        # match, harmless animation must not discard the existing consensus.
        self.assertEqual(self.read(1)[0].quantity, 12)
        self.assertEqual(self.matcher.calls, before+1)

    def test_animated_pixels_do_not_prevent_initial_consensus(self):
        slot, (x,y,w,h) = next(iter(LAYOUTS['currency'].slots.items()))
        self.assertIsNone(self.read(1)[0].quantity)
        self.frame[y+25,x+25] = 30
        self.assertIsNone(self.read(2)[0].quantity)
        self.frame[y+25,x+26] = 35
        self.assertEqual(self.read(3)[0].quantity, 12)

    def test_periodic_recheck_and_context_changes_require_fresh_votes(self):
        self.confirm()
        self.assertIsNone(self.read(31)[0].quantity)
        self.assertIsNone(self.read(32)[0].quantity)
        self.assertEqual(self.read(33)[0].quantity, 12)
        self.assertIsNone(self.read(34, tab='B')[0].quantity)
        expedition = self.read(35, 'expedition', 'B')
        self.assertEqual(len(expedition), len(LAYOUTS['expedition'].slots))
        self.assertTrue(all(r.slot.startswith('E') and r.quantity is None for r in expedition))
        self.assertIsNone(self.read(36, 'currency', 'A')[0].quantity)

    def test_matcher_refresh_invalidates_confirmed_cells(self):
        self.confirm()
        self.scanner.matcher = Matcher()
        self.assertIsNone(self.read(1)[0].quantity)
