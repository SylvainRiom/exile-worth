from __future__ import annotations

import json
import re
import sqlite3
import time
import unicodedata
from contextlib import closing
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np

from .diagnostics import ChangeGate, format_scores, log
from .model import DATA, Reading, Reason
from .i18n import t
from .catalog import reference_items
from .icons import IconMatch, IconMatcher, SAGA_FAMILY
from .layouts import (ALL_SLOTS, CURRENCY_SLOTS, LAYOUTS, RUNE_PAGES, layout_for_tab, aligned_slots,
                      edge_maps, LEGACY_EXPEDITION_SLOTS, has_views, layout_family, selector_underlines)

# Inner rectangles, measured on the user's 1920x1080 currency tab.
SLOTS = CURRENCY_SLOTS  # Compatibility for existing profiles and callers.

# Fixed three-column tiers in the standard currency tab. Position resolves only
# a family already confirmed from its artwork; it cannot invent an identity.
TIER_ITEMS = {}
POSITION_FAMILIES = {}
for row, family in enumerate([
    ('transmute','greater-orb-of-transmutation','perfect-orb-of-transmutation'),
    ('aug','greater-orb-of-augmentation','perfect-orb-of-augmentation'),
    ('regal','greater-regal-orb','perfect-regal-orb'),
    ('exalted','greater-exalted-orb','perfect-exalted-orb'),
    ('chaos','greater-chaos-orb','perfect-chaos-orb'),
], 1):
    for column, item in enumerate(family, 1):
        TIER_ITEMS[f'L{row}{column}'] = item
        POSITION_FAMILIES[f'L{row}{column}'] = set(family)

# Confirmed against the full Expedition screenshot, not the editable tab name.
# Resolve only a confidently recognised saga family; silhouettes remain unknown.
SAGA_ITEMS = ('medveds-saga', 'voranas-saga', 'uhtreds-saga', 'olroths-saga')
for slot, item in zip(('E03', 'E04', 'E05', 'E06'), SAGA_ITEMS):
    TIER_ITEMS[slot] = item
    POSITION_FAMILIES[slot] = SAGA_FAMILY


# Dedicated cells: the game accepts only one item in each. Where the item is
# known, it settles near-identical artwork (the same essence at the same tier,
# diluted emotions) and a clearly different match is refused, never renamed.
# Established from real captures (filled cells) and the game's order (ghosts).
SLOT_ITEMS = {}
_ESSENCE_ROWS = (
    [(f'ES{4*row+column+1:02}', base) for row, base in enumerate(
        ('the-body', 'the-mind', 'enhancement', 'flames', 'insulation', 'ice',
         'thawing', 'electricity', 'grounding', 'ruin')) for column in range(4)]
    + [(f'ES{41+4*row+column:02}', base) for row, base in enumerate(
        ('command', 'abrasion', 'sorcery', 'haste', 'alacrity', 'seeking',
         'battle', 'the-infinite', 'opulence')) for column in range(4)])
for (slot, base), tier in zip(_ESSENCE_ROWS, ('lesser-', '', 'greater-', 'perfect-') * 19):
    SLOT_ITEMS[slot] = f'{tier}essence-of-{base}'
# These two lesser essences do not exist; their cells stay unassigned.
for slot in ('ES01', 'ES65'):
    del SLOT_ITEMS[slot]
SLOT_ITEMS.update(zip(('ES82', 'ES83', 'ES84', 'ES85', 'ES86', 'ES87'), (
    'essence-of-hysteria', 'essence-of-horror', 'essence-of-delirium',
    'essence-of-insanity', 'essence-of-the-abyss', 'essence-of-the-breach')))
_EMOTIONS = ('diluted-liquid-ire', 'diluted-liquid-guilt', 'diluted-liquid-greed',
             'liquid-disgust', 'liquid-despair', 'concentrated-liquid-fear',
             'liquid-paranoia', 'liquid-envy', 'concentrated-liquid-suffering',
             'concentrated-liquid-isolation')
_POTENT = ('potent-liquid-melancholy', 'potent-liquid-ferocity', 'potent-liquid-contempt')
SLOT_ITEMS.update(zip(('DE01', 'DE02', 'DE03'), ('simulacrum-splinter', 'simulacrum', 'raven-touched-shard')))
SLOT_ITEMS.update(zip([f'DE{n:02}' for n in range(4, 14)], _EMOTIONS))
SLOT_ITEMS.update(zip([f'DE{n:02}' for n in range(14, 24)], [f'ancient-{item}' for item in _EMOTIONS]))
SLOT_ITEMS.update(zip([f'DE{n:02}' for n in range(27, 33)], _POTENT + tuple(f'ancient-{item}' for item in _POTENT)))


# Cells that accept a family rather than one item. The Abyss tab's central
# diamond holds Abyss bones only (its bottom row holds abyssal omens, which
# poe.ninja files under Ritual, so the family is per cell, never per tab).
SLOT_FAMILIES = {}
_ABYSS_BONES = frozenset(item for item, entry in reference_items().items() if entry['category'] == 'Abyss')
SLOT_FAMILIES.update({f'AB{number:02}': _ABYSS_BONES for number in range(1, 14)})


def dedicated_item(slot, match):
    """The item a dedicated cell holds, None when the artwork disagrees.

    Returns `match.item` unchanged for a cell with no known item or family.
    """
    family = SLOT_FAMILIES.get(slot)
    if family is not None:
        return match.item if match.item in family else None
    expected = SLOT_ITEMS.get(slot)
    if expected is None:
        return match.item
    if match.item == expected or (match.item is None and expected in match.contenders):
        return expected
    return None


def layout_anchors(frame, layout_id='currency'):
    return {slot: crop(frame, (x-3,y-3,w+6,3)).tolist()
            for slot,(x,y,w,h) in LAYOUTS[layout_id].slots.items()}


def normalize(frame):
    height, width = frame.shape[:2]
    if abs(width / height - 16 / 9) > .025:
        raise ValueError(t('error.aspect_ratio'))
    return cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_AREA)


def crop(frame, rect):
    x, y, w, h = map(int, rect)
    return frame[y:y+h, x:x+w].copy()


def similarity(a, b):
    if a.shape != b.shape or a.size == 0:
        return 0.0
    # Absolute pixel agreement also rejects flat or black occlusions.
    return max(0.0, 1 - float(np.abs(a.astype(float) - b.astype(float)).mean()) / 100)


def icon_patch(frame, rect):
    image = crop(frame, rect)
    # Remove stack digits but retain lower-right variant markers.
    return image[19:, :]


def tab_key(name):
    return ' '.join(unicodedata.normalize('NFKC', name).casefold().split())


def read_tab_text(image, ocr):
    if image.size == 0:
        return None
    enlarged = cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    result, _ = ocr(enlarged)
    if not result:
        return None
    parts = sorted((min(p[0] for p in row[0]), max(p[0] for p in row[0]), row[1].strip(), float(row[2]))
                   for row in result if len(row) >= 3 and row[1].strip())
    # OCR sometimes reads a word's start twice (`De` over `Delirium`): a word
    # that begins the next one and overlaps its box is that echo.
    parts = [part for part, following in zip(parts, parts[1:] + [None])
             if not (following and following[2].casefold().startswith(part[2].casefold())
                     and part[1] > following[0])]
    words = [word for _,_,word,confidence in parts if confidence >= .85 and
             (re.search(r'[\w]', word, re.UNICODE) or re.fullmatch(r'[$€£¥]+', word))]
    return ' '.join(words).strip() or None


def high_contrast(image):
    """Inverted, stretched brightness: dark text on a lit menu row reads again."""
    value = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 2]
    return cv2.cvtColor(255 - cv2.normalize(value, None, 0, 255, cv2.NORM_MINMAX), cv2.COLOR_GRAY2BGR)


@lru_cache(maxsize=2)
def symbol_reference(place):
    path = Path(__file__).with_name('reference_tabs') / f'dollar_{place}.png'
    return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)


def known_symbol(image, place):
    """The game's $$ glyph is too small for OCR but has a stable shape."""
    template = symbol_reference(place)
    if template is None or image.shape[0] < template.shape[0] or image.shape[1] < template.shape[1]:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    score = float(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED).max())
    return '$$' if score >= .80 else None


def selected_tab_rect(frame):
    """Locate the bright lower edge of the selected tab without running OCR."""
    if frame.shape[0] < 765 or frame.shape[1] < 855:
        return None
    # At y=121 the selected tab continues into the bright lower border. Other
    # tabs end above it. The first small pinned tab can also remain highlighted.
    strip = frame[121, 40:594].astype(np.int16)
    high, low = strip.max(axis=1), strip.min(axis=1)
    active = (high > 48) & ((high-low > 10) | (high > 65))
    runs, start = [], None
    for index, value in enumerate([*active, False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if index-start >= 32:
                runs.append((40+start, 40+index))
            start = None
    if not runs:
        return None
    x1,x2 = pick_selected_run(frame, runs)
    return (max(40,x1-3), 97, min(594,x2+3)-max(40,x1-3), 27)


# How close a tab's colour must be to the underline to be the selected one.
# Measured: the selected tab 0.13 (BREACH) and 0.17 (SAGA), others 0.78 and more.
TAB_COLOUR_MAX = .4


def tab_colour_distances(frame, runs):
    """Chromaticity distance between each lit tab and the line under the bar.

    The line below the tab bar takes the selected tab's colour (red under
    BREACH, purple under SAGA). None when that line is too dark to tell.
    """
    line = frame[124:126, 40:594].reshape(-1, 3).astype(float).mean(axis=0)
    if line.sum() < 40:
        return None
    line = line / line.sum()
    distances = []
    for x1, x2 in runs:
        body = np.median(frame[112:120, x1+4:x2-4].reshape(-1, 3).astype(float), axis=0)
        distances.append(float(np.linalg.norm(body / max(body.sum(), 1) - line)))
    return distances


def pick_selected_run(frame, runs):
    """The selected tab among the lit ones.

    Coloured tabs are all lit at y=121, and a pinned folder may be too. The
    selected tab reaches down into the line under the bar, and that line has its
    colour; without a readable line, the rightmost lit tab is kept, as before.
    """
    distances = tab_colour_distances(frame, runs)
    if distances is not None:
        close = [(distance, run) for distance, run in zip(distances, runs) if distance <= TAB_COLOUR_MAX]
        if close:
            # Two tabs may share the selected colour; only the selected one
            # reaches down into the line.
            lower = frame[123, 40:594].max(axis=1) > 48
            reaching = [(distance, run) for distance, run in close
                        if lower[run[0]-40+4:run[1]-40-4].mean() > .8]
            return min(reaching or close)[1]
    return max(runs, key=lambda run: run[0])


def active_tab(frame, ocr):
    """Use the selected tab's highlight; confirm with the sidebar arrow when open."""
    rect = selected_tab_rect(frame)
    if rect is None:
        return None
    top_image = crop(frame,rect)
    name = read_tab_text(top_image, ocr) or known_symbol(top_image, 'top')

    # The expanded tab menu has a small warm arrow beside the active row.
    arrow = frame[90:755,666:686].astype(np.int16)
    warm = (arrow[:,:,2] > 100) & (arrow[:,:,2] > arrow[:,:,1]+30) & \
           (arrow[:,:,2] > arrow[:,:,0]+20)
    rows = warm.sum(axis=1)
    if rows.max() >= 2 and rows.sum() >= 8:
        peak = int(rows.argmax())+90
        menu_image = frame[max(90,peak-13):min(755,peak+13),685:854]
        selected = read_tab_text(menu_image,ocr) or known_symbol(menu_image, 'menu')
        selected = without_menu_icon(selected, name)
        if name and (not selected or tab_key(selected) != tab_key(name)):
            # A lit row (dark text on bright green) can defeat OCR. A second,
            # high-contrast read may only confirm the tab's title, never replace it.
            retry = without_menu_icon(read_tab_text(high_contrast(menu_image), ocr), name)
            if retry and tab_key(retry) == tab_key(name):
                selected = retry
        if not selected or (name and tab_key(selected) != tab_key(name)):
            return None
        name = selected
    return name, rect


def without_menu_icon(menu_name, top_name):
    """Drop the menu row's small tab icon when OCR read it as a letter.

    The Breach icon reads as `B`, giving `B BREACH` beside a `BREACH` tab. Only
    a single leading character goes, and only when the rest is the tab's own
    title, so a genuinely different name still refuses the match.
    """
    if not menu_name or not top_name:
        return menu_name
    words = menu_name.split()
    if len(words) > 1 and len(words[0]) == 1 and tab_key(' '.join(words[1:])) == tab_key(top_name):
        return ' '.join(words[1:])
    return menu_name


def label_score(frame, selected, tab):
    """How closely the tab's stored label matches the frame.

    With `selected`, the label is looked for where the selected tab is now,
    a few pixels either way since that rect is padded from the lit run's
    edges; without, at the rect the user drew when registering it.
    """
    label = np.array(tab['label'], np.uint8)
    if selected is None:
        return similarity(crop(frame, tab['rect']), label)
    height, width = label.shape[:2]
    return max(similarity(crop(frame, (selected[0]+dx, tab['rect'][1], width, height)), label)
               for dx in range(-LABEL_SHIFT, LABEL_SHIFT+1))


# How far a label is looked for around the selected tab's padded rect.
LABEL_SHIFT = 4


class Profiles:
    def __init__(self, directory=DATA):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.gate = ChangeGate()
        self.file = directory / 'profiles.json'
        self.data = json.loads(self.file.read_text('utf-8')) if self.file.exists() else {'tabs': [], 'slots': {}}

    def save(self):
        temporary = self.file.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), 'utf-8')
        temporary.replace(self.file)

    def register(self, name, league, rect, frame, layout_id='currency'):
        import uuid
        if not name.strip() or rect[2] < 12 or rect[3] < 8:
            raise ValueError(t('profile.need_name'))
        if any(t['name'] == name and t['league'] == league for t in self.data['tabs']):
            raise ValueError(t('profile.duplicate_name'))
        tab = dict(id=uuid.uuid4().hex, name=name, league=league, rect=rect,
                   label=crop(frame, rect).tolist(), layout_id=layout_id,
                   anchor_rects=LAYOUTS[layout_id].slots,
                   layout=layout_anchors(frame, layout_id))
        self.data['tabs'].append(tab)
        self.save()
        return tab

    def remove(self, tab_id):
        """Forget a registered tab; the next time it is seen it registers anew.

        The list is replaced, not mutated: the live loop iterates it on its
        own thread. The name is kept under `removed` so past history points
        can still name the tab.
        """
        tab = next((tab for tab in self.data['tabs'] if tab['id'] == tab_id), None)
        if tab is None:
            return None
        self.data['tabs'] = [other for other in self.data['tabs'] if other['id'] != tab_id]
        self.data.setdefault('removed', {})[tab_id] = tab['name']
        self.save()
        return tab

    def observe(self, frame, league, layout_id, ocr):
        """Register a confidently selected tab once, preserving its UUID later."""
        selected = active_tab(frame, ocr)
        if not selected:
            return None, t('profile.unreadable_tab')
        name, rect = selected
        if not name:
            return None, t('profile.unreadable_title')
        key = tab_key(name)
        matches = [tab for tab in self.data['tabs'] if tab['league'] == league and
                   layout_family(layout_for_tab(tab).id) == layout_family(layout_id) and
                   tab_key(tab.get('visible_name', tab['name'])) == key]
        if len(matches) > 1:
            return None, t('profile.ambiguous_label')
        if matches:
            tab = matches[0]
            previous = tab['rect']
            if abs(previous[0]-rect[0]) > 6 or abs(previous[2]-rect[2]) > 12:
                # Horizontal tab scrolling/reordering changes the label position.
                # A unique active name plus the same detected structure is enough
                # to retain its UUID; duplicate names remain rejected above.
                tab['rect'] = rect
                tab['label'] = crop(frame, rect).tolist()
                tab['anchor_rects'] = LAYOUTS[layout_id].slots
                tab['layout'] = layout_anchors(frame, layout_id)
                self.save()
                return tab, t('profile.moved', name=tab['name'])
            return tab, ''
        # Correct an auto-created profile that had the wrong structure before
        # this page was supported. Reuse its UUID only if no stock or history
        # has ever been stored for it.
        mistaken = [tab for tab in self.data['tabs'] if tab['league'] == league and
                    tab.get('auto_registered') and tab_key(tab.get('visible_name', tab['name'])) == key and
                    layout_family(layout_for_tab(tab).id) != layout_family(layout_id) and
                    abs(tab['rect'][0]-rect[0]) <= 6 and abs(tab['rect'][2]-rect[2]) <= 12]
        if len(mistaken) == 1 and self._no_stored_inventory(mistaken[0]['id']):
            tab = mistaken[0]
            tab['layout_id'] = layout_family(layout_id)
            tab['anchor_rects'] = LAYOUTS[layout_id].slots
            tab['layout'] = layout_anchors(frame, layout_id)
            self.save()
            return tab, t('profile.type_corrected', name=tab['name'])
        # A different stash structure may legitimately reuse the visible name.
        display = name
        if any(tab['league'] == league and tab['name'] == display for tab in self.data['tabs']):
            display = f'{name} ({LAYOUTS[layout_id].name})'
        tab = self.register(display, league, rect, frame, layout_family(layout_id))
        tab['visible_name'] = name
        tab['auto_registered'] = True
        self.save()
        return tab, t('profile.auto_added', name=display)

    def _no_stored_inventory(self, tab_id):
        database = self.directory / 'inventory.sqlite3'
        if not database.exists():
            return True
        try:
            # `with sqlite3.connect(...)` commits but does not close: use closing().
            with closing(sqlite3.connect(database)) as connection:
                return not any(connection.execute(f'SELECT 1 FROM {table} WHERE tab=? LIMIT 1',
                                                  (tab_id,)).fetchone()
                               for table in ('slots', 'history'))
        except sqlite3.Error:
            return False

    def calibrate(self, slot, item, frame, empty=False):
        if self.data['slots'].get(slot, {}).get('item', item) != item:
            self.data['slots'][slot] = {}
        entry = self.data['slots'].setdefault(slot, {})
        entry['item'] = item
        entry['override'] = True
        layout_id = next((key for key, layout in LAYOUTS.items() if slot in layout.slots), 'currency')
        rect = aligned_slots(frame, layout_id)[slot]
        entry['empty' if empty else 'icon'] = icon_patch(frame, rect).tolist()
        # Thin case-border strips serve as layout anchors independent of quantities.
        x,y,w,h = ALL_SLOTS[slot]
        entry['border'] = crop(frame, (x-3,y-3,w+6,3)).tolist()
        self.save()

    def identify(self, frame, league):
        candidates = []
        selected = selected_tab_rect(frame)
        for tab in self.data['tabs']:
            if tab['league'] == league:
                # The tab bar scrolls: a tab's position depends on where the
                # player came from (Delirium registered at x=181 was selected
                # at x=466). Its label is compared where the selected tab is now.
                follows = tab.get('auto_registered') or has_views(layout_for_tab(tab).id)
                if follows and (selected is None or abs(selected[2]-tab['rect'][2]) > 6):
                    continue
                # Views of one tab have different grids. Their stable outer tab
                # label identifies the parent; the current view is detected separately.
                if has_views(layout_for_tab(tab).id):
                    candidates.append((label_score(frame, selected, tab), tab))
                    continue
                layout = tab.get('layout') or {slot: ref['border'] for slot,ref in self.data['slots'].items()}
                anchors = []
                for slot, border in layout.items():
                    if slot not in layout_for_tab(tab).slots:
                        continue
                    anchors_rects = tab.get('anchor_rects') or (
                        LEGACY_EXPEDITION_SLOTS if tab.get('layout_id') == 'expedition' else ALL_SLOTS)
                    x,y,w,h = anchors_rects[slot]
                    anchors.append(similarity(crop(frame, (x-3,y-3,w+6,3)), np.array(border, np.uint8)))
                if len(anchors) < 5 or sum(s > .80 for s in anchors) / len(anchors) < .8:
                    continue
                candidates.append((label_score(frame, selected if follows else None, tab), tab))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        ranked = [(score, tab['name']) for score, tab in candidates]
        if not candidates or candidates[0][0] < .96:
            self.record_identity(
                'no candidate passed the border filter' if not candidates else
                f'best {ranked[0][1]}={ranked[0][0]:.4f} < .96', ranked)
            return None, t('profile.unknown_tab')
        if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .04:
            self.record_identity(f'ambiguous: {ranked[0][1]} and {ranked[1][1]} '
                                 f'differ by {ranked[0][0]-ranked[1][0]:.4f} < .04', ranked)
            return None, t('profile.ambiguous_identity')
        self.record_identity(f'matched {ranked[0][1]} ({ranked[0][0]:.4f})', ranked)
        return candidates[0][1], ''

    def record_identity(self, verdict, ranked):
        if not self.gate.passes('identity', verdict):
            return
        log.info('tab identity: %s | candidates %s', verdict,
                 format_scores(ranked) or 'none')


# A view button is lit when its underline clears the floor and leads every
# other button. Real captures: lit >= 68.4, lead >= 40. Hover lights less, and
# two lit buttons fail the lead, which falls back to the borders.
SELECTOR_LIT_MIN = 45
SELECTOR_LEAD_MIN = 20


def lit_rune_view(frame):
    """The Runes view whose selector button is lit, or None; with the values."""
    values = selector_underlines(frame)
    (view, lit), (_, second) = sorted(values.items(), key=lambda item: item[1], reverse=True)[:2]
    if lit >= SELECTOR_LIT_MIN and lit - second >= SELECTOR_LEAD_MIN:
        return view, values
    return None, values


class DigitReader:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        self.last_approximate = False
        # The white glyph run the last read found, None when there was none.
        self.last_bounds = None

    def read(self, image):
        self.last_approximate = False
        raw_image = image
        # Counts are white, whereas much of the underlying icon is coloured.
        bright = image.max(axis=2).astype(np.int16)
        dark = image.min(axis=2).astype(np.int16)
        white = ((bright > 160) & (bright-dark < 60)).astype(np.uint8) * 255
        bounds = self.last_bounds = self.counter_bounds(white, image)
        # A decimal point and a K suffix are not digit-shaped components. Check
        # the full counter first so that 24.7K cannot silently become 24 or 247.
        full = self.recognize_info(raw_image)
        # The strip also holds artwork: Omen of Gambling's gold bag beside a
        # `37` read `37M` at 0.58. A real mark is white like its digits, so the
        # strip's mark only counts when its white pixels alone show one too.
        if full.marked or full.approximate:
            white_strip = self.recognize_info(cv2.cvtColor(white, cv2.COLOR_GRAY2BGR))
            if not white_strip.marked:
                full = CounterRead(None if full.approximate else full.quantity, full.confidence, False, False)
        if full.approximate and full.quantity is not None:
            return self.accept(full)
        if bounds is not None:
            x,y,w,h = bounds
            image, white = image[y:y+h,x:x+w], white[y:y+h,x:x+w]
        raw = self.recognize_info(image)
        clean = self.recognize_info(cv2.cvtColor(white, cv2.COLOR_GRAY2BGR))
        if raw.quantity is not None and clean.quantity is not None and raw.quantity != clean.quantity:
            return None, min(raw.confidence, clean.confidence)
        if raw.quantity is not None:
            chosen = raw
        elif clean.quantity is None and bounds is not None and full.quantity is not None:
            # A tight crop can remove the context OCR needs (real Expedition 6).
            # Reuse the already validated full read only when neither crop
            # produced a conflicting number, never when no glyph was found.
            chosen = full
        else:
            chosen = clean
        # A suffix or decimal mark seen by any read, even below the confidence
        # bar, means the counter is abbreviated: an exact number read elsewhere
        # is then the truncated digits of 24.7K, not a count.
        if chosen.quantity is not None and not chosen.approximate and (full.marked or raw.marked or clean.marked):
            return None, chosen.confidence
        return self.accept(chosen)

    def accept(self, info):
        self.last_approximate = info.approximate and info.quantity is not None
        return info.quantity, info.confidence

    @staticmethod
    def counter_bounds(white, image=None):
        """Follow aligned white glyphs from the top-left; ignore distant highlights.

        With `image`, a tinted component is not a glyph: counters are pure
        white (mean saturation 0.0-0.1 measured), while pale artwork touching
        them, such as essence crystals, measures 12.9 and more.
        """
        count, labels, stats, _ = cv2.connectedComponentsWithStats(white)
        def neutral(index):
            if image is None:
                return True
            pixels = image[labels == index].astype(np.int16)
            return float((pixels.max(axis=1) - pixels.min(axis=1)).mean()) <= COUNTER_SATURATION_MAX
        letters = sorted((tuple(map(int,s[:4])) for index, s in enumerate(stats[1:], 1)
                          if 2 <= s[2] <= 15 and 6 <= s[3] <= 18 and s[1] <= 10 and neutral(index)),
                         key=lambda s:s[0])
        if not letters or letters[0][0] > 10:
            return None
        run = [letters[0]]
        for box in letters[1:]:
            prior = run[-1]
            if box[0] - (prior[0]+prior[2]) > 8:
                break
            if abs(box[1]-run[0][1]) <= 3 and abs(box[1]+box[3]-run[0][1]-run[0][3]) <= 3:
                run.append(box)
        x1,y1 = min(b[0] for b in run),min(b[1] for b in run)
        x2,y2 = max(b[0]+b[2] for b in run),max(b[1]+b[3] for b in run)
        return max(0,x1-1),max(0,y1-1),min(white.shape[1],x2+1)-max(0,x1-1),min(white.shape[0],y2+1)-max(0,y1-1)

    def recognize(self, image):
        info = self.recognize_info(image)
        return info.quantity, info.confidence

    def recognize_info(self, image):
        enlarged = cv2.resize(image, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        enlarged = cv2.copyMakeBorder(enlarged, 12,12,12,12, cv2.BORDER_CONSTANT)
        result, _ = self.ocr(enlarged, use_det=False, use_cls=False, use_rec=True)
        if not result:
            return CounterRead(None, 0.0, False, False)
        text, confidence = result[0]
        text = text.strip()
        quantity, approximate = parse_quantity(text)
        # `marked` survives a refused read: it is evidence about the counter's
        # format even when the digits themselves are not trusted. Below
        # MARK_CONFIDENCE_MIN the read is noise: `6M` at 0.38 on a Ritual omen
        # was artwork, while the crops read `6` at 0.99.
        marked = abbreviation_marked(text) and confidence >= MARK_CONFIDENCE_MIN
        if quantity is not None and confidence >= .90:
            return CounterRead(quantity, float(confidence), approximate, marked)
        return CounterRead(None, float(confidence), False, marked)


# The counter strip at the top of a cell, and the taller one retried when a
# counter was found but not read (`Scanner.read_counter`). Glyphs run from
# row 8-9 to 18-19.
COUNTER_HEIGHT = 18
COUNTER_RETRY_HEIGHT = 20

# The most colour a counter glyph may carry (mean max-min of its pixels).
COUNTER_SATURATION_MAX = 6

# The least confidence at which a read's K/M or decimal mark is believed.
MARK_CONFIDENCE_MIN = .5


class CounterRead(NamedTuple):
    quantity: int | None
    confidence: float
    approximate: bool
    marked: bool


def abbreviation_marked(text):
    """A K/M suffix or a decimal mark after a digit: the count is abbreviated."""
    return bool(re.search(r'[0-9][.,]?[0-9]*[KkMm]|[0-9][.,][0-9]', text))


def parse_quantity(text):
    text = text.strip().replace(',', '.')
    if re.fullmatch(r'[0-9]{1,6}', text):
        return int(text), False
    if re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,2})?[KkMm]', text):
        multiplier = 1000 if text[-1].lower() == 'k' else 1_000_000
        return round(float(text[:-1])*multiplier), True
    return None, False


class Scanner:
    def __init__(self, profiles, digits=None, matcher=None):
        self.profiles = profiles
        self.digits = digits or DigitReader()
        self.matcher = matcher or IconMatcher({})
        self.last_layout_id = 'currency'
        # Why the last decision went the way it did, for the session log.
        self.last_layout_scores = []
        self.last_layout_verdict = ''
        self.last_selector = {}
        # What the last detection rested on: 'borders', 'selector', 'icons' or None.
        self.last_layout_basis = None
        self.gate = ChangeGate()
        # Alignment is fitted per frame and per layout; detection and reading ask
        # for the same one on the same frame. Keeping the frame object (never its
        # id()) makes `is` a sound identity test.
        self._aligned_frame = None
        self._aligned = {}
        self.reset_incremental()

    def aligned(self, frame, layout_id, edges=None):
        """`aligned_slots` for this frame, computed once per layout."""
        if self._aligned_frame is not frame:
            self._aligned_frame, self._aligned = frame, {}
        if layout_id not in self._aligned:
            self._aligned[layout_id] = aligned_slots(frame, layout_id, edges)
        return self._aligned[layout_id]

    def reset_incremental(self):
        self.live_cache = {}
        self.live_key = None
        self.live_config = None
        self.live_consensus = Consensus()
        self.last_metrics = {}
        self.preview_readings = []

    def read_incremental(self, frame, layout_id, identity, clock=None):
        """Confirm on fresh images; reuse only fully confirmed, unchanged cells."""
        started = time.perf_counter()
        clock = time.monotonic() if clock is None else clock
        key = (identity, layout_id)
        # A rebuilt matcher must invalidate the cache. id() can be reused after
        # collection, so the matcher carries its own monotonic revision.
        config = (self.matcher.revision, json.dumps(self.profiles.data['slots'], sort_keys=True))
        if key != self.live_key or config != self.live_config:
            self.reset_incremental()
            self.live_key, self.live_config = key, config
        slots = self.aligned(frame, layout_id)
        pending, reusable, matches = [], {}, {}
        patches = {slot: crop(frame, rect) for slot, rect in slots.items()}
        for slot, patch in patches.items():
            old = self.live_cache.get(slot)
            if old is None:
                pending.append(slot)
                continue
            previous, reading, match, checked = old
            same = np.array_equal(previous, patch)
            expired = clock - checked >= 30
            if same and reading.item and reading.quantity is not None and not expired:
                reusable[slot] = reading
                continue
            if expired:
                self.live_consensus.votes.pop(slot, None)
            # Counter changes do not require another icon search.
            if not expired and np.array_equal(previous[19:], patch[19:]):
                matches[slot] = match
            pending.append(slot)
        raw = self.read(frame, layout_id, pending, matches) if pending else []
        self.preview_readings = [*raw, *reusable.values()]
        confirmed = self.live_consensus.push(key, raw)
        for reading in confirmed:
            self.live_cache[reading.slot] = (patches[reading.slot], reading,
                                             self.last_matches[reading.slot], clock)
        result = {r.slot: r for r in confirmed}
        result.update(reusable)
        self.last_metrics = dict(cells=len(slots), ocr=len(pending),
                                 icons=len(pending)-len(matches),
                                 milliseconds=(time.perf_counter()-started)*1000)
        log.debug('frame %s: %d cells, %d re-read, %d icon searches, %.1f ms',
                  layout_id, len(slots), len(pending), len(pending)-len(matches),
                  self.last_metrics['milliseconds'])
        return [result[slot] for slot in slots]

    def detect_layout(self, frame, borders_only=False):
        # Borders identify the structure even with an empty/missing icon catalogue.
        # One set of edge maps serves every layout and their alignment searches.
        self.last_layout_basis = None
        edges = edge_maps(frame)
        vertical, horizontal = edges
        structures = []
        for layout in LAYOUTS.values():
            found = 0
            for x,y,w,h in self.aligned(frame, layout.id, edges).values():
                sides = []
                for edge in (y, y+h):
                    strip = horizontal[max(0,edge-6):edge+7, x+8:x+w-8]
                    sides.append(float(np.max(np.mean(strip > 12, axis=1))))
                for edge in (x, x+w):
                    strip = vertical[y+8:y+h-8, max(0,edge-6):edge+7]
                    sides.append(float(np.max(np.mean(strip > 12, axis=0))))
                found += sum(score >= .65 for score in sides) >= 3
            structures.append((found / len(layout.slots), layout.id))
        structures.sort(reverse=True)
        self.last_layout_scores = structures
        best, runner = structures[0], structures[1]
        # Runes and Kalguuran share most of their borders (0.03 of headroom on
        # a Runes capture), while the lit selector button names the view by a
        # lead of 40. On a frame structured as a Runes stash, the selector
        # decides; its grid must still hold, and it must not contradict a
        # clearly better rune grid.
        view, underlines = lit_rune_view(frame)
        self.last_selector = underlines
        if view is not None and best[1] in RUNE_PAGES:
            scores = {layout_id: score for score, layout_id in structures}
            foreign = max(score for score, layout_id in structures if layout_id not in RUNE_PAGES)
            lit = (f'selector lit {view} ({underlines[view]:.1f}, '
                   f'next {sorted(underlines.values())[-2]:.1f})')
            if scores[view] >= .55 and scores[view]-foreign >= .12 and best[0]-scores[view] < .12:
                self.last_layout_basis = 'selector'
                self.record_layout(f'{lit}; accepted {view} (grid {scores[view]:.3f} >= .55, '
                                   f'{scores[view]-foreign:.3f} over other stashes >= .12)', structures)
                return view
            self.record_layout(f'{lit}; rejected: grid {scores[view]:.3f}, best {best[1]} '
                               f'{best[0]:.3f}, other stashes {foreign:.3f}', structures)
            return None
        if best[0] >= .55 and best[0]-runner[0] >= .12:
            self.last_layout_basis = 'borders'
            self.record_layout(f'borders accepted {best[1]} '
                               f'(score {best[0]:.3f} >= .55, margin {best[0]-runner[0]:.3f} >= .12)',
                               structures)
            return best[1]
        reason = (f'score {best[0]:.3f} < .55' if best[0] < .55
                  else f'margin over {runner[1]} only {best[0]-runner[0]:.3f} < .12')
        if borders_only:
            self.record_layout(f'borders rejected: {reason}', structures)
            return None
        scores = []
        for layout in LAYOUTS.values():
            matches = self.matcher.match_many([crop(frame, rect) for rect in layout.slots.values()])
            score = sum(bool(match.alternatives) for match in matches)
            scores.append((score,layout.id))
        scores.sort(reverse=True)
        if scores[0][0] < 2 or scores[0][0] - scores[1][0] < 2:
            self.record_layout(
                f'borders rejected ({reason}); icons rejected too '
                f'(best {scores[0][1]}={scores[0][0]}, runner {scores[1][1]}={scores[1][0]}, '
                'needs >=2 and a lead of >=2)', structures, scores)
            return None
        self.last_layout_basis = 'icons'
        self.record_layout(f'borders rejected ({reason}); icons accepted {scores[0][1]} '
                           f'({scores[0][0]} vs {scores[1][0]})', structures, scores)
        return scores[0][1]

    def record_layout(self, verdict, borders, icons=None):
        """Log a layout decision, but only when the verdict actually changes."""
        self.last_layout_verdict = verdict
        if not self.gate.passes('layout', verdict):
            return
        message = 'layout: %s | borders %s' % (verdict, format_scores(borders))
        if icons is not None:
            message += ' | icons %s' % format_scores(icons)
        log.info(message)

    def read_counter(self, frame, rect):
        """A cell's stack count: (quantity, confidence, approximate).

        The strip stops at row 18, where the lowest glyph rows are cut; most
        digits survive that, but a `4` without its foot reads `1`. A taller
        strip reaches the artwork under the digits and broke seven counts
        that the short one read right, so it is only a second chance for a
        counter the short strip found but could not read.
        """
        x, y, w, _h = rect
        quantity, confidence = self.digits.read(crop(frame, (x, y, w, COUNTER_HEIGHT)))
        approximate = getattr(self.digits, 'last_approximate', False)
        if quantity is None and getattr(self.digits, 'last_bounds', None) is not None:
            retry, retry_confidence = self.digits.read(crop(frame, (x, y, w, COUNTER_RETRY_HEIGHT)))
            if retry is not None:
                return retry, retry_confidence, getattr(self.digits, 'last_approximate', False)
        return quantity, confidence, approximate

    def read(self, frame, layout_id='currency', slot_ids=None, cached_matches=None):
        self.last_layout_id = layout_id
        slots = self.aligned(frame, layout_id)
        if slot_ids is not None:
            slots = {slot: rect for slot, rect in slots.items() if slot in slot_ids}
        results = []
        matches = dict(cached_matches or {})
        missing = [slot for slot in slots if slot not in matches]
        if missing:
            matches.update(zip(missing, self.matcher.match_many([crop(frame, slots[slot]) for slot in missing])))
        self.last_matches = matches
        for slot, rect in slots.items():
            match = matches[slot]
            x,y,w,h = rect
            # Read the white stack count independently of icon recognition.
            quantity, confidence, approximate = self.read_counter(frame, rect)
            ref = self.profiles.data['slots'].get(slot)
            # A dark cell with no counter is empty even when an icon matches it:
            # sparse, dark artwork (Carved Mischief) matches the ghost that views
            # like Breach draw in their empty cells at 0.92 and above, while no
            # real item measured is that dark. It can never name an empty cell.
            if quantity is None and not ref and visually_empty(crop(frame, rect)):
                results.append(Reading(slot, None, None, 0, Reason.EMPTY))
                continue
            item = dedicated_item(slot, match)
            if item is None and (slot in SLOT_ITEMS or slot in SLOT_FAMILIES) and (match.item or match.contenders):
                log.debug('cell %s: artwork %s does not fit its dedicated cell', slot,
                          match.item or match.contenders)
                # Refused by its cell: unrecognised, not a variant of the refused item.
                match = IconMatch(None, match.confidence, match.candidate, match.margin)
            if len(match.alternatives) > 1:
                expected = TIER_ITEMS.get(slot)
                if expected in match.alternatives and set(match.alternatives) <= POSITION_FAMILIES.get(slot, set()):
                    item = expected
            local_override = bool(ref and ref.get('override') and 'icon' in ref and
                                  similarity(icon_patch(frame,rect),np.array(ref['icon'],np.uint8)) >= .9)
            if local_override:
                item = ref['item']
            if item:
                results.append(Reading(slot, item, quantity, min(match.confidence, confidence),
                                       (Reason.LOCAL_REF if local_override else Reason.AUTO) if quantity is not None else Reason.UNREADABLE_COUNT, approximate))
                continue
            if not ref:
                reason = Reason.VARIANT if match.alternatives else Reason.UNKNOWN_ICON
                results.append(Reading(slot, None, quantity, confidence, reason, approximate, tuple(match.alternatives)))
                continue
            icon = icon_patch(frame, rect)
            present = similarity(icon, np.array(ref['icon'], np.uint8)) if 'icon' in ref else 0
            empty = similarity(icon, np.array(ref['empty'], np.uint8)) if 'empty' in ref else 0
            if empty >= .94 and empty - present > .06:
                results.append(Reading(slot, ref['item'], 0, empty, Reason.EMPTY_CONFIRMED))
            elif present >= .86 and present - empty > .06:
                results.append(Reading(slot, ref['item'], quantity, min(present, confidence),
                                       Reason.LOCAL_REF if quantity is not None else Reason.UNREADABLE_COUNT, approximate))
            else:
                results.append(Reading(slot, None, quantity, confidence, Reason.HIDDEN_ICON, approximate))
        self.record_coverage(layout_id, results, matches)
        return results

    def record_coverage(self, layout_id, results, matches):
        """Log the cells that stayed unidentified, with the near-miss the matcher saw.

        `IconMatch.candidate` and `.margin` exist for exactly this question: when a
        cell is refused, what was the runner-up and by how much did it miss?
        """
        unknown = [r for r in results if r.item is None and r.reason != Reason.EMPTY]
        identified = sum(1 for r in results if r.item)
        empty = sum(1 for r in results if r.reason == Reason.EMPTY)
        state = (layout_id, identified, empty, tuple(sorted(r.slot for r in unknown)))
        if not self.gate.passes('coverage', state):
            return
        log.info('recognition %s: %d identified, %d empty, %d unidentified',
                 layout_id, identified, empty, len(unknown))
        for reading in unknown:
            match = matches.get(reading.slot)
            if match is None:
                continue
            log.info('  %-4s unidentified reason=%-15s best=%-28s score=%.4f margin=%.4f',
                     reading.slot, reading.reason, match.candidate, match.confidence, match.margin)


def visually_empty(cell):
    """Conservative visual filter; an empty cell is never a stored zero."""
    if cell.shape[0] < 30 or cell.shape[1] < 30:
        return False
    brightness = cell[18:].max(axis=2)
    return np.percentile(brightness, 95) < 65 and np.mean(brightness > 85) < .02


class Consensus:
    """Require matching observations; never carry a vote across another tab."""
    def __init__(self, required=3):
        self.required = required
        self.reset()

    def reset(self):
        self.tab = None
        self.votes = {}

    def push(self, tab, readings):
        if tab != self.tab:
            self.reset()
            self.tab = tab
        accepted = []
        for r in readings:
            previous, count = self.votes.get(r.slot, (None, 0))
            empty = r.reason == Reason.EMPTY
            key = (r.item, r.quantity, r.approximate, empty)
            count = count + 1 if key == previous and (r.quantity is not None or empty) else 1
            self.votes[r.slot] = (key, count)
            if (r.quantity is None and not empty) or count < self.required:
                accepted.append(Reading(r.slot, r.item, None, r.confidence,
                                        r.reason if r.quantity is None and not empty else Reason.PENDING, r.approximate, r.alternatives))
            else:
                accepted.append(Reading(**asdict(r)))
        return accepted
