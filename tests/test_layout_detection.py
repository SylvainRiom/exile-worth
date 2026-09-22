import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from joy_tracker.app import App
from joy_tracker.layouts import LAYOUTS, aligned_slots
from joy_tracker.vision import Profiles, Scanner


class LayoutDetectionTests(unittest.TestCase):
    def test_shifted_expedition_grid_is_fitted_without_changing_currency_geometry(self):
        layout = LAYOUTS['expedition']
        original = dict(layout.slots)
        frame = np.zeros((1080,1920,3), np.uint8)
        for x,y,w,h in layout.slots.values():
            cv2.rectangle(frame, (x+13,y+4), (x+w+13,y+h+4), (90,110,140), 2)
        fitted = aligned_slots(frame, 'expedition')
        for slot,(x,y,w,h) in original.items():
            self.assertLessEqual(abs(fitted[slot][0] - (x+13)), 2)
            self.assertLessEqual(abs(fitted[slot][1] - (y+4)), 2)
        self.assertEqual(layout.slots, original)
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), digits=object())
            self.assertEqual(scanner.detect_layout(frame), 'expedition')

    def test_alignment_does_not_guess_from_blank_image(self):
        frame = np.zeros((1080,1920,3), np.uint8)
        self.assertEqual(aligned_slots(frame, 'expedition'), LAYOUTS['expedition'].slots)

    def test_empty_structures_detected_without_icons(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), digits=object())
            for layout in LAYOUTS.values():
                frame = np.zeros((1080,1920,3), np.uint8)
                for x,y,w,h in layout.slots.values():
                    cv2.rectangle(frame, (x,y), (x+w,y+h), (90,110,140), 2)
                self.assertEqual(scanner.detect_layout(frame), layout.id)
            self.assertIsNone(scanner.detect_layout(np.zeros_like(frame)))

    def test_unknown_never_reuses_previous_structure(self):
        app = SimpleNamespace(layout_override=None, active_layout_id='currency',
                              scanner=SimpleNamespace(detect_layout=lambda frame:None))
        self.assertIsNone(App.resolve_layout(app, None, None))
        app.active_layout_id = 'expedition'
        self.assertIsNone(App.resolve_layout(app, None, None))

    def test_manual_type_wins_over_old_registered_type(self):
        app = SimpleNamespace(layout_override='expedition')
        self.assertEqual(App.resolve_layout(app, None, {'layout_id':'currency'}), 'expedition')
