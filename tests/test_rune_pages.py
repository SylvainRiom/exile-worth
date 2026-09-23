import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from exile_worth.layouts import LAYOUTS, RUNE_PAGES, aligned_slots, layout_family
from exile_worth.app import App
from exile_worth.model import Reading, Reason, Store
from exile_worth.vision import Consensus, Profiles, Scanner


FIXTURES = Path(__file__).parent / 'fixtures' / 'runes_real'

# The five real captures, one per view, taken in a single session on
# 22 September 2026 at 1920x1080. `runes.png` is the earlier 21 September
# capture, kept because the crop is pixel-identical.
REAL_VIEWS = ('runes', 'kalguuran', 'soul_cores', 'idols', 'ancient_augments')

# The view selector sits above the grid: five buttons of 64 px pitch, the
# visible one lit by an amber glow. Measured on the five captures.
SELECTOR_BAND = (130, 190)
SELECTOR_X = (175, 239, 303, 367, 431)
SELECTOR_WIDTH = 64


def real_view(name):
    """A real capture placed back at the client origin it was cut from."""
    crop = cv2.imread(str(FIXTURES / f'{name}.png'))
    assert crop is not None, name
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[:crop.shape[0], :crop.shape[1]] = crop
    return frame


def selector_warmth(frame):
    """Amber excess per selector button; the visible view is the warmest."""
    top, bottom = SELECTOR_BAND
    band = frame[top:bottom].astype(np.int16)
    warm = band[:, :, 2] - band[:, :, 0]
    return [float(warm[:, x:x+SELECTOR_WIDTH].mean()) for x in SELECTOR_X]


def bordered_page(page):
    frame = np.full((1080, 1920, 3), 20, np.uint8)
    for x, y, w, h in LAYOUTS[page].slots.values():
        cv2.rectangle(frame, (x, y), (x+w, y+h), (95, 110, 125), 2)
    return frame


class RunePageTests(unittest.TestCase):
    def test_saved_real_rune_stash_uses_rune_grid(self):
        crop = cv2.imread(str(Path(__file__).parent / 'fixtures/runes_real/runes.png'))
        frame = np.zeros((1080, 1920, 3), np.uint8)
        frame[:crop.shape[0], :crop.shape[1]] = crop
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)))
            self.assertEqual(scanner.detect_layout(frame), 'runes')
        slots = aligned_slots(frame, 'runes')
        self.assertEqual(len(slots), 70)
        self.assertEqual(slots['R01'][0], 35)
        self.assertLessEqual(abs(slots['R01'][1] - 202), 3)

    def test_five_real_captures_detect_their_own_view(self):
        """The four non-Runes geometries were measured on chat screenshots.

        This is the check against real captures: synthetic grids draw the
        borders the layout already declares, so they cannot disagree.
        """
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)))
            for view in REAL_VIEWS:
                with self.subTest(view=view):
                    self.assertEqual(scanner.detect_layout(real_view(view)), view)

    def test_real_captures_align_on_one_translation_within_tolerance(self):
        for view in REAL_VIEWS:
            with self.subTest(view=view):
                frame = real_view(view)
                reference = LAYOUTS[view].slots
                slots = aligned_slots(frame, view)
                self.assertEqual(len(slots), len(reference))
                shifts = {(x - reference[slot][0], y - reference[slot][1])
                          for slot, (x, y, _w, _h) in slots.items()}
                self.assertEqual(len(shifts), 1)
                dx, dy = shifts.pop()
                self.assertLessEqual(max(abs(dx), abs(dy)), 3)

    def test_view_selector_lights_the_visible_view(self):
        """The lit button names the visible view without reading the grid.

        Recorded as an observation, not as a decision: nothing in `vision.py`
        consults the selector yet. It is measured here so that it cannot rot
        unnoticed before that choice is made.
        """
        for index, view in enumerate(REAL_VIEWS):
            with self.subTest(view=view):
                warmth = selector_warmth(real_view(view))
                lit = warmth[index]
                others = warmth[:index] + warmth[index+1:]
                self.assertEqual(max(warmth), lit)
                # The conch button reads warm even unlit, so the decision has
                # to be a comparison between buttons, never a fixed threshold.
                self.assertGreater(lit - max(others), 3.0)

    def test_five_grids_detected_without_reusing_other_layouts(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)))
            for page in RUNE_PAGES:
                with self.subTest(page=page):
                    self.assertEqual(scanner.detect_layout(bordered_page(page)), page)
                    self.assertEqual(layout_family(page), 'runes')
            slot_sets = [set(LAYOUTS[page].slots) for page in RUNE_PAGES]
            self.assertEqual(sum(map(len, slot_sets)), len(set().union(*slot_sets)))

    def test_subpage_reuses_parent_profile_and_preserves_other_stock(self):
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            with patch('exile_worth.vision.active_tab', return_value=('Runes', (490, 96, 90, 29))):
                first, _ = profiles.observe(bordered_page('runes'), 'A', 'runes', object())
                second, _ = profiles.observe(bordered_page('kalguuran'), 'A', 'kalguuran', object())
            self.assertEqual(first['id'], second['id'])
            self.assertEqual(len(profiles.data['tabs']), 1)
            self.assertEqual(first['layout_id'], 'runes')
            store = Store(Path(directory) / 'inventory.sqlite3')
            try:
                store.sync('A', first['id'], [Reading('R01', 'rune', 2)])
                store.sync('A', first['id'], [Reading('K01', 'kalguuran', 3)])
                self.assertEqual({row[1]: row[3] for row in store.rows('A')}, {'R01': 2, 'K01': 3})
                store.sync('A', first['id'], [Reading('R01', None, None, 0, Reason.EMPTY)])
                self.assertEqual({row[1] for row in store.rows('A')}, {'K01'})
            finally:
                store.close()

    def test_empty_cell_requires_consensus_before_removing_stock(self):
        consensus = Consensus()
        empty = Reading('R01', None, None, 0, Reason.EMPTY)
        self.assertEqual(consensus.push('runes', [empty])[0].reason, Reason.PENDING)
        self.assertEqual(consensus.push('runes', [empty])[0].reason, Reason.PENDING)
        self.assertEqual(consensus.push('runes', [empty])[0].reason, Reason.EMPTY)

    def test_known_parent_resolves_each_visible_page_and_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)))
            app = SimpleNamespace(layout_override=None, scanner=scanner)
            parent = {'layout_id': 'runes'}
            for page in RUNE_PAGES:
                with self.subTest(page=page):
                    self.assertEqual(App.resolve_layout(app, bordered_page(page), parent), page)
            self.assertIsNone(App.resolve_layout(app, np.zeros((1080, 1920, 3), np.uint8), parent))

    def test_misclassified_empty_profile_keeps_uuid_when_corrected(self):
        crop = cv2.imread(str(Path(__file__).parent / 'fixtures/runes_real/runes.png'))
        frame = np.zeros((1080, 1920, 3), np.uint8)
        frame[:crop.shape[0], :crop.shape[1]] = crop
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            rect = (487, 97, 105, 27)
            old = profiles.register('Runes', 'A', rect, frame, 'currency')
            old['auto_registered'] = True
            old['visible_name'] = 'Runes'
            profiles.save()
            app = SimpleNamespace(layout_override=None, scanner=Scanner(profiles))
            self.assertEqual(App.resolve_layout(app, frame, old), 'runes')
            with patch('exile_worth.vision.active_tab', return_value=('Runes', rect)):
                fixed, _ = profiles.observe(frame, 'A', 'runes', object())
            self.assertEqual(fixed['id'], old['id'])
            self.assertEqual(fixed['layout_id'], 'runes')
            self.assertEqual(len(profiles.data['tabs']), 1)

    def test_profile_with_existing_stock_is_not_reclassified(self):
        frame = bordered_page('runes')
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            rect = (487, 97, 105, 27)
            old = profiles.register('Runes', 'A', rect, frame, 'currency')
            old['auto_registered'] = True
            old['visible_name'] = 'Runes'
            profiles.save()
            store = Store(Path(directory) / 'inventory.sqlite3')
            store.sync('A', old['id'], [Reading('C01', 'divine', 2)])
            store.close()
            with patch('exile_worth.vision.active_tab', return_value=('Runes', rect)):
                new, _ = profiles.observe(frame, 'A', 'runes', object())
            self.assertNotEqual(new['id'], old['id'])
            self.assertEqual(old['layout_id'], 'currency')


if __name__ == '__main__':
    unittest.main()
