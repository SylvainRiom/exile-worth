"""Regression on the user's real 1920x1080 captures of four single-view tabs:
Abyss, Delirium, Essences and Ritual (23 September 2026).

The expected readings were checked by eye against the artwork, cell by cell,
not copied from the recogniser. See tests/fixtures/stash_real/README.md.
"""
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from exile_worth.icons import IconMatcher
from exile_worth.layouts import LAYOUTS, aligned_slots
from exile_worth.model import Reason
from exile_worth.vision import DigitReader, Profiles, Scanner

FIXTURES = Path(__file__).parent / 'fixtures'
ROOT = FIXTURES / 'stash_real'
TABS = {'abyss': 'Abyss', 'delirium': 'Delirium', 'essences': 'Essences', 'ritual': 'Ritual'}


def stash_frame(name):
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[:765, :655] = cv2.imread(str(ROOT / f'{name}.png'))
    return frame


def icons():
    """The four categories' artwork plus the Expedition set, as rivals."""
    images = {}
    for folder in (ROOT / 'icons', FIXTURES / 'expedition_real' / 'icons'):
        for icon in sorted(folder.glob('*.png')):
            images.setdefault(icon.stem, cv2.imread(str(icon), cv2.IMREAD_UNCHANGED))
    return images


class RealStashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.truth = json.loads((ROOT / 'readings.json').read_text('utf-8'))
        cls.frames = {name: stash_frame(name) for name in TABS}
        cls.matcher = IconMatcher(icons())
        cls.digits = DigitReader()

    def test_each_tab_is_recognised_from_its_borders(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), matcher=IconMatcher({}))
            for name, frame in self.frames.items():
                with self.subTest(tab=name):
                    self.assertEqual(scanner.detect_layout(frame, borders_only=True), name)

    def test_the_declared_cells_sit_on_the_real_borders(self):
        for name, frame in self.frames.items():
            with self.subTest(tab=name):
                reference = LAYOUTS[name].slots
                shifts = {(x - reference[s][0], y - reference[s][1])
                          for s, (x, y, _w, _h) in aligned_slots(frame, name).items()}
                self.assertEqual(len(shifts), 1)
                self.assertLessEqual(max(map(abs, shifts.pop())), 3)

    def test_items_and_counts_match_the_verified_truth(self):
        for name, frame in self.frames.items():
            truth = self.truth[name]
            with tempfile.TemporaryDirectory() as directory:
                scanner = Scanner(Profiles(Path(directory)), digits=self.digits, matcher=self.matcher)
                readings = {r.slot: r for r in scanner.read(frame, name)}
            for slot, (item, quantity) in truth['read'].items():
                with self.subTest(tab=name, slot=slot):
                    self.assertEqual((readings[slot].item, readings[slot].quantity), (item, quantity))
            for slot, item in truth['count_unreadable'].items():
                with self.subTest(tab=name, slot=slot):
                    self.assertEqual(readings[slot].item, item)
                    self.assertIsNone(readings[slot].quantity)
            # Bright ghosts stay unidentified: never named, never counted.
            for slot in truth['unnamed']:
                with self.subTest(tab=name, slot=slot):
                    self.assertIsNone(readings[slot].item)
                    self.assertIsNone(readings[slot].quantity)
            known = set(truth['read']) | set(truth['count_unreadable']) | set(truth['unnamed'])
            for slot, reading in readings.items():
                if slot not in known:
                    with self.subTest(tab=name, slot=slot):
                        self.assertEqual(reading.reason, Reason.EMPTY)

    def test_the_active_tab_title_is_read_among_coloured_tabs(self):
        from rapidocr_onnxruntime import RapidOCR
        from exile_worth.vision import active_tab
        ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        for name, title in TABS.items():
            with self.subTest(tab=name):
                self.assertEqual(active_tab(self.frames[name], ocr)[0], title)

    def test_new_tabs_do_not_claim_the_older_captures(self):
        from tests.margins import expedition_frame, load_frame
        from tests.test_breach_real import breach_frame
        frames = {'expedition': expedition_frame(), 'breach': breach_frame()}
        for view in ('runes', 'kalguuran', 'soul_cores', 'idols', 'ancient_augments'):
            frames[view] = load_frame(FIXTURES / 'runes_real' / f'{view}.png')
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), matcher=IconMatcher({}))
            for own, frame in frames.items():
                with self.subTest(capture=own):
                    self.assertEqual(scanner.detect_layout(frame, borders_only=True), own)
                    scores = dict((layout, score) for score, layout in scanner.last_layout_scores)
                    # Closest measured: Delirium on the Kalguuran capture, 0.562
                    # against 0.967, a lead of 0.40.
                    for name in TABS:
                        self.assertGreater(scores[own] - scores[name], .3)


class MisregisteredTabTests(unittest.TestCase):
    """The user's Ritual tab was saved as Runes before Ritual had a geometry."""

    def test_an_empty_tab_saved_as_runes_is_corrected_to_ritual_with_its_uuid(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from exile_worth.app import App
        frame = stash_frame('ritual')
        rect = (491, 97, 101, 27)
        with tempfile.TemporaryDirectory() as directory:
            profiles = Profiles(Path(directory))
            old = profiles.register('Ritual', 'A', rect, frame, 'runes')
            old['auto_registered'] = True
            old['visible_name'] = 'Ritual'
            profiles.save()
            app = SimpleNamespace(layout_override=None, scanner=Scanner(profiles, matcher=IconMatcher({})))
            # A Runes profile used to refuse every other family, so the wrong
            # type could never be corrected.
            self.assertEqual(App.resolve_layout(app, frame, old), 'ritual')
            with patch('exile_worth.vision.active_tab', return_value=('Ritual', rect)):
                fixed, _ = profiles.observe(frame, 'A', 'ritual', object())
            self.assertEqual(fixed['id'], old['id'])
            self.assertEqual(fixed['layout_id'], 'ritual')
            self.assertEqual(len(profiles.data['tabs']), 1)

    def test_the_icon_fallback_never_registers_a_tab(self):
        from types import SimpleNamespace
        from exile_worth.app import App
        for basis, override, allowed in (('icons', None, False), (None, None, False),
                                         ('borders', None, True), ('selector', None, True),
                                         ('icons', 'ritual', True)):
            with self.subTest(basis=basis, override=override):
                app = SimpleNamespace(layout_override=override,
                                      scanner=SimpleNamespace(last_layout_basis=basis))
                self.assertEqual(App.may_register(app), allowed)
