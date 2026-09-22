"""Guard the headroom of every recognition decision against silent erosion.

A pass/fail suite cannot tell a decision that barely held from one that held
comfortably. That distinction is what this project keeps getting wrong: the
structural separation threshold was lowered from 18 to 12 points to make Runes
detect, and nothing showed what it cost the other stashes.

These tests compare the current headroom against `margin_baseline.json`. A drop
fails with the numbers in the message; an improvement is reported so the baseline
can be refreshed deliberately with `python -m tests.margins --update`.
"""
import json
import unittest

from tests import margins

# Recognition is deterministic here: identical fixtures, no network, no OCR.
# The slack only absorbs floating-point drift across BLAS/OpenCV builds.
TOLERANCE = 1e-3


class MarginBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.measured = {m.name: m for m in margins.measure()}
        cls.baseline = json.loads(margins.BASELINE.read_text('utf-8'))

    def test_baseline_covers_exactly_the_measured_decisions(self):
        """A new decision must be added to the baseline, not silently unguarded."""
        self.assertEqual(set(self.measured), set(self.baseline),
                         'run `python -m tests.margins --update` after adding or '
                         'removing a measurement')

    def test_no_decision_lost_headroom(self):
        regressions = []
        for name, current in sorted(self.measured.items()):
            recorded = self.baseline[name]
            if current.kind == 'count':
                continue
            if current.headroom < recorded['headroom'] - TOLERANCE:
                regressions.append(
                    f'{name}: headroom {current.headroom:.4f} < baseline '
                    f'{recorded["headroom"]:.4f} (measured {current.measured:.4f} '
                    f'vs threshold {current.threshold:.4f}, {current.detail})')
        self.assertFalse(regressions, 'headroom shrank:\n  ' + '\n  '.join(regressions))

    def test_counts_did_not_change(self):
        """Fewer identified cells is a regression even when every margin holds."""
        for name, current in sorted(self.measured.items()):
            if current.kind != 'count':
                continue
            with self.subTest(name):
                self.assertEqual(current.measured, self.baseline[name]['measured'],
                                 f'{name} changed: {current.detail}')

    def test_every_decision_still_passes_its_threshold(self):
        for name, current in sorted(self.measured.items()):
            if current.kind == 'count':
                continue
            with self.subTest(name):
                self.assertGreaterEqual(
                    current.headroom, 0,
                    f'{name} would flip: measured {current.measured:.4f} '
                    f'vs threshold {current.threshold:.4f} ({current.direction})')

    def test_thresholds_were_not_relaxed(self):
        """Lowering a threshold *raises* headroom, so it hides itself.

        That is the failure mode this project actually has: the structural
        separation was lowered from 18 to 12 points for Runes, and nothing
        reported what it cost. Pinning the thresholds makes such a change a
        deliberate act that requires refreshing the baseline and re-measuring
        every fixture.
        """
        relaxed = []
        for name, current in sorted(self.measured.items()):
            recorded = self.baseline[name]['threshold']
            if abs(current.threshold - recorded) > TOLERANCE:
                direction = 'relaxed' if (
                    current.threshold < recorded if current.direction == 'min'
                    else current.threshold > recorded) else 'tightened'
            else:
                continue
            relaxed.append(f'{name}: threshold {direction} from {recorded} to '
                           f'{current.threshold}')
        self.assertFalse(relaxed, 'thresholds changed; re-measure every fixture '
                                  'then run `python -m tests.margins --update`:\n  '
                         + '\n  '.join(relaxed))

    def test_runes_separation_stays_the_documented_tight_one(self):
        """The known fragile decision, pinned so a threshold change is visible.

        Runes beats Kalguuran by 0.15 against a required 0.12. That 0.03 is the
        smallest structural headroom in the project and the reason the threshold
        must not be lowered again without re-measuring every fixture.
        """
        runes = self.measured['runes_real.border_margin']
        self.assertGreaterEqual(runes.headroom, 0.03 - TOLERANCE)
        self.assertLess(runes.headroom, 0.10,
                        'if this grew, the fixtures or the threshold changed; '
                        'refresh the baseline and this comment')

    def test_report_renders_and_flags_tight_decisions(self):
        text = margins.report(list(self.measured.values()))
        self.assertIn('headroom', text)
        self.assertIn('runes_real.border_margin', text)
        self.assertIn('TIGHT', text, 'the tight decisions must stay visible')
        self.assertNotIn('FAILS', text)


if __name__ == '__main__':
    unittest.main()
