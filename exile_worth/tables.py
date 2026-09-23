"""Sortable tables: how a displayed cell orders against its neighbours.

The tables are rebuilt on every live reading, so the order is not a one-off
action on click: it is a state the table reapplies after each refresh.
"""
from __future__ import annotations

import re

# A displayed number: `1,234`, `≈ 24,700`, `0.125`, optionally followed by a
# parenthesised note such as ` (provisional)` or a pending change `→ 145 (provisional)`,
# which sorts by the confirmed number before the arrow. Thousands use a comma, as every
# quantity in the interface is formatted with `{:,}`.
_NUMBER = re.compile(r'^\s*≈?\s*(-?[0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:\(.*\)|→.*)?\s*$')
_MISSING = {'', '—', '-'}


def sort_key(text):
    """Numbers by value, text in natural order (C2 before C10), blanks last.

    Blanks stay last whichever direction is chosen; `sorted_rows` handles that,
    because reversing the whole key would bring them first.
    """
    text = str(text).strip()
    if text in _MISSING:
        return (2, ())
    number = _NUMBER.match(text)
    if number:
        return (0, (float(number.group(1).replace(',', '')),))
    return (1, tuple(int(part) if part.isdigit() else part.casefold()
                     for part in re.split(r'([0-9]+)', text)))


def sorted_rows(rows, descending=False):
    """Order (row id, cell text) pairs; missing values stay at the bottom."""
    present = [row for row in rows if sort_key(row[1])[0] != 2]
    missing = [row for row in rows if sort_key(row[1])[0] == 2]
    present.sort(key=lambda row: sort_key(row[1]), reverse=descending)
    return [row_id for row_id, _ in present + missing]
