"""Stash geometry in normalized 1920x1080 client coordinates."""
from dataclasses import dataclass

from .i18n import t


@dataclass(frozen=True)
class Layout:
    id: str
    name: str
    slots: dict


CURRENCY_SLOTS = {}
for row, y in enumerate((154,222,289,357,425)):
    for column,x in enumerate((33,94,155)):
        CURRENCY_SLOTS[f'L{row+1}{column+1}'] = (x,y,52,51)
for index,(x,y) in enumerate([
    (237,154),(303,154),(371,154),(449,154),(509,154),(573,154),
    (237,222),(303,222),(371,222),(573,222),
    (270,290),(337,290),(438,310),(506,310),(573,310),
    (506,378),(573,378),(573,466),
    (203,553),(270,553),(337,553),(404,553),
]):
    CURRENCY_SLOTS[f'C{index+1:02}'] = (x,y,52,51)

# Second reference image is 1902x1080; normalize horizontal coordinates too.
EXPEDITION_SLOTS = {}
points = [(x,181,51,51) for x in (123,190,257,324,392,460)]
points += [(205,278,101,101),(324,278,101,101)]
points += [(x,404,51,51) for x in (191,259,395)]
points += [(x,471,51,51) for x in (191,259,326,395)]
points += [(x,546,51,51) for x in (87,155,223,291,359,428,496)]
points += [(x,614,51,51) for x in (122,190,258,326,394,462)]
points += [(x,688,51,51) for x in (191,259,326,395)]
for index,(x,y,w,h) in enumerate(points):
    EXPEDITION_SLOTS[f'E{index+1:02}'] = (round(x*1920/1902),y,round(w*1920/1902),h)

# The original coordinates came from a cropped chat image. On the saved full
# 1920x1080 client capture every Expedition column is 14 px farther right.
# Retain the old anchor positions for profiles registered before this correction.
LEGACY_EXPEDITION_SLOTS = dict(EXPEDITION_SLOTS)
EXPEDITION_SLOTS = {slot:(x+14,y,w,h) for slot,(x,y,w,h) in EXPEDITION_SLOTS.items()}


def _rune_grid(prefix, rows):
    return {f'{prefix}{index:02}': (x, y, 52, 52)
            for index, (x, y) in enumerate(((x, y) for y, xs in rows for x in xs), 1)}


# Measured from the five chat screenshots (the game client content is shown at
# native vertical scale). Keep separate slot namespaces so hidden pages survive
# a sync of the currently visible page.
RUNE_PAGES = {
    'runes': ('Runes', _rune_grid('R', [
        (y, (35, 97, 159, 245, 307, 369, 455, 517, 579))
        for y in (199, 267, 334, 401, 468)] + [
        (550, (35, 97, 159, 245, 455, 517, 579)),
        (618, (35, 97, 159, 245, 307, 369, 455, 517, 579)),
        (686, (35, 97, 159, 245, 307, 369, 455, 517, 579))])),
    'kalguuran': ('Kalguuran Runes', _rune_grid('K', [
        (200, (137, 204, 271, 338, 405, 472)),
        (267, (137, 204, 271, 338, 405, 472)),
        (334, (170, 237, 304, 371, 438)),
        (408, (35, 103, 170, 237, 304, 371, 438, 505, 572)),
        (475, (35, 103, 170, 237, 304, 371, 438, 505, 572)),
        (543, (35, 103, 170, 237, 304, 371, 438, 505, 572)),
        (618, (103, 170, 237, 304, 371, 438, 505)),
        (686, (35, 103, 170, 237, 304, 371, 438, 505, 572))])),
    'soul_cores': ('Soul Cores', _rune_grid('S', [
        (209, (69, 136, 203, 270, 337, 404, 471, 538)),
        (277, (103, 170, 237, 304, 371, 438, 505)),
        (363, (69, 136, 203, 270, 337, 404, 471, 538)),
        (431, (103, 170, 237, 304, 371, 438, 505)),
        (519, (103, 170, 237, 304, 371, 438, 505)),
        (587, (136, 203, 270, 337, 404, 471)),
        (674, (203, 270, 337, 404))])),
    'idols': ('Idols', _rune_grid('I', [
        (223, (69, 136, 203, 270, 337, 404, 471, 538)),
        (299, (136, 203, 270, 337, 404, 471)),
        (417, (103, 170, 237, 304, 371, 438, 505)),
        (531, (103, 170, 237, 304, 371, 438, 505)),
        (647, (237, 304, 371))])),
    'ancient_augments': ('Ancient Augments', _rune_grid('A', [
        (213, (203, 270, 337, 404)),
        (327, (203, 270, 337, 404)),
        (442, (304,)),
        (557, (203, 270, 337, 404)),
        (672, (203, 270, 337, 404))])),
}

LAYOUTS = {
    'currency':Layout('currency','Currencies',CURRENCY_SLOTS),
    'expedition':Layout('expedition','Expedition',EXPEDITION_SLOTS),
}
LAYOUTS.update({key: Layout(key, name, slots) for key, (name, slots) in RUNE_PAGES.items()})
ALL_SLOTS = {slot:rect for layout in LAYOUTS.values() for slot,rect in layout.slots.items()}
UNKNOWN_LAYOUT = Layout('unknown', 'Unrecognised type', {})

# The Runes tab's view selector: five buttons above the grid, in RUNE_PAGES
# order, 64 px apart. The visible view carries an amber underline along the
# bottom of its button; hovering lights one far less sharply. Only that strip
# is measured, so the golden conch artwork above it does not count. Measured
# on the five real 1920x1080 captures: lit 68 to 73, unlit 27 to 28.
SELECTOR_X = (175, 239, 303, 367, 431)
SELECTOR_UNDERLINE = (176, 182)
SELECTOR_INSET = 8


def selector_underlines(frame):
    """Amber excess (red minus blue) of each view button's underline, by view."""
    import numpy as np

    top, bottom = SELECTOR_UNDERLINE
    band = frame[top:bottom].astype(np.int16)
    warm = band[:, :, 2] - band[:, :, 0]
    return {view: float(warm[:, x+SELECTOR_INSET:x+64-SELECTOR_INSET].mean())
            for view, x in zip(RUNE_PAGES, SELECTOR_X)}


def layout_name(layout_id):
    """Display name for a layout. `Layout.name` stays the English fallback."""
    return t(f'layout.{layout_id}')


def layout_family(layout_id):
    return 'runes' if layout_id in RUNE_PAGES else layout_id


# Every layout's cells fit inside this window, with room for the +/-20 px
# alignment search and the +7 px scoring strips (measured: 658 x 766).
REGION = (800, 700)


def edge_maps(frame):
    """Gradient magnitudes over the stash region: (vertical, horizontal).

    Detection scores four sides of every cell of every layout, so these maps are
    read many times per frame but depend only on the frame. Building them once
    and passing them down is worth about 27 ms per live-loop iteration.
    """
    import cv2
    import numpy as np

    height, width = REGION
    gray = cv2.cvtColor(frame[:height, :width], cv2.COLOR_BGR2GRAY).astype(np.float32)
    return np.abs(np.diff(gray, axis=1)), np.abs(np.diff(gray, axis=0))


def aligned_slots(frame, layout_id, edges=None):
    """Fit a common translation to the case borders, never to item identity.

    An unconvincing fit leaves the reference geometry unchanged. Each layout
    keeps its own rectangles; this cannot turn an unknown structure into another.

    `edges` accepts the maps from `edge_maps(frame)` when a caller already built
    them for this frame; the result is identical either way.
    """
    import numpy as np

    slots = LAYOUTS[layout_id].slots
    edges = edge_maps(frame) if edges is None else edges
    offsets = [0, 0]
    for axis in (0, 1):
        scores = np.zeros(41)
        for x,y,w,h in slots.values():
            if axis == 0:
                strips = [edges[0][y+8:y+h-8, x+d-22:x+d+22] for d in (0,w)]
            else:
                x += offsets[0]
                strips = [edges[1][y+d-22:y+d+22, x+8:x+w-8] for d in (0,h)]
            for strip in strips:
                profile = np.mean(strip > 12, axis=axis)
                strength = np.maximum.reduce([profile[i:i+41] for i in range(4)])
                scores += strength >= .65
        scores /= 2*len(slots)
        best = scores.max()
        if best >= .65 and best - scores[20] >= .20:
            peaks = np.flatnonzero(scores == best)
            groups = np.split(peaks, np.flatnonzero(np.diff(peaks) > 1)+1)
            peak = max(groups, key=lambda group:(len(group), -abs(np.mean(group)-20)))
            offsets[axis] = int(round(float(np.mean(peak))))-20
    dx,dy = offsets
    return {slot:(x+dx,y+dy,w,h) for slot,(x,y,w,h) in slots.items()}


def layout_for_tab(tab):
    # Existing profiles remain valid and keep their inventory IDs.
    return LAYOUTS.get(tab.get('layout_id','currency'),LAYOUTS['currency'])


def expected_slot_count(tab):
    """How many cells a registered tab is expected to cover.

    A Runes tab is a single profile spanning five view geometries, so it expects
    the sum of all five, not just the visible one. This lived in three identical
    copies in `app.py`; the next multi-view stash would have made them diverge.
    """
    layout = layout_for_tab(tab)
    if layout_family(layout.id) == 'runes':
        return sum(len(LAYOUTS[key].slots) for key in RUNE_PAGES)
    return len(layout.slots)
