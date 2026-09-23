"""Measure how comfortably each recognition decision passes its threshold.

The suite is otherwise pass/fail, which hides the thing that actually breaks this
project: a threshold nudged for one stash quietly leaves another one a hair from
failing. Every measurement here reports `headroom`, the distance between what was
measured and the value at which the decision would flip. A regression shows up as
shrinking headroom long before a test turns red.

`python -m tests.margins` prints the table; `test_margins.py` enforces the floors
recorded in `margin_baseline.json`.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np

from exile_worth.icons import IconMatcher
from exile_worth.layouts import LAYOUTS, aligned_slots
from exile_worth.model import Reason
from exile_worth.vision import (Profiles, Scanner, crop, known_symbol,
                                selected_tab_rect, symbol_reference)

FIXTURES = Path(__file__).parent / 'fixtures'
BASELINE = Path(__file__).parent / 'margin_baseline.json'

# Thresholds the decisions are compared against, from vision.py and icons.py.
BORDER_SCORE_MIN = .55
BORDER_MARGIN_MIN = .12
ICON_THRESHOLD = .92
ICON_MARGIN_MIN = .015


@dataclass(frozen=True)
class Margin:
    name: str
    measured: float
    threshold: float
    headroom: float          # distance to the flip point; negative would fail
    direction: str = 'min'   # 'min': measured must stay above; 'max': below
    kind: str = 'margin'     # 'count' values are exact tallies, not margins
    detail: str = ''

    @staticmethod
    def of(name, measured, threshold, detail='', direction='min', kind='margin'):
        measured, threshold = float(measured), float(threshold)
        headroom = measured - threshold if direction == 'min' else threshold - measured
        return Margin(name, round(measured, 4), round(threshold, 4),
                      round(headroom, 4), direction, kind, detail)


class Digits:
    """Quantities are irrelevant here; only the visual decisions are measured."""
    last_approximate = False

    def read(self, image):
        return None, 0.0


def load_frame(path, x=0, y=0):
    crop_image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if crop_image is None:
        raise FileNotFoundError(path)
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[y:y+crop_image.shape[0], x:x+crop_image.shape[1]] = crop_image
    return frame


def expedition_frame():
    meta = json.loads((FIXTURES / 'expedition_real' / 'items.json').read_text('utf-8'))
    return load_frame(FIXTURES / 'expedition_real' / 'stash.png',
                      meta.get('x', 0), meta.get('y', 0))


def expedition_icons():
    images = {}
    for icon in sorted((FIXTURES / 'expedition_real' / 'icons').glob('*.png')):
        image = cv2.imread(str(icon), cv2.IMREAD_UNCHANGED)
        if image is not None:
            images[icon.stem] = image
    return images


def layout_margins(frame, expected, label):
    """How far the winning structure sits from the runner-up and the floor."""
    with tempfile.TemporaryDirectory() as directory:
        scanner = Scanner(Profiles(Path(directory)), digits=Digits(), matcher=IconMatcher({}))
        detected = scanner.detect_layout(frame, borders_only=True)
        scores = scanner.last_layout_scores
    assert detected == expected, f'{label}: detected {detected!r}, expected {expected!r}'
    (best, winner), (second, runner) = scores[0], scores[1]
    return [
        Margin.of(f'{label}.border_score', best, BORDER_SCORE_MIN, f'{winner}'),
        Margin.of(f'{label}.border_margin', best - second, BORDER_MARGIN_MIN,
                  f'{winner} over {runner} ({second:.3f})'),
    ]


def icon_margins(frame, layout_id, icons, label):
    """The weakest identified cell is the one a threshold change breaks first."""
    with tempfile.TemporaryDirectory() as directory:
        scanner = Scanner(Profiles(Path(directory)), digits=Digits(), matcher=IconMatcher(icons))
        readings = scanner.read(frame, layout_id)
        matches = scanner.last_matches
    identified = [r for r in readings if r.item]
    assert identified, f'{label}: no cell identified'
    # A cell the matcher accepted outright, versus one the documented fixed-slot
    # families disambiguated. Only the first kind is governed by ICON_MARGIN_MIN.
    by_matcher = [r for r in identified if matches[r.slot].item]
    by_position = [r for r in identified if not matches[r.slot].item]
    assert by_matcher, f'{label}: no cell accepted by the matcher alone'
    scored = [(matches[r.slot].confidence, matches[r.slot].margin, r.slot) for r in by_matcher]
    weak_score = min(scored)
    weak_margin = min((margin, score, slot) for score, margin, slot in scored)
    empty = [r for r in readings if r.reason == Reason.EMPTY]
    results = [
        Margin.of(f'{label}.icon_score_min', weak_score[0], ICON_THRESHOLD,
                  f'weakest cell {weak_score[2]}'),
        Margin.of(f'{label}.icon_margin_min', weak_margin[0], ICON_MARGIN_MIN,
                  f'closest call {weak_margin[2]}'),
        Margin.of(f'{label}.identified', len(identified), len(identified),
                  f'{len(by_matcher)} by matcher + {len(by_position)} by position', kind='count'),
        Margin.of(f'{label}.empty', len(empty), len(empty), f'{len(empty)} cells', kind='count'),
    ]
    return results


def alignment_margins(frame, layout_id, label):
    """Fitted rectangles must still sit on the cell borders."""
    slots = aligned_slots(frame, layout_id)
    reference = LAYOUTS[layout_id].slots
    shifts = {(x - reference[slot][0], y - reference[slot][1])
              for slot, (x, y, _w, _h) in slots.items()}
    assert len(shifts) == 1, f'{label}: alignment must be one common translation'
    dx, dy = shifts.pop()
    return [Margin.of(f'{label}.alignment_shift', max(abs(dx), abs(dy)), 20,
                      f'dx={dx} dy={dy}, refused beyond +/-20', direction='max')]


# Thresholds from `selected_tab_rect`, `active_tab` and `known_symbol`.
TAB_RUN_MIN = 32
ARROW_ROWS_MIN = 2
ARROW_TOTAL_MIN = 8
SYMBOL_THRESHOLD = .80


def dollar_frame():
    """The `$$` scenario: the real stash with SAGA deselected and the real menu."""
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[:765, :645] = cv2.imread(str(FIXTURES / 'expedition_real' / 'stash.png'),
                                   cv2.IMREAD_COLOR)
    frame[121, 500:591] = frame[126, 500:591]
    frame[182:225, 666:855] = cv2.imread(str(FIXTURES / 'tab_labels' / 'dollar_selected_menu.png'),
                                         cv2.IMREAD_COLOR)
    return frame


def tab_label_margins(frame, label):
    """Selecting and naming the `$$` tab, whose label OCR cannot read.

    The two `symbol_*` scores are close to tautological: the templates in
    `reference_tabs/` were cut from this very capture, so a score near 1.0 says
    the matcher still recognises its own source, **not** that `$$` is robust in
    general. They are worth guarding anyway: preprocessing changes show up here
    first. The run length and the arrow counts are real measurements.
    """
    results = []
    rect = selected_tab_rect(frame)
    assert rect is not None, f'{label}: no tab appears selected'

    strip = frame[121, 40:594].astype(np.int16)
    high, low = strip.max(axis=1), strip.min(axis=1)
    active = (high > 48) & ((high - low > 10) | (high > 65))
    runs, start = [], None
    for index, value in enumerate([*active, False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append(index - start)
            start = None
    results.append(Margin.of(f'{label}.tab_run_length', max(runs), TAB_RUN_MIN,
                             f'longest lit run of {len(runs)}'))

    arrow = frame[90:755, 666:686].astype(np.int16)
    warm = (arrow[:, :, 2] > 100) & (arrow[:, :, 2] > arrow[:, :, 1] + 30) &            (arrow[:, :, 2] > arrow[:, :, 0] + 20)
    rows = warm.sum(axis=1)
    results.append(Margin.of(f'{label}.arrow_rows', rows.max(), ARROW_ROWS_MIN,
                             'widest warm row beside the menu'))
    results.append(Margin.of(f'{label}.arrow_total', rows.sum(), ARROW_TOTAL_MIN,
                             'warm pixels in the arrow column'))

    peak = int(rows.argmax()) + 90
    images = {'menu': frame[max(90, peak-13):min(755, peak+13), 685:854],
              'top': crop(frame, rect)}
    for place, image in images.items():
        template = symbol_reference(place)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        score = float(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED).max())
        results.append(Margin.of(f'{label}.symbol_{place}', score, SYMBOL_THRESHOLD,
                                 'template cut from this capture'))
        assert known_symbol(image, place) == '$$', f'{label}: {place} no longer reads $$'
    return results


# The five Runes views. `runes` keeps the original label so its recorded
# baseline entries survive; the other four were captured on 22 September 2026.
RUNE_VIEWS = {
    'runes': 'runes_real',
    'kalguuran': 'kalguuran_real',
    'soul_cores': 'soul_cores_real',
    'idols': 'idols_real',
    'ancient_augments': 'ancient_augments_real',
}


def measure():
    results = []
    expedition = expedition_frame()
    results += layout_margins(expedition, 'expedition', 'expedition_real')
    results += alignment_margins(expedition, 'expedition', 'expedition_real')
    results += icon_margins(expedition, 'expedition', expedition_icons(), 'expedition_real')

    # All five Runes views, from real captures of one session. The first view
    # keeps the `runes_real` label its baseline entries were recorded under.
    for view, label in RUNE_VIEWS.items():
        frame = load_frame(FIXTURES / 'runes_real' / f'{view}.png')
        results += layout_margins(frame, view, label)
        results += alignment_margins(frame, view, label)

    results += tab_label_margins(dollar_frame(), 'dollar_tab')
    return results


def report(results=None):
    results = results or measure()
    width = max(len(m.name) for m in results)
    lines = [f'{"decision".ljust(width)}  {"measured":>9}  {"threshold":>9}  {"headroom":>9}  detail',
             '-' * (width + 45)]
    for m in results:
        if m.kind == 'count':
            flag = ''
        elif m.headroom < 0:
            flag = '  <-- FAILS'
        elif m.headroom < .05:
            flag = '  <-- TIGHT'
        else:
            flag = ''
        lines.append(f'{m.name.ljust(width)}  {m.measured:9.4f}  {m.threshold:9.4f}  '
                     f'{m.headroom:9.4f}  {m.detail}{flag}')
    return '\n'.join(lines)


def write_baseline(path=BASELINE):
    data = {m.name: asdict(m) for m in measure()}
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', 'utf-8')
    return data


if __name__ == '__main__':
    import sys
    if '--update' in sys.argv:
        write_baseline()
        print(f'baseline written to {BASELINE}')
    print(report())
