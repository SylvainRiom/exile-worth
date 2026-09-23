"""The session log is the tool for diagnosing a recognition failure.

These tests pin the things that make it useful: the numbers behind a verdict,
the near-miss on a refused cell, tracebacks, and the absence of per-frame spam.
"""
import json
import logging
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from exile_worth import diagnostics
from exile_worth.diagnostics import ChangeGate, format_scores
from exile_worth.icons import IconMatcher
from exile_worth.vision import Profiles, Scanner

FIXTURES = Path(__file__).parent / 'fixtures'


class Digits:
    last_approximate = False

    def read(self, image):
        return None, 0.0


def detach_handlers():
    for handler in list(diagnostics.log.handlers):
        handler.close()
        diagnostics.log.removeHandler(handler)
    diagnostics._configured = False


def fresh_log(directory):
    """diagnostics.setup() is deliberately once-per-process; rebuild for a test."""
    detach_handlers()
    diagnostics.setup(directory, level='DEBUG')
    return diagnostics.log


def read_log(directory):
    for handler in diagnostics.log.handlers:
        handler.flush()
    return (Path(directory) / 'session.log').read_text('utf-8')


class ChangeGateTests(unittest.TestCase):
    def test_only_the_first_of_an_unchanged_verdict_passes(self):
        gate = ChangeGate()
        self.assertTrue(gate.passes('layout', 'a'))
        self.assertFalse(gate.passes('layout', 'a'))
        self.assertTrue(gate.passes('layout', 'b'))
        self.assertTrue(gate.passes('layout', 'a'))
        # Keys are independent: one noisy event must not mask another.
        self.assertTrue(gate.passes('identity', 'a'))

    def test_format_scores_ranks_and_truncates(self):
        scores = [(0.1, 'low'), (0.9, 'high'), (0.5, 'mid')]
        self.assertEqual(format_scores(scores, limit=2), 'high=0.900, mid=0.500')
        self.assertEqual(format_scores([]), '')


class SessionLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        fresh_log(self.directory)

    def tearDown(self):
        detach_handlers()
        self.temp.cleanup()

    def test_failure_records_the_traceback_not_just_the_message(self):
        def inner():
            raise ValueError('boom')
        try:
            inner()
        except ValueError as exc:
            diagnostics.failure('unit', exc)
        text = read_log(self.directory)
        self.assertIn('unit: boom', text)
        self.assertIn('Traceback (most recent call last)', text)
        # The frame that actually raised must be identifiable.
        self.assertIn('in inner', text)

    def test_setup_survives_an_unusable_directory(self):
        detach_handlers()
        blocked = self.directory / 'a-file'
        blocked.write_text('not a directory', encoding='utf-8')
        diagnostics.setup(blocked / 'nested', level='INFO')
        diagnostics.log.info('must not raise')

    def test_layout_verdict_records_the_numbers_and_does_not_repeat(self):
        scanner = Scanner(Profiles(self.directory), digits=Digits(), matcher=IconMatcher({}))
        blank = np.zeros((1080, 1920, 3), np.uint8)
        self.assertIsNone(scanner.detect_layout(blank, borders_only=True))
        first = read_log(self.directory)
        self.assertIn('layout: borders rejected', first)
        self.assertIn('< .55', first)          # the threshold that was missed
        self.assertIn('borders ', first)       # the ranking of every candidate
        for _ in range(5):
            scanner.detect_layout(blank, borders_only=True)
        self.assertEqual(read_log(self.directory).count('layout: borders rejected'),
                         1, 'an unchanged verdict must be logged once')

    def test_accepted_layout_records_score_and_margin(self):
        stash = cv2.imread(str(FIXTURES / 'expedition_real' / 'stash.png'), cv2.IMREAD_COLOR)
        meta = json.loads((FIXTURES / 'expedition_real' / 'items.json').read_text('utf-8'))
        frame = np.zeros((1080, 1920, 3), np.uint8)
        x, y = meta.get('x', 0), meta.get('y', 0)
        frame[y:y+stash.shape[0], x:x+stash.shape[1]] = stash
        scanner = Scanner(Profiles(self.directory), digits=Digits(), matcher=IconMatcher({}))
        self.assertEqual(scanner.detect_layout(frame, borders_only=True), 'expedition')
        text = read_log(self.directory)
        self.assertIn('borders accepted expedition', text)
        self.assertIn('margin', text)
        self.assertIn('expedition=', text)
        # The margin over the runner-up is what a threshold change would erode.
        self.assertTrue(scanner.last_layout_scores[0][0] - scanner.last_layout_scores[1][0] > .12)

    def test_unidentified_cell_logs_the_near_miss(self):
        """The refused candidate and its margin are the point of the log."""
        icons = {}
        for icon in (FIXTURES / 'expedition_real' / 'icons').glob('*.png'):
            image = cv2.imread(str(icon), cv2.IMREAD_UNCHANGED)
            if image is not None:
                icons[icon.stem] = image
        stash = cv2.imread(str(FIXTURES / 'runes_real' / 'runes.png'), cv2.IMREAD_COLOR)
        frame = np.zeros((1080, 1920, 3), np.uint8)
        frame[:stash.shape[0], :stash.shape[1]] = stash
        scanner = Scanner(Profiles(self.directory), digits=Digits(), matcher=IconMatcher(icons))
        # Rune artwork against the Expedition catalogue: recognisable cells, no match.
        readings = scanner.read(frame, 'runes')
        unknown = [r for r in readings if r.item is None and r.reason != 'empty']
        self.assertTrue(unknown, 'expected unmatched cells for this combination')
        text = read_log(self.directory)
        self.assertIn('recognition runes:', text)
        self.assertIn('unidentified', text)
        self.assertIn('best=', text)
        self.assertIn('margin=', text)

    def test_frame_metrics_stay_at_debug_level(self):
        scanner = Scanner(Profiles(self.directory), digits=Digits(), matcher=IconMatcher({}))
        blank = np.zeros((1080, 1920, 3), np.uint8)
        scanner.read_incremental(blank, 'currency', ('league', 'tab'))
        self.assertIn('frame currency:', read_log(self.directory))
        diagnostics.log.setLevel(logging.INFO)
        scanner.read_incremental(blank, 'currency', ('league', 'tab'))
        self.assertEqual(read_log(self.directory).count('frame currency:'), 1)


if __name__ == '__main__':
    unittest.main()
