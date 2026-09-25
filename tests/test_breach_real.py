"""Regression on the user's real 1920x1080 capture of the Breach tab, Catalysts view."""
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from exile_worth.icons import IconMatcher
from exile_worth.layouts import LAYOUTS, aligned_slots, expected_slot_count, layout_family
from exile_worth.model import Reason
from exile_worth.vision import DigitReader, Profiles, Scanner

FIXTURES = Path(__file__).parent / 'fixtures'
BREACH = FIXTURES / 'breach_real'


def breach_frame():
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[:765, :655] = cv2.imread(str(BREACH / 'catalysts.png'))
    return frame


def icons():
    """Breach references plus the Expedition ones, so the matcher has rivals."""
    images = {}
    for folder in (BREACH / 'icons', FIXTURES / 'expedition_real' / 'icons'):
        for icon in sorted(folder.glob('*.png')):
            images[icon.stem] = cv2.imread(str(icon), cv2.IMREAD_UNCHANGED)
    return images


class RealBreachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = breach_frame()
        cls.truth = json.loads((BREACH / 'readings.json').read_text('utf-8'))

    def test_the_catalysts_view_is_recognised_from_its_borders(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), matcher=IconMatcher({}))
            self.assertEqual(scanner.detect_layout(self.frame, borders_only=True), 'breach')
        self.assertEqual(layout_family('breach'), 'breach')

    def test_the_declared_cells_sit_on_the_real_borders(self):
        slots = aligned_slots(self.frame, 'breach')
        reference = LAYOUTS['breach'].slots
        self.assertEqual(len(slots), 29)
        shifts = {(x - reference[s][0], y - reference[s][1]) for s, (x, y, _w, _h) in slots.items()}
        self.assertEqual(len(shifts), 1)
        self.assertLessEqual(max(map(abs, shifts.pop())), 3)

    def test_a_breach_tab_expects_every_cell_of_its_views(self):
        self.assertEqual(expected_slot_count({'layout_id': 'breach'}), 29)

    def test_items_and_counts_are_read_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), digits=DigitReader(), matcher=IconMatcher(icons()))
            readings = {r.slot: r for r in scanner.read(self.frame, 'breach')}
        for slot, (item, quantity) in self.truth.items():
            with self.subTest(slot=slot):
                self.assertEqual((readings[slot].item, readings[slot].quantity), (item, quantity))
                self.assertFalse(readings[slot].approximate)
        # B02, the Breachlord Sac ghost, is brighter than `visually_empty`
        # allows; it shows no counter, so it is empty like the others.
        empty = [slot for slot in LAYOUTS['breach'].slots if slot not in self.truth]
        for slot in empty:
            with self.subTest(slot=slot):
                self.assertEqual(readings[slot].reason, Reason.EMPTY)

    def test_breach_does_not_claim_the_other_real_captures(self):
        from tests.margins import expedition_frame, load_frame
        frames = [expedition_frame()] + [load_frame(FIXTURES / 'runes_real' / f'{view}.png')
                                         for view in ('runes', 'kalguuran', 'soul_cores', 'idols', 'ancient_augments')]
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), matcher=IconMatcher({}))
            for frame in frames:
                self.assertNotEqual(scanner.detect_layout(frame, borders_only=True), 'breach')
                scores = dict((layout, score) for score, layout in scanner.last_layout_scores)
                self.assertLess(scores['breach'], .55)

    def test_the_selected_tab_is_the_one_coloured_like_the_line_below(self):
        """Every coloured tab is lit at y=121; the red line names BREACH, not Abyss."""
        from rapidocr_onnxruntime import RapidOCR
        from exile_worth.vision import active_tab, selected_tab_rect
        rect = selected_tab_rect(self.frame)
        self.assertLess(rect[0], 60)
        ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        self.assertEqual(active_tab(self.frame, ocr)[0], 'BREACH')

    def test_the_menu_icon_read_as_a_letter_is_dropped_only_before_the_same_title(self):
        from exile_worth.vision import without_menu_icon
        self.assertEqual(without_menu_icon('B BREACH', 'BREACH'), 'BREACH')
        self.assertEqual(without_menu_icon('B OTHER', 'BREACH'), 'B OTHER')
        self.assertEqual(without_menu_icon('BREACH', 'BREACH'), 'BREACH')
        self.assertEqual(without_menu_icon('Maps', None), 'Maps')
