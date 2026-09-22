import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from joy_tracker.layouts import LAYOUTS, RUNE_PAGES, aligned_slots, layout_family
from joy_tracker.app import App
from joy_tracker.model import Reading, Reason, Store
from joy_tracker.vision import Consensus, Profiles, Scanner


def bordered_page(page):
    frame = np.full((1080, 1920, 3), 20, np.uint8)
    for x, y, w, h in LAYOUTS[page].slots.values():
        cv2.rectangle(frame, (x, y), (x+w, y+h), (95, 110, 125), 2)
    return frame


class RunePageTests(unittest.TestCase):
    def test_saved_real_rune_stash_uses_rune_grid(self):
        crop = cv2.imread(str(Path(__file__).parent / 'fixtures/runes_real/stash.png'))
        frame = np.zeros((1080, 1920, 3), np.uint8)
        frame[:crop.shape[0], :crop.shape[1]] = crop
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)))
            self.assertEqual(scanner.detect_layout(frame), 'runes')
        slots = aligned_slots(frame, 'runes')
        self.assertEqual(len(slots), 70)
        self.assertEqual(slots['R01'][0], 35)
        self.assertLessEqual(abs(slots['R01'][1] - 202), 3)

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
            with patch('joy_tracker.vision.active_tab', return_value=('Runes', (490, 96, 90, 29))):
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
        crop = cv2.imread(str(Path(__file__).parent / 'fixtures/runes_real/stash.png'))
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
            with patch('joy_tracker.vision.active_tab', return_value=('Runes', rect)):
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
            with patch('joy_tracker.vision.active_tab', return_value=('Runes', rect)):
                new, _ = profiles.observe(frame, 'A', 'runes', object())
            self.assertNotEqual(new['id'], old['id'])
            self.assertEqual(old['layout_id'], 'currency')


if __name__ == '__main__':
    unittest.main()
