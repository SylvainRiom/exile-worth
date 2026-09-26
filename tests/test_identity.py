"""A registered tab is found again when its background changes between sessions."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from exile_worth.layouts import LAYOUTS
from exile_worth.vision import Profiles, selected_tab_rect
from tests.test_stash_real import stash_frame


class NoOCR:
    """Registration must not need the title once the label is known."""
    def __call__(self, image):
        raise AssertionError('the title was read by OCR')


class LabelAfterBackgroundChangeTests(unittest.TestCase):
    def test_delirium_is_found_by_its_label_when_its_strips_change(self):
        frame = stash_frame('delirium')
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            tab = profiles.register('Delirium', 'A', selected_tab_rect(frame), frame, 'delirium')
            tab['auto_registered'] = True
            self.assertEqual(profiles.identify(frame, 'A')[0]['id'], tab['id'])
            # The user's Delirium: its middle rows' background changed between
            # sessions, and the strips above those cells stopped matching.
            later = frame.copy()
            ys = [y for slot, (_x, y, _w, _h) in LAYOUTS['delirium'].slots.items() if 'DE04' <= slot <= 'DE26']
            band = later[min(ys)-6:max(ys)+60, :655].astype(np.int16)
            later[min(ys)-6:max(ys)+60, :655] = np.clip(band + 45, 0, 255).astype(np.uint8)
            self.assertIsNone(profiles.identify(later, 'A')[0])
            found, _ = profiles.observe(later, 'A', 'delirium', NoOCR())
            self.assertEqual(found['id'], tab['id'])
            self.assertEqual(len(profiles.data['tabs']), 1)

    def test_another_structure_or_label_is_not_taken_for_it(self):
        delirium = stash_frame('delirium')
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            tab = profiles.register('Delirium', 'A', selected_tab_rect(delirium), delirium, 'delirium')
            tab['auto_registered'] = True
            self.assertIsNone(profiles.match_label(delirium, 'A', 'abyss'), 'Another structure')
            self.assertIsNone(profiles.match_label(stash_frame('essences'), 'A', 'delirium'), 'Another label')
            self.assertIsNone(profiles.match_label(delirium, 'B', 'delirium'), 'Another league')


class ManualLinkTests(unittest.TestCase):
    def test_relink_learns_the_tab_again_from_the_frame(self):
        frame = stash_frame('delirium')
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            tab = profiles.register('34', 'A', selected_tab_rect(frame), frame, 'delirium')
            tab['auto_registered'] = True
            # The tab looks different now (hover, colour): nothing finds it.
            later = frame.copy()
            later[97:124, 40:600] = 255 - later[97:124, 40:600]
            self.assertIsNone(profiles.identify(later, 'A')[0])
            self.assertIsNone(profiles.match_label(later, 'A', 'delirium'))
            profiles.relink(tab['id'], later, 'delirium')
            self.assertEqual(profiles.identify(later, 'A')[0]['id'], tab['id'])
            self.assertEqual(Profiles(Path(directory)).identify(later, 'A')[0]['id'], tab['id'], 'Saved')

    def test_relink_refuses_another_structure_and_a_hidden_tab_bar(self):
        frame = stash_frame('delirium')
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            tab = profiles.register('34', 'A', selected_tab_rect(frame), frame, 'delirium')
            with self.assertRaises(ValueError):
                profiles.relink(tab['id'], frame, 'abyss')
            hidden = frame.copy()
            hidden[90:130] = 0
            with self.assertRaises(ValueError):
                profiles.relink(tab['id'], hidden, 'delirium')

    def test_a_new_tab_is_registered_under_the_typed_name(self):
        frame = stash_frame('ritual')
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            tab = profiles.register_selected(' 31 ', 'A', frame, 'ritual')
            self.assertEqual((tab['name'], tab['visible_name'], tab['layout_id']), ('31', '31', 'ritual'))
            self.assertEqual(profiles.identify(frame, 'A')[0]['id'], tab['id'])
            with self.assertRaises(ValueError):
                profiles.register_selected('31', 'A', frame, 'ritual')


if __name__ == '__main__':
    unittest.main()
