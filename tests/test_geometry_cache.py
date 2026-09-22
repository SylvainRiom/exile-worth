"""Sharing geometry work between detection and reading must change nothing.

`detect_layout` fits an alignment for every layout, then `read` and
`read_incremental` ask for the winner's alignment on the same frame. Computing it
once is worth about half the live loop's geometry budget, but a cache that
outlives its frame would silently read the previous stash with the previous
rectangles. These tests pin both halves: the saving, and the invalidation.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from exile_worth.icons import IconMatcher
from exile_worth.layouts import LAYOUTS, aligned_slots, edge_maps
from exile_worth.vision import Profiles, Scanner

FIXTURES = Path(__file__).parent / 'fixtures'


class Digits:
    last_approximate = False

    def read(self, image):
        return None, 0.0


def expedition_frame():
    meta = json.loads((FIXTURES / 'expedition_real' / 'items.json').read_text('utf-8'))
    stash = cv2.imread(str(FIXTURES / 'expedition_real' / 'stash.png'), cv2.IMREAD_COLOR)
    frame = np.zeros((1080, 1920, 3), np.uint8)
    x, y = meta.get('x', 0), meta.get('y', 0)
    frame[y:y+stash.shape[0], x:x+stash.shape[1]] = stash
    return frame


def runes_frame():
    stash = cv2.imread(str(FIXTURES / 'runes_real' / 'stash.png'), cv2.IMREAD_COLOR)
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[:stash.shape[0], :stash.shape[1]] = stash
    return frame


class EdgeMapTests(unittest.TestCase):
    def test_shared_maps_equal_the_ones_aligned_slots_would_build(self):
        frame = expedition_frame()
        shared = edge_maps(frame)
        self.assertEqual(aligned_slots(frame, 'expedition', shared),
                         aligned_slots(frame, 'expedition'),
                         'passing prebuilt edge maps must not change the fit')

    def test_region_window_covers_every_layout(self):
        """The maps are built on a crop; a layout reaching past it would misfit."""
        height, width = 800, 700
        for layout in LAYOUTS.values():
            for slot, (x, y, w, h) in layout.slots.items():
                with self.subTest(f'{layout.id}.{slot}'):
                    # +20 for the alignment search, +7 for the scoring strip.
                    self.assertLess(x + w + 27, width)
                    self.assertLess(y + h + 27, height)


class AlignmentCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.scanner = Scanner(Profiles(Path(self.temp.name)),
                               digits=Digits(), matcher=IconMatcher({}))

    def tearDown(self):
        self.temp.cleanup()

    def test_same_frame_fits_each_layout_once(self):
        frame = expedition_frame()
        with patch('exile_worth.vision.aligned_slots', wraps=aligned_slots) as fit:
            self.scanner.detect_layout(frame, borders_only=True)
            after_detection = fit.call_count
            self.scanner.read(frame, 'expedition')
            self.assertEqual(fit.call_count, after_detection,
                             'reading must reuse the alignment detection just fitted')
        self.assertEqual(after_detection, len(LAYOUTS),
                         'one fit per layout, not one per caller')

    def test_a_new_frame_is_never_served_the_previous_alignment(self):
        """The failure this cache could cause: reading a stash with stale rectangles."""
        first, second = expedition_frame(), runes_frame()
        self.scanner.detect_layout(first, borders_only=True)
        cached = dict(self.scanner._aligned)
        self.assertTrue(cached)
        self.scanner.detect_layout(second, borders_only=True)
        self.assertIsNot(self.scanner._aligned_frame, first)
        self.assertNotEqual(self.scanner._aligned['runes'], cached['runes'],
                            'a different stash must be re-fitted')

    def test_an_equal_but_distinct_frame_is_refitted(self):
        """Identity, not equality: a copy is a different frame and is refitted."""
        frame = expedition_frame()
        self.scanner.detect_layout(frame, borders_only=True)
        copy = frame.copy()
        with patch('exile_worth.vision.aligned_slots', wraps=aligned_slots) as fit:
            self.scanner.read(copy, 'expedition')
            self.assertEqual(fit.call_count, 1)

    def test_cached_alignment_matches_an_uncached_fit(self):
        frame = expedition_frame()
        expected = aligned_slots(frame, 'expedition')
        self.scanner.detect_layout(frame, borders_only=True)
        self.assertEqual(self.scanner.aligned(frame, 'expedition'), expected)

    def test_readings_are_identical_with_and_without_a_warm_cache(self):
        frame = expedition_frame()
        cold = Scanner(Profiles(Path(self.temp.name)), digits=Digits(), matcher=IconMatcher({}))
        without = cold.read(frame, 'expedition')
        self.scanner.detect_layout(frame, borders_only=True)
        with_cache = self.scanner.read(frame, 'expedition')
        self.assertEqual([(r.slot, r.item, r.quantity, r.reason) for r in without],
                         [(r.slot, r.item, r.quantity, r.reason) for r in with_cache])


if __name__ == '__main__':
    unittest.main()
