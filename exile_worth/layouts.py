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


def _breach_catalysts():
    """The Catalysts view of the Breach tab, measured on a real 1920x1080 capture.

    Two small cells and one large at the top (splinters, Breachlord Sac,
    Breachstone), then four rows of catalysts: normal ones on rows of 6 and 7,
    refined ones below on the same pattern. Rows of 7 sit half a cell left.
    """
    cells = [(270, 226, 57, 57), (338, 226, 57, 57), (277, 294, 110, 109)]
    six, seven = (135, 203, 270, 338, 405, 472), (102, 169, 237, 304, 372, 439, 507)
    for y, xs in ((434, six), (502, seven), (590, six), (657, seven)):
        cells += [(x, y, 57, 57) for x in xs]
    return {f'B{index:02}': rect for index, rect in enumerate(cells, 1)}


# Views of the Breach tab. `breach` is the family name too, as `runes` is; the
# Wombgifts view is added once it has been measured on a real capture.
BREACH_PAGES = {
    'breach': ('Breach Catalysts', _breach_catalysts()),
}


# Four single-view tabs measured on real 1920x1080 captures (23 September 2026),
# cell by cell from their edge profiles, then checked by overlay. Cells are
# listed top to bottom; their order only names them.
def _cells(prefix, rects):
    return {f'{prefix}{index:02}': rect for index, rect in enumerate(rects, 1)}


# Abyss: a diamond of 13 cells above a row of 8.
ABYSS_SLOTS = _cells('AB', [
    (305, 181, 56, 58), (305, 281, 54, 58), (239, 347, 54, 58), (305, 347, 54, 58),
    (370, 347, 56, 58), (206, 413, 54, 56), (270, 413, 57, 56), (338, 413, 55, 57),
    (403, 413, 58, 57), (237, 480, 56, 58), (303, 480, 56, 58), (370, 480, 54, 58),
    (303, 546, 56, 58), (74, 645, 54, 57), (140, 644, 54, 58), (206, 644, 54, 58),
    (272, 644, 54, 58), (338, 644, 54, 58), (403, 644, 56, 58), (471, 644, 54, 58),
    (537, 644, 54, 58),
])

# Delirium: two mirrored groups of 10 around a column of 4, top and bottom rows.
DELIRIUM_SLOTS = _cells('DE', [
    (265, 181, 57, 55), (346, 181, 57, 55), (306, 248, 55, 57), (82, 322, 56, 57),
    (149, 322, 56, 57), (217, 322, 56, 57), (393, 322, 54, 57), (461, 322, 55, 57),
    (527, 322, 55, 57), (115, 390, 57, 55), (183, 390, 55, 55), (426, 390, 55, 55),
    (493, 390, 57, 55), (82, 474, 56, 57), (149, 474, 55, 57), (217, 474, 56, 57),
    (393, 474, 54, 57), (461, 474, 55, 57), (527, 474, 55, 57), (115, 542, 57, 55),
    (183, 542, 55, 55), (426, 542, 55, 55), (493, 542, 57, 55), (305, 359, 56, 56),
    (303, 427, 58, 57), (305, 494, 56, 56), (95, 631, 55, 54), (166, 629, 55, 56),
    (234, 629, 57, 56), (371, 629, 57, 56), (442, 629, 54, 56), (510, 629, 57, 56),
])

# Essences: two blocks of 4 columns (10 rows left, 9 right), a tall centre cell,
# a 2x2 group and a 2x3 group in the centre column.
ESSENCE_SLOTS = _cells('ES', [
    (44, 145, 51, 50), (98, 145, 51, 50), (152, 145, 51, 50), (209, 145, 51, 50),
    (44, 206, 51, 50), (98, 206, 51, 50), (152, 206, 51, 50), (209, 206, 51, 50),
    (44, 266, 51, 50), (98, 266, 51, 50), (152, 266, 51, 50), (209, 266, 51, 50),
    (44, 327, 51, 50), (98, 327, 51, 50), (152, 327, 51, 50), (209, 327, 51, 50),
    (44, 388, 51, 50), (98, 388, 51, 50), (152, 388, 51, 50), (209, 388, 51, 50),
    (44, 449, 51, 50), (98, 449, 51, 50), (152, 449, 51, 50), (209, 449, 51, 50),
    (44, 509, 51, 50), (98, 509, 51, 50), (152, 509, 51, 50), (209, 509, 51, 50),
    (44, 570, 51, 50), (98, 570, 51, 50), (152, 570, 51, 50), (209, 570, 51, 50),
    (44, 631, 51, 50), (98, 631, 51, 50), (152, 631, 51, 50), (209, 631, 51, 50),
    (44, 692, 51, 50), (98, 692, 51, 50), (152, 692, 51, 50), (209, 692, 51, 50),
    (404, 145, 51, 50), (458, 145, 51, 50), (512, 145, 51, 50), (571, 145, 51, 50),
    (404, 206, 51, 50), (458, 206, 51, 50), (512, 206, 51, 50), (571, 206, 51, 50),
    (404, 266, 51, 50), (458, 266, 51, 50), (512, 266, 51, 50), (571, 266, 51, 50),
    (404, 327, 51, 50), (458, 327, 51, 50), (512, 327, 51, 50), (571, 327, 51, 50),
    (404, 388, 51, 50), (458, 388, 51, 50), (512, 388, 51, 50), (571, 388, 51, 50),
    (404, 449, 51, 50), (458, 449, 51, 50), (512, 449, 51, 50), (571, 449, 51, 50),
    (404, 509, 51, 50), (458, 509, 51, 50), (512, 509, 51, 50), (571, 509, 51, 50),
    (404, 570, 51, 50), (458, 570, 51, 50), (512, 570, 51, 50), (571, 570, 51, 50),
    (404, 631, 51, 50), (458, 631, 51, 50), (512, 631, 51, 50), (571, 631, 51, 50),
    (284, 184, 98, 193), (280, 388, 50, 50), (334, 388, 50, 50), (280, 449, 50, 50),
    (334, 449, 50, 50), (280, 570, 50, 50), (334, 570, 50, 50), (280, 631, 50, 50),
    (334, 631, 50, 50), (280, 692, 50, 50), (334, 692, 50, 50),
])

# Ritual: an irregular layout of 33 cells, one of them wide at the top.
RITUAL_SLOTS = _cells('RI', [
    (203, 150, 57, 57), (278, 150, 106, 57), (404, 150, 57, 57), (203, 251, 57, 57),
    (348, 251, 57, 57), (409, 251, 57, 57), (108, 339, 57, 57), (169, 339, 57, 57),
    (230, 339, 57, 57), (317, 339, 57, 57), (378, 339, 57, 57), (439, 339, 57, 57),
    (139, 400, 57, 57), (199, 400, 57, 57), (317, 400, 57, 57), (378, 400, 57, 57),
    (439, 400, 57, 57), (500, 400, 57, 57), (125, 488, 57, 57), (186, 488, 57, 57),
    (274, 488, 57, 57), (334, 488, 57, 57), (423, 488, 57, 57), (483, 488, 57, 57),
    (125, 575, 57, 57), (186, 575, 57, 57), (108, 677, 57, 57), (169, 677, 57, 57),
    (230, 677, 57, 57), (317, 677, 57, 57), (378, 677, 57, 57), (439, 677, 57, 57),
    (500, 677, 57, 57),
])

# A stash type made of several views keeps one profile for all of them, with a
# separate cell namespace per view so a hidden view keeps its stock. The first
# view's id is also the family's id and the stored `layout_id` of its tabs.
VIEW_FAMILIES = {
    'runes': tuple(RUNE_PAGES),
    'breach': tuple(BREACH_PAGES),
}

LAYOUTS = {
    'currency':Layout('currency','Currencies',CURRENCY_SLOTS),
    'expedition':Layout('expedition','Expedition',EXPEDITION_SLOTS),
    'abyss':Layout('abyss','Abyss',ABYSS_SLOTS),
    'delirium':Layout('delirium','Delirium',DELIRIUM_SLOTS),
    'essences':Layout('essences','Essences',ESSENCE_SLOTS),
    'ritual':Layout('ritual','Ritual',RITUAL_SLOTS),
}
LAYOUTS.update({key: Layout(key, name, slots) for key, (name, slots) in RUNE_PAGES.items()})
LAYOUTS.update({key: Layout(key, name, slots) for key, (name, slots) in BREACH_PAGES.items()})
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
    return next((family for family, views in VIEW_FAMILIES.items() if layout_id in views), layout_id)


def has_views(layout_id):
    """True for a stash type made of several views (Runes, Breach)."""
    return layout_family(layout_id) in VIEW_FAMILIES


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
    if has_views(layout.id):
        return sum(len(LAYOUTS[key].slots) for key in VIEW_FAMILIES[layout_family(layout.id)])
    return len(layout.slots)
