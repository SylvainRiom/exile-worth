"""A problem report: one local zip the player sends to whoever helps them.

Nothing is uploaded. The player chooses where the file goes and who gets it,
which keeps the rule that no screenshot or inventory leaves the machine on
its own.
"""
from __future__ import annotations

import csv
import io
import json
import platform
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import cv2

from . import __version__

# Everything the recogniser reads lies in this corner of the normalised
# 1920x1080 frame: the tab bar, every stash grid, the Runes selector and the
# side menu (x 685..854). Cropping to it leaves out the chat and the
# character, and matches the real captures under tests/fixtures.
STASH_AREA = (860, 765)

# The tab fields worth reading; the label and border pixels are left out.
TAB_FIELDS = ('id', 'name', 'visible_name', 'league', 'layout_id', 'rect', 'auto_registered')


def stash_crop(frame):
    width, height = STASH_AREA
    return frame[:height, :width]


def safe_name(text):
    """A file name part: letters, digits, dashes; never empty."""
    return re.sub(r'[^\w-]+', '-', text, flags=re.UNICODE).strip('-') or 'tab'


def png(frame):
    ok, encoded = cv2.imencode('.png', stash_crop(frame))
    if not ok:
        raise ValueError('PNG encoding failed')
    return encoded.tobytes()


def build_report(path, data_dir, summary, frames=(), rows=()):
    """Write the report to `path` and return the names it holds.

    `summary` is JSON-ready context; `frames` are (label, frame) pairs;
    `rows` are the stored cells, written as CSV.
    """
    names = []
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        report = dict(summary, version=__version__,
                      created=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      system=platform.platform(), python=platform.python_version())
        archive.writestr('report.json', json.dumps(report, ensure_ascii=False, indent=2, default=str))
        names.append('report.json')
        used = set()
        for label, frame in frames:
            if frame is None:
                continue
            name = f'stash-{safe_name(label)}.png'
            index = 2
            while name in used:
                name = f'stash-{safe_name(label)}-{index}.png'
                index += 1
            used.add(name)
            archive.writestr(name, png(frame))
            names.append(name)
        table = io.StringIO()
        writer = csv.writer(table)
        writer.writerow(['tab_id', 'slot', 'item_id', 'quantity', 'confirmed_utc', 'uncertain'])
        writer.writerows(rows)
        archive.writestr('inventory.csv', table.getvalue())
        names.append('inventory.csv')
        # The log and its rotations, oldest last, as the handler names them.
        for log in sorted(Path(data_dir).glob('session.log*')):
            archive.write(log, log.name)
            names.append(log.name)
    return names


def reveal(path):
    """Show the report selected in Explorer, so the player can drag it away."""
    try:
        subprocess.Popen(['explorer', f'/select,{Path(path)}'])
    except OSError:
        pass


def tab_summary(tab):
    return {field: tab[field] for field in TAB_FIELDS if field in tab}
